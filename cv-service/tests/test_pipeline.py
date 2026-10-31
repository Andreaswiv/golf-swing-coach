from __future__ import annotations

import json

import numpy as np
import pytest

from app.landmarks import LANDMARK_NAMES
from app.pipeline import (
    KEYPOINTS_FORMAT,
    _frame_timestamps_seconds,
    run_pipeline,
    select_golfer,
)
from app.pose.base import PoseDetection
from app.video import VideoError, probe_video

from .conftest import FakeEstimator, make_landmarks, write_test_video


def test_probe_video_reports_metadata(video_path):
    meta = probe_video(video_path)
    assert (meta.width, meta.height) == (320, 240)
    assert meta.fps == pytest.approx(30.0, abs=0.5)
    assert meta.orientation == "landscape"
    assert meta.declared_frame_count == pytest.approx(30, abs=2)


def test_probe_video_missing_file(tmp_path):
    with pytest.raises(VideoError):
        probe_video(tmp_path / "nope.mp4")


def test_probe_video_garbage_file(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"this is not a video")
    with pytest.raises(VideoError):
        probe_video(bad)


def test_pipeline_writes_raw_keypoints(video_path, tmp_path, fake_estimator):
    out = tmp_path / "keypoints" / "a1.json"
    progress: list[int] = []

    result = run_pipeline(
        video_path,
        out,
        fake_estimator,
        camera_angle="face_on",
        handedness="left",
        on_progress=lambda pct, _stage: progress.append(pct),
    )

    payload = json.loads(out.read_text())
    assert payload["format"] == KEYPOINTS_FORMAT
    assert payload["landmark_names"] == LANDMARK_NAMES
    assert payload["camera_angle"] == "face_on"
    # Raw data: left-handed footage is stored un-mirrored.
    assert payload["handedness"] == "left"
    assert payload["video"]["frame_count"] == result.frame_count == len(payload["frames"])

    first = payload["frames"][0]
    assert list(first.keys()) == ["i", "t", "n", "lm"]
    assert np.asarray(first["lm"]).shape == (33, 5)
    times = [f["t"] for f in payload["frames"]]
    assert times == sorted(times) and times[0] == 0.0

    assert progress == sorted(progress)
    assert max(progress) <= 99  # 100 is reserved for the job manager's "completed"
    assert fake_estimator.calls == sorted(set(fake_estimator.calls))  # strictly increasing


def test_pipeline_handles_frames_without_pose(video_path, tmp_path):
    estimator = FakeEstimator(plan=lambda i: [])
    out = tmp_path / "k.json"
    result = run_pipeline(video_path, out, estimator, "down_the_line", "right")

    payload = json.loads(out.read_text())
    assert all(f["lm"] is None and f["n"] == 0 for f in payload["frames"])
    assert result.quality.overall == "poor"
    assert any(w.code == "pose_not_detected" for w in result.quality.warnings)


def test_pipeline_rejects_unreadable_video(tmp_path, fake_estimator):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(VideoError):
        run_pipeline(bad, tmp_path / "k.json", fake_estimator, "face_on", "right")
    assert not (tmp_path / "k.json").exists()


def test_select_golfer_prefers_largest_person():
    small = PoseDetection(make_landmarks(cx=0.8, scale=0.3))
    large = PoseDetection(make_landmarks(cx=0.4, scale=1.0))
    assert select_golfer([small, large]) is large
    assert select_golfer([]) is None
    assert select_golfer([small]) is small


def test_timestamps_fall_back_when_container_times_unusable():
    assert _frame_timestamps_seconds([0, 0, 0, 0], 50.0) == pytest.approx([0, 0.02, 0.04, 0.06])
    good = _frame_timestamps_seconds([100.0, 120.0, 150.0], 30.0)
    assert good == pytest.approx([0.0, 0.02, 0.05])  # variable frame rate is preserved


def test_pipeline_flags_multiple_people(tmp_path):
    video = write_test_video(tmp_path / "multi")
    estimator = FakeEstimator(plan=lambda i: [make_landmarks(0.3), make_landmarks(0.7, scale=0.5)])
    result = run_pipeline(video, tmp_path / "k.json", estimator, "face_on", "right")
    assert any(w.code == "multiple_people" for w in result.quality.warnings)


def test_pipeline_rejects_videos_longer_than_15_seconds(tmp_path, fake_estimator):
    video = write_test_video(tmp_path / "long", frames=16 * 5, fps=5.0)  # 16 s
    with pytest.raises(VideoError, match="16.0 seconds long. The limit is 15 seconds"):
        run_pipeline(video, tmp_path / "k.json", fake_estimator, "down_the_line", "right")
    assert not (tmp_path / "k.json").exists()


def test_pipeline_accepts_a_15_second_video(tmp_path, fake_estimator):
    video = write_test_video(tmp_path / "ok", frames=15 * 5, fps=5.0)
    run_pipeline(video, tmp_path / "k.json", fake_estimator, "down_the_line", "right")
