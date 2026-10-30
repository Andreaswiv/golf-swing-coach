"""In-process job manager.

Jobs run one at a time on a single worker thread (pose estimation is CPU
bound; running several videos in parallel would just make all of them slower).
State is held in memory: if the CV service restarts, the API re-submits any
analysis that did not finish. This is intentionally simple for the MVP; there
is no Redis / RabbitMQ.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import PIPELINE_VERSION
from .config import Settings
from .pipeline import run_pipeline
from .pose.base import PoseEstimator
from .schemas import JobRequest, JobState
from .club.detector import ClubDetector
from .video import VideoError

log = logging.getLogger("cv.jobs")

EstimatorFactory = Callable[[], PoseEstimator]
ClubDetectorFactory = Callable[[], "ClubDetector"]
MAX_REMEMBERED_JOBS = 200


class JobManager:
    def __init__(
        self,
        settings: Settings,
        estimator_factory: EstimatorFactory,
        club_factory: ClubDetectorFactory | None = None,
    ) -> None:
        self._settings = settings
        self._factory = estimator_factory
        self._club_factory = club_factory
        self._jobs: "OrderedDict[str, JobState]" = OrderedDict()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cv-job")

    # ------------------------------------------------------------------ API
    def submit(self, request: JobRequest) -> JobState:
        # Validate paths up front so bad requests fail fast with a clear error.
        video_abs = self._settings.resolve_data_path(request.video_path)
        keypoints_abs = self._settings.resolve_data_path(request.keypoints_path)

        job_id = uuid.uuid4().hex
        state = JobState(job_id=job_id, analysis_id=request.analysis_id, status="queued")
        with self._lock:
            self._jobs[job_id] = state
            while len(self._jobs) > MAX_REMEMBERED_JOBS:
                self._jobs.popitem(last=False)
        self._executor.submit(self._run, job_id, request, video_abs, keypoints_abs)
        return state.model_copy()

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            state = self._jobs.get(job_id)
            return state.model_copy() if state else None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------- internals
    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if state is not None:
                for key, value in changes.items():
                    setattr(state, key, value)

    def _create_club_detector(self) -> ClubDetector | None:
        """Club detection is optional: a missing or broken model must not fail the analysis."""
        if self._club_factory is None:
            return None
        try:
            return self._club_factory()
        except Exception:  # noqa: BLE001
            log.exception("Club detector could not be loaded; continuing without club tracking")
            return None

    def _run(self, job_id: str, request: JobRequest, video_abs, keypoints_abs) -> None:
        self._update(job_id, status="running", progress=1, stage="Starting")
        try:
            club = self._create_club_detector()
            with self._factory() as estimator:
                output = run_pipeline(
                    video_path=video_abs,
                    keypoints_path=keypoints_abs,
                    estimator=estimator,
                    camera_angle=request.camera_angle,
                    handedness=request.handedness,
                    on_progress=lambda pct, stage: self._update(
                        job_id, progress=pct, stage=stage
                    ),
                    max_process_dim=self._settings.max_process_dim,
                    club_detector=club,
                )
            if club is not None:
                club.close()
            result = {
                "pipeline_version": PIPELINE_VERSION,
                "pose_model": output.pose_model,
                "video": output.video.to_dict(),
                "keypoints": {
                    "path": request.keypoints_path,
                    "frame_count": output.frame_count,
                    "data_format": "golfcoach.keypoints.v1",
                },
                "quality": output.quality.to_dict(),
                "swing": output.swing,
            }
            self._update(job_id, status="completed", progress=100, stage="Completed", result=result)
        except VideoError as exc:
            log.warning("Job %s failed: %s", job_id, exc)
            self._update(job_id, status="failed", stage="Failed", error=str(exc))
        except FileNotFoundError as exc:
            log.error("Job %s failed: %s", job_id, exc)
            self._update(job_id, status="failed", stage="Failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - surface any failure to the API
            log.exception("Job %s crashed", job_id)
            self._update(
                job_id,
                status="failed",
                stage="Failed",
                error=f"Unexpected processing error: {type(exc).__name__}: {exc}",
            )
