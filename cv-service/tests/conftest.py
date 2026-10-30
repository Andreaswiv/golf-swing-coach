"""Shared test helpers: a synthetic video writer and a fake PoseEstimator.

The fake estimator lets the whole pipeline (decode -> estimate -> raw JSON ->
quality report) run in CI without the MediaPipe model file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

# Make ``import app`` work when pytest is started from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pose.base import PoseDetection, PoseEstimator  # noqa: E402


def write_test_video(path: Path, frames: int = 30, fps: float = 30.0, size=(320, 240)) -> Path:
    """Write a small synthetic clip (moving rectangle on a grey background)."""
    w, h = size
    for fourcc_name, suffix in (("mp4v", ".mp4"), ("MJPG", ".avi")):
        target = path.with_suffix(suffix)
        writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*fourcc_name), fps, (w, h))
        if not writer.isOpened():
            continue
        for i in range(frames):
            frame = np.full((h, w, 3), 110, dtype=np.uint8)
            x = 20 + (i * 5) % (w - 80)
            cv2.rectangle(frame, (x, 60), (x + 40, 180), (200, 180, 40), -1)
            writer.write(frame)
        writer.release()
        if target.is_file() and target.stat().st_size > 0:
            return target
    pytest.skip("OpenCV in this environment cannot write test videos")


def make_landmarks(cx: float = 0.5, scale: float = 1.0, visibility: float = 0.95) -> np.ndarray:
    """A plausible-looking (33, 5) landmark array centred on ``cx``."""
    lm = np.zeros((33, 5), dtype=np.float32)
    rng = np.random.default_rng(0)
    lm[:, 0] = cx + (rng.random(33) - 0.5) * 0.2 * scale
    lm[:, 1] = 0.1 + rng.random(33) * 0.8 * scale
    lm[:, 3] = visibility
    lm[:, 4] = visibility
    return lm


class FakeEstimator(PoseEstimator):
    """Deterministic estimator driven by a per-frame plan.

    ``plan(i)`` returns a list of landmark arrays (one per person) for frame ``i``.
    """

    name = "fake-estimator"

    def __init__(self, plan=None) -> None:
        self.plan = plan or (lambda i: [make_landmarks(cx=0.3 + 0.01 * i)])
        self.calls: list[int] = []
        self.closed = False

    def estimate(self, frame_bgr, timestamp_ms):
        i = len(self.calls)
        self.calls.append(timestamp_ms)
        return [PoseDetection(landmarks=lm) for lm in self.plan(i)]

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_estimator() -> FakeEstimator:
    return FakeEstimator()


@pytest.fixture
def video_path(tmp_path: Path) -> Path:
    return write_test_video(tmp_path / "swing")
