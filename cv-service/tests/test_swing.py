"""Swing analysis on synthetic swings with known phase times."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.landmarks import LANDMARK_INDEX as I
from app.swing import analyse_swing
from app.swing.series import fill_gaps, find_spikes, mirror_permutation, savgol

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
    club_ground_x=None,
):
    """A down-the-line style golfer: torso bent toward +x (the ball side), hands in front of the hips.

    ``time_scale`` > 1 slows the motion down (a slow-motion clip saved at ``fps``).
    ``mirror_footage`` produces what a left-handed golfer's camera would record.
    ``club_ground_x``: add club detections; in the downswing the shaft line points at this x on
    the ground (normalised; the ball is at 0.75, the toes at 0.52).
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
        lm[I["left_foot_index"], :2] = (0.52, 0.90)
        lm[I["right_foot_index"], :2] = (0.52, 0.90)
        hx, hy = (0.55, 0.62) if still else hands_at(t_real)
        for w in ("left_wrist", "right_wrist"):
            lm[I[w], :2] = (hx, hy)
        if mirror_footage:
            lm[:, 0] = 1.0 - lm[:, 0]
            lm = lm[mirror_permutation()]
        frame = {"i": i, "t": round(t_video, 4), "n": 1, "lm": None if i in drop_frames else lm.tolist()}
        if club_ground_x is not None:
            frame["club"] = _club(hx, hy, t_real, club_ground_x, mirror_footage)
        frames.append(frame)
    return {
        "format": "golfcoach.keypoints.v1",
        "video": {"width": 720, "height": 1280, "fps": fps, "frame_count": n, "rotation_degrees": 0},
        "camera_angle": camera_angle,
        "handedness": handedness,
        "frames": frames,
    }


BALL = (0.75, 0.90)


def _club(hx, hy, t_real, ground_x, mirror):
    """Club boxes for one frame: grip at the hands; the shaft line points at a ground spot."""
    if t_real < ADDRESS_END:
        head = np.array(BALL)
    else:
        target = np.array([ground_x if TOP_END <= t_real < IMPACT else 0.68, BALL[1]])
        grip = np.array([hx, hy])
        d = (grip - target) * [720, 1280]
        d = d / np.linalg.norm(d) * 0.35 * 1280  # club length in px, pointing away from the ground spot
        head = grip + d / [720, 1280]
    pts = {"hands": (hx, hy), "head": tuple(head)}

    def box(cx, cy, r=0.01):
        return [cx - r, cy - r, cx + r, cy + r, 0.9]

    club = {k: box(*v) for k, v in pts.items()}
    club["shaft"] = [min(hx, head[0]), min(hy, head[1]), max(hx, head[0]), max(hy, head[1]), 0.9]
    if mirror:
        club = {k: [1 - b[2], b[1], 1 - b[0], b[3], b[4]] for k, b in club.items()}
    return club


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


def _move_wrists(payload, frames, xy, wrists=("left_wrist",), vis=0.7):
    for i in frames:
        for w in wrists:
            payload["frames"][i]["lm"][I[w]][:2] = list(xy)
            payload["frames"][i]["lm"][I[w]][3] = vis


def _assert_real_swing_phases(result):
    assert result["status"] == "ok", result["notes"]
    t = phase_times(result)
    assert t["top"] == pytest.approx(TOP_END, abs=0.05)
    assert t["impact"] == pytest.approx(IMPACT, abs=0.05)
    assert ADDRESS_END <= t["takeaway"] <= ADDRESS_END + 0.2


def test_wrist_glitch_at_address_is_not_taken_for_the_swing():
    # Seen on a real clip: for 3 frames at 60 fps the hidden lead wrist was put a quarter of the
    # frame away, with high visibility, then came back. Its snap back down was faster than the real
    # downswing, so the "top" ended up 0.02 s after the takeaway.
    # (Without the fix this gives takeaway 0.38 s, top 0.42 s, impact 0.48 s.)
    payload = make_payload()
    _move_wrists(payload, range(24, 27), (0.75, 0.15), vis=0.9)
    _assert_real_swing_phases(analyse_swing(payload))


def test_too_fast_backswing_is_not_a_swing():
    # Both hands jump up and back for 0.1 s: longer than the glitch filter's limit, but no real
    # backswing rises that fast, so the real swing later in the clip must still be found.
    payload = make_payload()
    _move_wrists(payload, range(20, 26), (0.45, 0.25), wrists=("left_wrist", "right_wrist"), vis=0.95)
    _assert_real_swing_phases(analyse_swing(payload))


def test_glitch_filter_keeps_a_fast_real_downswing():
    # 30 fps, hands 0.4 torso lengths per frame through impact (faster than a tour player), on an
    # arc with the radius of the arms (~1.2 torso lengths), seen straight on so the turn at the
    # bottom is as sharp as it gets in the image. Moving fast is not a glitch, only leaving and
    # coming straight back is.
    torso = 100.0
    radius, step = 1.2 * torso, 0.4 / 1.2
    angles = np.arange(-8, 9) * step
    p = np.stack([radius * np.sin(angles), radius * np.cos(angles)], axis=1)
    assert not find_spikes(p, 2, 0.25 * torso, 0.1 * torso).any()
    still = np.zeros((10, 2))
    still[4:6] = [40, -30]  # two frames half a torso away while standing still, then straight back
    assert find_spikes(still, 2, 0.25 * torso, 0.1 * torso).tolist() == [i in (4, 5) for i in range(10)]


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
    assert result["version"] == "swing-0.5"
    assert result["feedback"]["summary"]
    assert analyse_swing(make_payload(still=True))["feedback"] is None


def test_stable_impact_values_are_not_penalised_for_30_fps():
    m = measurements(analyse_swing(make_payload(fps=30.0)))
    # The posture does not change around impact in this synthetic swing, so the exact impact frame does not matter.
    assert m["spine_angle_impact"]["confidence"] >= 0.9


def test_tour_swing_regression():
    """A tour professional's swing must be found correctly and must not get fault findings."""
    from pathlib import Path

    payload = json.loads((Path(__file__).parent / "fixtures" / "tour_swing_dtl_slowmo_club.json").read_text())
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
    assert {"good_setup_posture", "kept_posture", "steady_head", "on_plane"} <= kinds.keys()
    assert result["club"]["tracked"] and result["club"]["found_share"]["shaft"] > 0.9
    impact = [m for m in result["measurements"] if m["phase"] == "impact"]
    assert impact and min(m["confidence"] for m in impact) >= 0.6



# ---- club ------------------------------------------------------------------------------------

def _club_result(**kw):
    result = analyse_swing(make_payload(**kw))
    return result, measurements(result), _kinds(result["feedback"])


def test_on_plane_downswing_is_a_strength():
    result, m, kinds = _club_result(club_ground_x=0.68)
    assert result["club"]["tracked"]
    # Ground spot 0.07 * 720 px inside the ball over a 256 px torso: about -20%.
    assert m["shaft_points_downswing"]["value"] == pytest.approx(-20, abs=6)
    assert kinds["on_plane"] == "strength"
    assert result["club"]["plane"]["from"] == pytest.approx(list(BALL), abs=0.02)


def test_steep_downswing_is_over_the_top():
    _, m, kinds = _club_result(club_ground_x=1.08)  # ~93% of a torso beyond the ball
    assert m["shaft_points_downswing"]["value"] > 80
    assert kinds["over_the_top"] == "improve"
    _, _, kinds = _club_result(club_ground_x=0.96)  # ~59%: mild
    assert kinds["over_the_top"] == "watch"


def test_shaft_pointing_inside_the_toes_is_inside_out():
    _, _, kinds = _club_result(club_ground_x=0.48)  # just inside the toes (0.52)
    assert kinds["inside_out"] == "watch"
    _, _, kinds = _club_result(club_ground_x=0.30)  # far inside the toes: about 60% of a torso
    assert kinds["inside_out"] == "improve"


def _club_feedback(shaft=None, path=None, toes=-60.0, confidence=0.8):
    from app.swing.feedback import build_feedback

    ms = []
    for name, value in (("shaft_points_downswing", shaft), ("hand_path_downswing", path)):
        if value is not None:
            ms.append({"name": name, "value": value, "confidence": confidence, "phase": "downswing",
                       "frame_index": 10, "unit": "% torso", "type": "measured"})
    fb = build_feedback(ms, "down_the_line", [], {"tracked": True, "toes_from_ball": toes})
    return {f["code"]: f["kind"] for f in fb["findings"]}


def test_hands_dropping_far_inside_is_inside_out():
    assert _club_feedback(path=-15.0) == {"inside_out": "watch"}
    assert _club_feedback(path=-25.0) == {"inside_out": "improve"}
    assert _club_feedback(path=-25.0, confidence=0.4) == {"inside_out": "watch"}  # uncertain: only worth checking
    assert _club_feedback(shaft=-130.0, path=-25.0)["inside_out"] == "improve"


def test_slightly_inside_is_good_not_inside_out():
    # A tour swing measured hand path 0 and shaft -21% (between the toes at -103% and the ball).
    assert _club_feedback(shaft=-21.0, path=0.0) == {"on_plane": "strength"}
    assert _club_feedback(path=-8.0) == {"on_plane": "strength"}  # shaft not measurable: hands decide


def test_shaft_a_little_beyond_the_ball_is_neither_praised_nor_a_fault():
    assert _club_feedback(shaft=10.0, path=-5.0) == {"on_plane": "strength"}
    assert _club_feedback(shaft=38.0, path=-7.0) == {}
    assert _club_feedback(shaft=45.0, path=-7.0) == {"over_the_top": "watch"}


def test_hands_alone_slightly_outside_gets_no_club_verdict():
    assert _club_feedback(path=6.0) == {}
    assert _club_feedback(path=15.0) == {"over_the_top": "watch"}


def _takeaway_frame(payload) -> int:
    return next(pp["frame_index"] for pp in analyse_swing(payload)["phases"] if pp["name"] == "takeaway")


def test_plane_starts_at_the_ball_even_when_the_club_rests_longer_at_the_top():
    # Seen on a slow-motion tour clip: only a few frames before the takeaway had club data, while
    # the club head sat still at the top for 25 frames. The plane must come from address.
    payload = make_payload(club_ground_x=0.68, time_scale=3.0)
    address_end = int(ADDRESS_END * 3.0 * FPS)  # the synthetic club head leaves the ball here
    for f in payload["frames"][: address_end - 8]:
        del f["club"]  # outside the club window: only 8 frames of the club at address
    plane = analyse_swing(payload)["club"]["plane"]
    assert plane is not None
    assert plane["from"] == pytest.approx(list(BALL), abs=0.02)


def test_plane_ignores_the_club_head_starting_back_before_the_hands():
    payload = make_payload(club_ground_x=0.68)
    takeaway = _takeaway_frame(payload)
    for i, k in enumerate(range(takeaway - 8, takeaway)):
        box = payload["frames"][k]["club"]["head"]
        shift = 0.015 * (i + 1)  # club head creeping back toward the golfer
        payload["frames"][k]["club"]["head"] = [box[0] - shift, box[1] - shift / 2, box[2] - shift, box[3] - shift / 2, box[4]]
    plane = analyse_swing(payload)["club"]["plane"]
    assert plane["from"] == pytest.approx(list(BALL), abs=0.02)


def test_no_believable_address_means_no_plane_and_no_plane_verdicts():
    payload = make_payload(club_ground_x=0.30)
    takeaway = _takeaway_frame(payload)
    for f in payload["frames"][: takeaway + 1]:
        del f["club"]
    result = analyse_swing(payload)
    assert result["club"]["tracked"] and result["club"]["plane"] is None
    names = {m["name"] for m in result["measurements"]}
    assert not names & {"shaft_points_downswing", "hand_path_downswing"}
    assert not {f["code"] for f in result["feedback"]["findings"]} & {"over_the_top", "inside_out", "on_plane"}

def test_club_results_are_mirrored_for_left_handed_golfers():
    right = _club_result(club_ground_x=1.08)[1]
    left = _club_result(club_ground_x=1.08, handedness="left", mirror_footage=True)
    assert left[1]["shaft_points_downswing"]["value"] == pytest.approx(right["shaft_points_downswing"]["value"], abs=0.5)
    # The plane line for display is in the ORIGINAL (unmirrored) image: the ball is on the left there.
    assert left[0]["club"]["plane"]["from"][0] == pytest.approx(1 - BALL[0], abs=0.02)


def test_without_club_data_the_club_is_reported_as_not_tracked():
    result = analyse_swing(make_payload())
    assert result["club"] == {"tracked": False}
    assert not any(m["name"].startswith("shaft") for m in result["measurements"])
    assert any("not tracked" in x for x in result["feedback"]["not_checked"])


# ---- measurement ratings (traffic lights) ---------------------------------------------------

def _rated(name, value, confidence=0.9, toes=None):
    from app.swing.ratings import rate_measurements

    m = [{"name": name, "value": value, "confidence": confidence}]
    rate_measurements(m, {"toes_from_ball": toes})
    return m[0]["rating"]


def test_ratings_use_the_feedback_limits():
    assert [_rated("spine_angle_address", v) for v in (38, 25, 18, 52, 60)] == ["good", "watch", "bad", "watch", "bad"]
    assert [_rated("hand_path_downswing", v) for v in (0, -15, -25, 15, 25)] == ["good", "watch", "bad", "watch", "bad"]
    assert [_rated("shaft_points_downswing", v, toes=-60) for v in (-20, 30, 90, -70, -110)] == [
        "good", "watch", "bad", "watch", "bad"]
    assert _rated("spine_angle_top", 35) is None  # without the address angle there is nothing to compare
    assert _rated("backswing_duration", 0.8) is None  # context only, no judgement


def test_spine_angle_at_top_and_impact_is_rated_against_address():
    from app.swing.ratings import rate_measurements

    ms = [{"name": "spine_angle_address", "value": 40.0, "confidence": 0.9}]
    ms += [{"name": "spine_angle_top", "value": v, "confidence": 0.9} for v in (39.0, 26.0, 20.0)]
    rate_measurements(ms)
    assert [m["rating"] for m in ms[1:]] == ["good", "watch", "bad"]
    assert "40" in ms[1]["typical"]


def test_uncertain_values_are_never_red_or_green():
    assert _rated("spine_angle_address", 18, confidence=0.3) == "watch"
    assert _rated("spine_angle_address", 38, confidence=0.3) is None


def test_ratings_agree_with_the_feedback():
    # Every measurement behind a finding is coloured like the finding: strength -> green,
    # fault -> yellow or red (never green), on the synthetic swings with every club verdict.
    colour = {"strength": {"good"}, "watch": {"watch", "bad"}, "improve": {"bad"}}
    for kw in ({}, {"club_ground_x": 0.68}, {"club_ground_x": 0.95}, {"club_ground_x": 0.30}, {"camera_angle": "face_on"}):
        result = analyse_swing(make_payload(**kw))
        rated = {m["name"]: m["rating"] for m in result["measurements"]}
        for f in result["feedback"]["findings"]:
            for name in f["measurements"]:
                assert rated[name] in colour[f["kind"]] | ({"watch"} if f["kind"] == "watch" else set()), (kw, f["code"], name, rated[name])
