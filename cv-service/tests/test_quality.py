from __future__ import annotations

import numpy as np
import pytest

from app.quality import (
    FrameObservation,
    assess_quality,
    temporal_resolution_factor,
)
from app.video import VideoMetadata

from .conftest import make_landmarks


def _meta(fps: float = 120.0, width: int = 1920, height: int = 1080) -> VideoMetadata:
    return VideoMetadata(
        width=width,
        height=height,
        fps=fps,
        declared_frame_count=100,
        duration_seconds=100 / fps,
        orientation="landscape",
        rotation_degrees=0,
        codec="avc1",
    )


def _obs(n: int = 100, **kw) -> list[FrameObservation]:
    return [FrameObservation(n_poses=1, landmarks=make_landmarks(**kw)) for _ in range(n)]


GOOD_LIGHT = [(120.0, 50.0)] * 5


def codes(report) -> set[str]:
    return {w.code for w in report.warnings}


def test_good_footage_has_no_warnings():
    report = assess_quality(_meta(), _obs(), GOOD_LIGHT)
    assert report.overall == "good"
    assert report.warnings == []
    # Unimplemented checks must be listed so the UI never implies they passed.
    assert set(report.checks_not_run) == {"camera_motion", "camera_angle_match"}


def test_low_fps_warns_but_does_not_reject():
    report = assess_quality(_meta(fps=30), _obs(), GOOD_LIGHT)
    assert "low_fps" in codes(report)
    assert report.stats["temporal_resolution_factor"] < 1.0
    assert report.overall == "warning"


@pytest.mark.parametrize("fps", [59.6, 59.94, 59.969, 60.0])
def test_phone_rates_around_60_fps_count_as_60(fps):
    assert "low_fps" not in codes(assess_quality(_meta(fps=fps), _obs(), GOOD_LIGHT))
    assert temporal_resolution_factor(fps) == 0.9


def test_a_rate_clearly_below_60_still_warns():
    assert "low_fps" in codes(assess_quality(_meta(fps=50), _obs(), GOOD_LIGHT))


def test_very_low_fps_is_high_severity():
    report = assess_quality(_meta(fps=24), _obs(), GOOD_LIGHT)
    assert report.overall == "poor"


def test_temporal_resolution_factor_is_monotonic():
    values = [temporal_resolution_factor(f) for f in (15, 30, 60, 120, 240)]
    assert values == sorted(values)
    assert values[-1] == 1.0


def test_dark_and_flat_footage_warn_about_lighting():
    assert "poor_lighting" in codes(assess_quality(_meta(), _obs(), [(30.0, 40.0)] * 5))
    assert "poor_lighting" in codes(assess_quality(_meta(), _obs(), [(240.0, 40.0)] * 5))


def test_low_visibility_joints_are_reported():
    report = assess_quality(_meta(), _obs(visibility=0.2), GOOD_LIGHT)
    assert "joints_low_visibility" in codes(report)


def test_golfer_leaving_frame_is_reported():
    lm = make_landmarks()
    lm[0, 1] = -0.2  # nose above the frame
    obs = [FrameObservation(1, lm.copy()) for _ in range(100)]
    assert "golfer_not_fully_visible" in codes(assess_quality(_meta(), obs, GOOD_LIGHT))


def test_missing_poses_are_reported():
    obs = _obs(40) + [FrameObservation(0, None) for _ in range(60)]
    report = assess_quality(_meta(), obs, GOOD_LIGHT)
    assert report.stats["pose_detection_rate"] == 0.4
    assert report.overall == "poor"


def test_report_is_json_serialisable():
    import json

    report = assess_quality(_meta(fps=30), _obs(), GOOD_LIGHT)
    json.dumps(report.to_dict())
    assert isinstance(np.float32(1.0).item(), float)
