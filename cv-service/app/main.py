"""FastAPI entry point for the computer-vision service."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import PIPELINE_VERSION
from .config import Settings
from .jobs import JobManager
from .pose.base import PoseEstimator
from .schemas import AnalyzeRequest, JobRequest, JobState
from .swing import analyse_swing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = Settings.from_env()


def _create_estimator() -> PoseEstimator:
    from .pose.mediapipe_estimator import MediaPipePoseEstimator

    return MediaPipePoseEstimator(settings.pose_model_path, num_poses=settings.num_poses)


jobs = JobManager(settings, _create_estimator)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    jobs.shutdown()


app = FastAPI(title="GolfCoach CV Service", version=PIPELINE_VERSION, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    model_present = settings.pose_model_path.is_file()
    return {
        "status": "ok" if model_present and settings.data_dir.is_dir() else "degraded",
        "pipeline_version": PIPELINE_VERSION,
        "pose_model_present": model_present,
        "data_dir_present": settings.data_dir.is_dir(),
    }


@app.post("/jobs", response_model=JobState, status_code=202)
def create_job(request: JobRequest) -> JobState:
    try:
        return jobs.submit(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs/{job_id}", response_model=JobState)
def get_job(job_id: str) -> JobState:
    state = jobs.get(job_id)
    if state is None:
        # Happens after a service restart; the API re-submits in that case.
        raise HTTPException(status_code=404, detail="Unknown job")
    return state


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    """Re-run the swing analysis on an existing keypoints file (fast; no pose model needed)."""
    try:
        path = settings.resolve_data_path(request.keypoints_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Keypoints file not found.")
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if payload.get("format") != "golfcoach.keypoints.v1":
        raise HTTPException(status_code=400, detail=f"Unsupported keypoints format: {payload.get('format')}")
    return analyse_swing(payload)
