"""Swing analysis on synthetic swings with known phase times."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.landmarks import LANDMARK_INDEX as I
from app.swing import analyse_swing
from app.swing.series import fill_gaps, mirror_permutation, savgol

FPS = 60.0
# Phase times of the synthetic swing (seconds of real time).
ADDRESS_END, TOP_START, TOP_END, IMPACT, FINISH, END = 0.8, 1.6, 1.7, 1.95, 2.6, 3.2


def _ease(u: float) -> float:
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(u, 0.0, 1.0))


def hands_at(t: float) -> tuple[float, float]:
    """Normalised (x, y) of the hands. y: 0.62 low (address/impact), 0.30 top, 0.28 finish."""
    if t < ADDRESS_END:
        return 0.55, 0.62
    if t < TOP_START:
        u = _ease((t - ADDRESS_END) / (TOP_START - ADDRESS_END))
        return 0.55 - 0.15 * u, 0.62 - 0.32 * u
    if t < TOP_END:
        return 0.40, 0.30
    if t < IMPACT:
        u = ((t - TOP_END) / (IMPACT - TOP_END)) ** 2  # accelerating downswing
        return 0.40 + 0.15 * u, 0.30 + 0.32 * u
    if t < FINISH:
        u = _ease((t - IMPACT) / (FINISH - IMPACT))
        return 0.55 + 0.10 * u, 0.62 - 0.34 * u
    return 0.65, 0.28


def make_payload(
    camera_angle="down_the_line",
    handedness="right",
    time_scale=1.0,
    fps=FPS,
    mirror_footage=False,
    still=False,
    drop_frames=(),
):
    """A down-the-line style golfer: torso bent toward +x (the ball side), hands in front of the hips.

    ``time_scale`` > 1 slows the motion down (a slow-motion clip saved at ``fps``).
    ``mirror_footage`` produces what a left-handed golfer's camera would record.
    """
    n = int(END * time_scale * fps)
    frames = []
    for i in range(n):
        t_video = i / fps
        t_real = t_video / time_scale
        lm = np.zeros((33, 5))
        lm[:, 3:] = 0.95
        lm[:, :2] = (0.5, 0.5)
        lm[I["nose"], :2] = (0.58, 0.28)
        lm[I["left_ear"], :2] = (0.56, 0.26)
        lm[I["right_ear"], :2] = (0.56, 0.26)
        lm[I["left_shoulder"], :2] = (0.56, 0.35)
        lm[I["right_shoulder"], :2] = (0.54, 0.35)
        lm[I["left_hip"], :2] = (0.46, 0.55)
        lm[I["right_hip"], :2] = (0.44, 0.55)
        lm[I["left_knee"], :2] = (0.50, 0.70)
        lm[I["right_knee"], :2] = (0.50, 0.70)
        lm[I["left_ankle"], :2] = (0.47, 0.88)
        lm[I["right_ankle"], :2] = (0.47, 0.88)
        hx, hy = (0.55, 0.62) if still else hands_at(t_real)
        for w in ("left_wrist", "right_wrist"):
            lm[I[w], :2] = (hx, hy)
        if mirror_footage:
            lm[:, 0] = 1.0 - lm[:, 0]
            lm = lm[mirror_permutation()]
        frames.append({"i": i, "t": round(t_video, 4), "n": 1, "lm": None if i in drop_frames else lm.tolist()})
    return {
        "format": "golfcoach.keypoints.v1",
        "video": {"width": 720, "height": 1280, "fps": fps, "frame_count": n, "rotation_degrees": 0},
        "camera_angle": camera_angle,
        "handedness": handedness,
        "frames": frames,
    }


def phase_times(result):
    return {p["name"]: p["timestamp_s"] for p in result["phases"]}


def measurements(result):
    return {m["name"]: m for m in result["measurements"]}


def test_detects_phases_of_a_synthetic_swing():
    result = analyse_swing(make_payload())
    assert result["status"] == "ok", result["notes"]
    t = phase_times(result)
    assert list(t) == ["address", "takeaway", "top", "impact", "finish"]
    assert t["address"] < ADDRESS_END
    # Takeaway = hands 8% of a torso length from address; this backswing eases in, so that is ~0.15 s later.
    assert ADDRESS_END <= t["takeaway"] <= ADDRESS_END + 0.2
    assert t["top"] == pytest.approx(TOP_END, abs=0.05)  # end of the pause, when the hands start down
    assert t["impact"] == pytest.approx(IMPACT, abs=0.05)
    assert FINISH - 0.15 < t["finish"] <= FINISH + 0.05
    assert not any(n["code"] == "slow_motion_suspected" for n in result["notes"])


def test_measurements_have_expected_values_and_metadata():
    m = measurements(analyse_swing(make_payload()))
    # Shoulders 0.1 * 720 px toward the ball over 0.2 * 1280 px of torso: atan(72 / 256) = 15.7 deg.
    assert m["spine_angle_address"]["value"] == pytest.approx(15.7, abs=0.5)
    assert m["spine_angle_change_impact"]["value"] == pytest.approx(0.0, abs=0.5)
    assert m["head_rise_impact"]["value"] == pytest.approx(0.0, abs=1.0)
    tempo = (TOP_END - ADDRESS_END) / (IMPACT - TOP_END)
    assert m["tempo_ratio"]["value"] == pytest.approx(tempo, rel=0.15)
    for item in m.values():
        assert item["type"] in ("measured", "estimated")
        assert 0.0 <= item["confidence"] <= 1.0
        assert item["unit"] in ("deg", "% torso", "ratio", "s")
    assert m["tempo_ratio"]["type"] == "estimated"
    assert m["spine_angle_address"]["type"] == "measured"


def test_left_handed_golfer_gets_the_same_results_as_mirrored_right_handed():
    right = analyse_swing(make_payload())
    left = analyse_swing(make_payload(handedness="left", mirror_footage=True))
    assert left["mirrored_for_left_handed"] is True
    assert phase_times(left) == phase_times(right)
    for name, m in measurements(right).items():
        assert measurements(left)[name]["value"] == pytest.approx(m["value"], abs=0.2), name


def test_slow_motion_clip_drops_all_timing_values():
    result = analyse_swing(make_payload(time_scale=4.0, fps=30.0))
    assert result["status"] == "ok"
    assert any(n["code"] == "slow_motion_suspected" for n in result["notes"])
    names = measurements(result)
    assert "spine_angle_address" in names
    assert not {"tempo_ratio", "backswing_duration", "downswing_duration"} & names.keys()


def test_low_frame_rate_lowers_impact_confidence():
    fast = {p["name"]: p["confidence"] for p in analyse_swing(make_payload(fps=120.0))["phases"]}
    slow = {p["name"]: p["confidence"] for p in analyse_swing(make_payload(fps=30.0))["phases"]}
    assert slow["impact"] < fast["impact"]
    assert slow["top"] == fast["top"]


def test_standing_still_is_not_a_swing():
    result = analyse_swing(make_payload(still=True))
    assert result["status"] == "no_swing_found"
    assert result["phases"] == [] and result["measurements"] == []
    assert result["notes"][0]["code"] == "no_swing_found"


def test_short_detection_gaps_are_bridged():
    result = analyse_swing(make_payload(drop_frames=set(range(70, 74))))
    assert result["status"] == "ok"
    assert phase_times(result)["impact"] == pytest.approx(IMPACT, abs=0.05)


def test_face_on_reports_face_on_measurements_only():
    names = measurements(analyse_swing(make_payload(camera_angle="face_on"))).keys()
    assert {"shoulder_tilt_address", "hip_shift_top", "head_shift_impact", "lead_arm_bend_top"} <= names
    assert not any(n.startswith("spine_angle") for n in names)


def test_broken_input_becomes_an_error_status_not_an_exception():
    result = analyse_swing({"format": "golfcoach.keypoints.v1", "frames": [{"t": 0, "lm": None}]})
    assert result["status"] == "error"
    assert result["notes"][0]["code"] == "analysis_error"


def test_result_is_json_serialisable():
    json.dumps(analyse_swing(make_payload()))


def test_savgol_keeps_quadratics_and_smooths_noise():
    x = np.arange(40, dtype=float)
    quad = 0.3 * x**2 - 2 * x + 5
    assert np.allclose(savgol(quad, 7, 2), quad)
    noisy = np.sin(x / 5) + np.random.default_rng(1).normal(0, 0.1, 40)
    assert np.std(savgol(noisy, 7, 2) - np.sin(x / 5)) < np.std(noisy - np.sin(x / 5))


def test_fill_gaps_only_bridges_short_interior_gaps():
    y = np.array([np.nan, 1.0, np.nan, np.nan, 4.0, np.nan, np.nan, np.nan, np.nan, 9.0, np.nan])
    out = fill_gaps(y, max_gap=3)
    assert np.isnan(out[0]) and np.isnan(out[-1])
    assert out[2:4].tolist() == [2.0, 3.0]
    assert np.isnan(out[5:9]).all()


# ---- feedback (rules engine) ------------------------------------------------------------------

from app.swing.feedback import build_feedback  # noqa: E402


def _m(name, value, confidence=1.0, phase="impact", unit="deg"):
    return {"name": name, "phase": phase, "frame_index": 10, "value": value, "unit": unit,
            "type": "measured", "confidence": confidence}


def _dtl(spine=38.0, knee=25.0, change=-2.0, hips=1.0, head_top=-3.0, head_imp=-4.0, conf=1.0):
    return [
        _m("spine_angle_address", spine, phase="address"),
        _m("trail_knee_flex_address", knee, phase="address"),
        _m("spine_angle_change_impact", change, conf),
        _m("rear_hip_toward_ball_impact", hips, conf, unit="% torso"),
        _m("head_rise_top", head_top, phase="top", unit="% torso"),
        _m("head_rise_impact", head_imp, conf, unit="% torso"),
    ]


def _kinds(fb):
    return {f["code"]: f["kind"] for f in fb["findings"]}


def test_good_down_the_line_swing_gets_strengths_only():
    fb = build_feedback(_dtl(), "down_the_line", [])
    assert set(_kinds(fb).values()) == {"strength"}
    assert {"good_setup_posture", "kept_posture", "steady_head"} <= _kinds(fb).keys()
    assert "No clear faults" in fb["summary"]


def test_clear_early_extension_is_the_main_thing_to_work_on():
    fb = build_feedback(_dtl(change=-20.0, hips=30.0), "down_the_line", [])
    assert fb["findings"][0]["code"] == "early_extension"
    assert fb["findings"][0]["kind"] == "improve"
    assert fb["findings"][0]["drill"] and fb["findings"][0]["why"]
    assert "main thing to work on" in fb["summary"]
    assert "20°" in fb["findings"][0]["detail"]


def test_uncertain_data_downgrades_faults_and_hides_praise():
    fb = build_feedback(_dtl(change=-20.0, hips=30.0, conf=0.3), "down_the_line", [])
    kinds = _kinds(fb)
    assert kinds["early_extension"] == "watch"  # clear fault, but on uncertain data
    assert "kept_posture" not in kinds
    assert "uncertain" in fb["summary"]


def test_mild_fault_is_worth_checking_not_a_fault():
    fb = build_feedback(_dtl(hips=18.0), "down_the_line", [])
    assert _kinds(fb)["early_extension"] == "watch"


def test_what_good_players_normally_do_is_not_a_fault():
    # 3D tour data: ~8 deg less forward bend, a few cm of pelvis toward the ball, head ~8 cm lower at impact.
    kinds = _kinds(build_feedback(_dtl(change=-8.0, hips=12.0, head_imp=-16.0), "down_the_line", []))
    assert set(kinds.values()) == {"strength"}


def test_setup_problems_are_reported_separately():
    kinds = _kinds(build_feedback(_dtl(spine=15.0, knee=5.0), "down_the_line", []))
    assert kinds["upright_setup"] == "improve" and kinds["straight_legs"] == "improve"
    assert "good_setup_posture" not in kinds


def test_face_on_rules_and_not_checked_list():
    ms = [
        _m("hip_shift_top", -20.0, phase="top", unit="% torso"),
        _m("head_shift_top", -5.0, phase="top", unit="% torso"),
        _m("hip_shift_impact", 12.0, unit="% torso"),
        _m("lead_arm_bend_top", 10.0, phase="top"),
        _m("stance_width_address", 1.2, phase="address", unit="ratio"),
    ]
    fb = build_feedback(ms, "face_on", [])
    kinds = _kinds(fb)
    assert kinds["sway"] == "improve" and kinds["good_weight_shift"] == "strength" and kinds["wide_backswing"] == "strength"
    assert "stance_width" not in kinds  # within range: no clutter
    assert any("down-the-line" in x for x in fb["not_checked"])


def test_tempo_and_slow_motion_note():
    assert _kinds(build_feedback([_m("tempo_ratio", 3.0, phase="top", unit="ratio")], "face_on", []))["good_tempo"] == "strength"
    assert _kinds(build_feedback([_m("tempo_ratio", 1.5, phase="top", unit="ratio")], "face_on", []))["quick_backswing"] == "watch"
    fb = build_feedback([], "down_the_line", [{"code": "slow_motion_suspected", "message": ""}])
    assert fb["findings"] == []
    assert any(x.startswith("Tempo") for x in fb["not_checked"])
    assert "not enough reliable data" in fb["summary"]


def test_feedback_text_never_contains_raw_placeholders():
    cases = (_dtl(), _dtl(change=-20.0, hips=30.0), _dtl(spine=60.0, knee=50.0, head_imp=-35.0), _dtl(head_top=20.0))
    for case in cases:
        fb = build_feedback(case, "down_the_line", [])
        texts = [fb["summary"], *fb["not_checked"]]
        for f in fb["findings"]:
            texts += [f["title"], f["detail"], f["why"] or "", f["drill"] or ""]
        for text in texts:
            for bad in ("None", "nan", "{", "}", "_"):
                assert bad not in text, (bad, text)


def test_analyse_swing_includes_feedback():
    result = analyse_swing(make_payload())
    assert result["version"] == "swing-0.3"
    assert result["feedback"]["summary"]
    assert analyse_swing(make_payload(still=True))["feedback"] is None


def test_stable_impact_values_are_not_penalised_for_30_fps():
    m = measurements(analyse_swing(make_payload(fps=30.0)))
    # The posture does not change around impact in this synthetic swing, so the exact impact frame does not matter.
    assert m["spine_angle_impact"]["confidence"] >= 0.9


def test_tour_swing_regression():
    """A tour professional's swing must be found correctly and must not get fault findings."""
    from pathlib import Path

    payload = json.loads((Path(__file__).parent / "fixtures" / "tour_swing_dtl_slowmo.json").read_text())
    result = analyse_swing(payload)
    assert result["status"] == "ok"
    frames = {p["name"]: p["frame_index"] for p in result["phases"]}
    # Checked by eye against the video frames.
    assert 20 <= frames["address"] <= 60
    assert 60 <= frames["takeaway"] <= 80
    assert 165 <= frames["top"] <= 185
    assert 224 <= frames["impact"] <= 234
    assert 300 <= frames["finish"] <= 320
    assert any(n["code"] == "slow_motion_suspected" for n in result["notes"])
    kinds = {f["code"]: f["kind"] for f in result["feedback"]["findings"]}
    assert "improve" not in kinds.values() and "watch" not in kinds.values(), kinds
    assert {"good_setup_posture", "kept_posture", "steady_head"} <= kinds.keys()
    impact = [m for m in result["measurements"] if m["phase"] == "impact"]
    assert impact and min(m["confidence"] for m in impact) >= 0.6
