"""Club detection plumbing: ONNX output decoding, the pipeline and the job manager."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.club.detector import Box, ClubDetector, OnnxClubDetector
from app.jobs import JobManager
from app.pipeline import run_pipeline
from app.schemas import JobRequest

from .conftest import FakeEstimator, write_test_video
from .test_jobs_and_config import make_settings, wait_for


class FakeClubDetector(ClubDetector):
    name = "fake-club"

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def detect(self, frame_bgr):
        self.calls += 1
        return {"shaft": Box(0.4, 0.5, 0.6, 0.9, 0.8), "hands": Box(0.45, 0.5, 0.5, 0.55, 0.9)}

    def close(self) -> None:
        self.closed = True


def _decoder() -> OnnxClubDetector:
    det = OnnxClubDetector.__new__(OnnxClubDetector)  # decoding needs no model file
    det.size, det.min_conf = 640, 0.35
    return det


def test_decode_undoes_the_letterbox_and_keeps_the_best_box_per_part():
    det = _decoder()
    # A 1280x720 portrait frame: scale 0.5, letterboxed with 140 px grey bars left and right.
    blob, scale, left, top = det.preprocess(np.zeros((1280, 720, 3), np.uint8))
    assert blob.shape == (1, 3, 640, 640)
    assert (scale, left, top) == (0.5, 140, 0)

    out = np.zeros((1, 7, 3), np.float32)
    out[0, :4, 0] = (320, 320, 100, 200)  # shaft, weak
    out[0, :4, 1] = (320, 320, 40, 40)  # shaft, best
    out[0, 4, :2] = (0.5, 0.9)
    out[0, 5, 2] = 0.2  # head below the confidence threshold
    out[0, 6, 2] = 0.7  # hands
    out[0, :4, 2] = (140, 100, 40, 20)  # half in the left grey bar
    found = det.decode(out, scale, left, top, 720, 1280)

    assert set(found) == {"shaft", "hands"}
    shaft = found["shaft"]
    assert shaft.conf == np.float32(0.9)
    # Centre (320, 320) in input pixels -> (360, 640) in the frame -> (0.5, 0.5).
    assert np.allclose([shaft.x1, shaft.y1, shaft.x2, shaft.y2], [0.4444, 0.4688, 0.5556, 0.5312], atol=1e-3)
    # Boxes reaching into the grey bars are clipped to the frame.
    assert found["hands"].x1 == 0.0


def test_pipeline_stores_club_boxes_per_frame(video_path, tmp_path, fake_estimator):
    club = FakeClubDetector()
    out = tmp_path / "k.json"
    result = run_pipeline(video_path, out, fake_estimator, "down_the_line", "right", club_detector=club)

    payload = json.loads(out.read_text())
    assert payload["club_model"] == "fake-club"
    assert club.calls == result.frame_count
    first = payload["frames"][0]
    assert list(first.keys()) == ["i", "t", "n", "lm", "club"]
    assert first["club"]["shaft"] == [0.4, 0.5, 0.6, 0.9, 0.8]
    assert "head" not in first["club"]


def test_pipeline_without_club_detector_has_no_club_data(video_path, tmp_path, fake_estimator):
    run_pipeline(video_path, tmp_path / "k.json", fake_estimator, "down_the_line", "right")
    payload = json.loads((tmp_path / "k.json").read_text())
    assert payload["club_model"] is None
    assert "club" not in payload["frames"][0]


def _submit(manager: JobManager, video) -> object:
    state = manager.submit(
        JobRequest(
            analysis_id="a1",
            video_path=f"videos/{video.name}",
            keypoints_path="keypoints/a1.json",
            camera_angle="down_the_line",
            handedness="right",
        )
    )
    return wait_for(manager, state.job_id)


def test_job_uses_and_closes_the_club_detector(tmp_path):
    (tmp_path / "videos").mkdir()
    video = write_test_video(tmp_path / "videos" / "v1")
    club = FakeClubDetector()
    manager = JobManager(make_settings(tmp_path), FakeEstimator, lambda: club)
    try:
        done = _submit(manager, video)
    finally:
        manager.shutdown()
    assert done.status == "completed", done.error
    assert club.calls > 0 and club.closed


def test_job_completes_without_club_tracking_when_the_club_model_fails(tmp_path):
    (tmp_path / "videos").mkdir()
    video = write_test_video(tmp_path / "videos" / "v1")

    def broken():
        raise FileNotFoundError("Club model not found")

    manager = JobManager(make_settings(tmp_path), FakeEstimator, broken)
    try:
        done = _submit(manager, video)
    finally:
        manager.shutdown()
    assert done.status == "completed", done.error
    payload = json.loads((tmp_path / "keypoints" / "a1.json").read_text())
    assert payload["club_model"] is None


# ---- club detection only around the swing ------------------------------------------------------

PAD_S = 1.5  # still at address before the synthetic swing, so the club window starts after frame 0


def _padded_swing(fps: float, **kw) -> dict:
    """The synthetic swing from test_swing, with PAD_S more of standing at address first."""
    from .test_swing import make_payload

    payload = make_payload(fps=fps, **kw)
    pad = int(PAD_S * fps)
    frames = [json.loads(json.dumps(payload["frames"][0])) for _ in range(pad)] + payload["frames"]
    for i, f in enumerate(frames):
        f["i"], f["t"] = i, round(i / fps, 4)
    payload["frames"] = frames
    return payload


def _swing_estimator(fps: float):
    """Estimator that replays the padded synthetic swing frame by frame."""
    frames = _padded_swing(fps)["frames"]
    return FakeEstimator(plan=lambda i: [np.array(frames[min(i, len(frames) - 1)]["lm"])]), len(frames)


def test_club_frame_range_covers_address_to_finish_only():
    from types import SimpleNamespace

    from app.pipeline import CLUB_LEAD_S, CLUB_TAIL_S, club_frame_range

    from .test_swing import ADDRESS_END, FINISH

    payload = _padded_swing(30.0)
    meta = SimpleNamespace(width=720, height=1280, fps=30.0)
    first, last = club_frame_range(payload["frames"], meta, "down_the_line", "right")
    t = [f["t"] - PAD_S for f in payload["frames"]]  # swing time, as in test_swing
    # Takeaway is a little after ADDRESS_END, the finish a little before FINISH (see test_swing).
    assert ADDRESS_END - CLUB_LEAD_S - 0.05 <= t[first] <= ADDRESS_END + 0.2 - CLUB_LEAD_S
    assert FINISH - 0.15 + CLUB_TAIL_S - 0.05 <= t[last] <= FINISH + CLUB_TAIL_S + 0.05
    assert first > 0 and last < len(t) - 1  # the waiting before and the still frames after are skipped


def test_club_frame_range_is_every_frame_when_no_swing_is_found():
    from types import SimpleNamespace

    from app.pipeline import club_frame_range

    from .test_swing import make_payload

    payload = make_payload(fps=30.0, still=True)
    meta = SimpleNamespace(width=720, height=1280, fps=30.0)
    assert club_frame_range(payload["frames"], meta, "down_the_line", "right") == (0, len(payload["frames"]) - 1)


def test_pipeline_runs_the_club_detector_only_around_the_swing(tmp_path):
    estimator, n = _swing_estimator(30.0)
    video = write_test_video(tmp_path / "swing", frames=n, fps=30.0)
    club = FakeClubDetector()
    out = tmp_path / "k.json"
    stages = []
    result = run_pipeline(video, out, estimator, "down_the_line", "right", club_detector=club,
                          on_progress=lambda pct, stage: stages.append((pct, stage)))

    payload = json.loads(out.read_text())
    first, last = payload["club_frames"]
    assert 0 < first < last < result.frame_count - 1
    assert club.calls == last - first + 1
    checked = [k for k, f in enumerate(payload["frames"]) if "club" in f]
    assert checked == list(range(first, last + 1))
    assert list(payload["frames"][first].keys()) == ["i", "t", "n", "lm", "club"]
    # Progress never goes backwards, and the club pass reports its own stage.
    assert [p for p, _ in stages] == sorted(p for p, _ in stages)
    assert "Tracking the club" in {s for _, s in stages}


def test_club_shares_count_only_the_checked_frames():
    from app.swing import analyse_swing

    from .test_swing import make_payload

    payload = make_payload(club_ground_x=0.68)
    frames = payload["frames"]
    keep = range(20, len(frames) - 20)  # as if only the frames around the swing were checked
    for k, f in enumerate(frames):
        if k not in keep:
            del f["club"]
    result = analyse_swing(payload)
    club = result["club"]
    assert club["found_share"]["shaft"] == 1.0
    assert (club["frames_checked"], club["frames_total"]) == (len(keep), len(frames))
    assert club["plane"] is not None
    assert any(m["name"] == "shaft_points_downswing" for m in result["measurements"])


# ---- physically impossible detections -------------------------------------------------------

def test_shaft_box_away_from_the_hands_is_ignored():
    # Seen on a real clip: power lines in the sky detected as the shaft while the club head was not
    # found, which made the drawn club reach across the frame.
    from app.swing import analyse_swing

    from .test_swing import make_payload

    payload = make_payload(club_ground_x=0.68)
    frames = payload["frames"]
    bad = range(100, 104)
    for k in bad:
        frames[k]["club"].pop("head")
        frames[k]["club"]["shaft"] = [0.75, 0.05, 0.98, 0.2, 0.7]  # a line in the sky, far from the hands
    result = analyse_swing(payload)
    track = result["club"]["track"]
    assert result["club"]["rejected_frames"] == len(bad)
    for k in bad:
        # No club drawn there (or a short interpolation between good frames), never into the sky.
        assert track[k] is None or track[k][2] < 0.75
    assert result["club"]["plane"] is not None


def test_club_head_further_away_than_the_club_is_long_is_ignored():
    from app.swing import analyse_swing

    from .test_swing import make_payload

    payload = make_payload(club_ground_x=0.68)
    k = 100
    payload["frames"][k]["club"]["head"] = [0.96, 0.96, 0.98, 0.98, 0.9]  # bottom corner: ~3.7 torso from the hands
    payload["frames"][k]["club"].pop("shaft")
    result = analyse_swing(payload)
    assert result["club"]["rejected_frames"] == 1
    t = result["club"]["track"][k]
    assert t is None or (t[2] < 0.9 and t[3] < 0.9)


def test_track_is_in_original_coordinates_for_left_handed_golfers():
    from app.swing import analyse_swing

    from .test_swing import make_payload

    right = analyse_swing(make_payload(club_ground_x=0.68))["club"]["track"]
    left = analyse_swing(make_payload(club_ground_x=0.68, handedness="left", mirror_footage=True))["club"]["track"]
    k = next(i for i, t in enumerate(right) if t)
    assert left[k][0] == pytest.approx(1 - right[k][0], abs=0.002)
    assert left[k][3] == pytest.approx(right[k][3], abs=0.002)


def test_overlong_limb_drops_the_joint_and_is_reported():
    # The wrist 'flies off' for 10 frames (too long for the glitch filter): the forearm would be
    # three times its length, which a real arm cannot look like on video.
    from app.swing import analyse_swing
    from app.landmarks import LANDMARK_INDEX as I

    from .test_swing import make_payload

    payload = make_payload()
    for k in range(10, 20):
        payload["frames"][k]["lm"][I["left_wrist"]][:2] = [0.95, 0.10]
    result = analyse_swing(payload)
    assert result["status"] == "ok"
    assert set(range(10, 20)) <= set(result["rejected_landmarks"]["left_wrist"])
    assert "right_wrist" not in result["rejected_landmarks"]
