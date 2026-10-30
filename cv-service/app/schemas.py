from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CameraAngle = Literal["face_on", "down_the_line"]
Handedness = Literal["right", "left"]
JobStatus = Literal["queued", "running", "completed", "failed"]


class JobRequest(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=64)
    # Both paths are relative to the shared data directory.
    video_path: str = Field(min_length=1)
    keypoints_path: str = Field(min_length=1)
    camera_angle: CameraAngle
    handedness: Handedness


class JobState(BaseModel):
    job_id: str
    analysis_id: str
    status: JobStatus
    progress: int = 0
    stage: str = "Queued"
    error: str | None = None
    result: dict[str, Any] | None = None


class AnalyzeRequest(BaseModel):
    # Relative to the shared data directory. Camera angle and handedness are read from the file.
    keypoints_path: str = Field(min_length=1)
