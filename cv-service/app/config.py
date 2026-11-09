"""Runtime configuration for the CV service, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Root folder shared with the ASP.NET Core API. All video / keypoint paths
    # exchanged between the services are relative to this folder.
    data_dir: Path
    # MediaPipe PoseLandmarker model file (.task). Downloaded at image build time.
    pose_model_path: Path
    # Frames larger than this (longest side, px) are downscaled before pose
    # estimation. Pose output is normalised, so this only affects speed.
    max_process_dim: int
    # How many people the pose model may return per frame (used to detect
    # "multiple people" situations).
    num_poses: int
    # Club detection (shaft, head, hands): ONNX model built into the image. Optional:
    # without it the analysis runs as before and says the club was not tracked.
    club_model_path: Path = Path("/app/models/club_swingtrace_yolo11m_quant.onnx")
    club_detection: bool = True
    # Inference threads for the club model; 0 = let ONNX Runtime decide.
    club_threads: int = 0

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            data_dir=Path(os.environ.get("DATA_DIR", "/data")).resolve(),
            pose_model_path=Path(
                os.environ.get("POSE_MODEL_PATH", "/app/models/pose_landmarker_full.task")
            ),
            max_process_dim=int(os.environ.get("MAX_PROCESS_DIM", "1280")),
            num_poses=int(os.environ.get("NUM_POSES", "2")),
            club_model_path=Path(os.environ.get("CLUB_MODEL_PATH", "/app/models/club_swingtrace_yolo11m_quant.onnx")),
            club_detection=os.environ.get("CLUB_DETECTION", "1").lower() not in ("0", "false", "no", "off"),
            club_threads=int(os.environ.get("CLUB_THREADS", "0")),
        )

    def resolve_data_path(self, relative: str) -> Path:
        """Resolve a path received from the API, refusing anything outside data_dir."""
        candidate = (self.data_dir / relative).resolve()
        if self.data_dir != candidate and self.data_dir not in candidate.parents:
            raise ValueError(f"Path escapes the data directory: {relative!r}")
        return candidate
