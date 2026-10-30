from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.jobs import JobManager
from app.schemas import JobRequest

from .conftest import FakeEstimator, write_test_video


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=data_dir.resolve(),
        pose_model_path=data_dir / "model.task",
        max_process_dim=640,
        num_poses=2,
    )


def wait_for(manager: JobManager, job_id: str, timeout: float = 30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = manager.get(job_id)
        if state and state.status in ("completed", "failed"):
            return state
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_resolve_data_path_blocks_traversal(tmp_path):
    settings = make_settings(tmp_path)
    assert settings.resolve_data_path("videos/a.mp4") == tmp_path.resolve() / "videos" / "a.mp4"
    for evil in ("../etc/passwd", "videos/../../x", "/etc/passwd"):
        with pytest.raises(ValueError):
            settings.resolve_data_path(evil)


def test_job_completes_and_reports_result(tmp_path):
    (tmp_path / "videos").mkdir()
    video = write_test_video(tmp_path / "videos" / "v1")
    estimator = FakeEstimator()
    manager = JobManager(make_settings(tmp_path), lambda: estimator)
    try:
        state = manager.submit(
            JobRequest(
                analysis_id="a1",
                video_path=f"videos/{video.name}",
                keypoints_path="keypoints/a1.json",
                camera_angle="face_on",
                handedness="right",
            )
        )
        # The worker thread may already have picked the job up by the time we look.
        assert state.status in ("queued", "running")
        done = wait_for(manager, state.job_id)
    finally:
        manager.shutdown()

    assert done.status == "completed", done.error
    assert done.progress == 100
    assert done.result["keypoints"]["path"] == "keypoints/a1.json"
    assert done.result["video"]["width"] == 320
    assert done.result["quality"]["overall"] in {"good", "warning", "poor"}
    assert (tmp_path / "keypoints" / "a1.json").is_file()
    assert estimator.closed  # model resources are released after every job


def test_job_fails_cleanly_for_unreadable_video(tmp_path):
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "bad.mp4").write_bytes(b"nope")
    manager = JobManager(make_settings(tmp_path), FakeEstimator)
    try:
        state = manager.submit(
            JobRequest(
                analysis_id="a2",
                video_path="videos/bad.mp4",
                keypoints_path="keypoints/a2.json",
                camera_angle="down_the_line",
                handedness="left",
            )
        )
        done = wait_for(manager, state.job_id)
    finally:
        manager.shutdown()
    assert done.status == "failed"
    assert done.error


def test_job_fails_cleanly_when_estimator_cannot_load(tmp_path):
    (tmp_path / "videos").mkdir()
    write_test_video(tmp_path / "videos" / "v3")
    video_name = next((tmp_path / "videos").glob("v3.*")).name

    def broken_factory():
        raise FileNotFoundError("Pose model not found")

    manager = JobManager(make_settings(tmp_path), broken_factory)
    try:
        state = manager.submit(
            JobRequest(
                analysis_id="a3",
                video_path=f"videos/{video_name}",
                keypoints_path="keypoints/a3.json",
                camera_angle="face_on",
                handedness="right",
            )
        )
        done = wait_for(manager, state.job_id)
    finally:
        manager.shutdown()
    assert done.status == "failed"
    assert "Pose model" in done.error


def test_submit_rejects_paths_outside_data_dir(tmp_path):
    manager = JobManager(make_settings(tmp_path), FakeEstimator)
    try:
        with pytest.raises(ValueError):
            manager.submit(
                JobRequest(
                    analysis_id="a4",
                    video_path="../outside.mp4",
                    keypoints_path="keypoints/a4.json",
                    camera_angle="face_on",
                    handedness="right",
                )
            )
    finally:
        manager.shutdown()


def test_unknown_job_returns_none(tmp_path):
    manager = JobManager(make_settings(tmp_path), FakeEstimator)
    try:
        assert manager.get("does-not-exist") is None
    finally:
        manager.shutdown()
        shutil.rmtree(tmp_path, ignore_errors=True)
