"""MediaPipe PoseLandmarker (Tasks API) implementation of ``PoseEstimator``.

Recent MediaPipe releases no longer ship the legacy ``mp.solutions.pose`` API;
the supported route is the Tasks API, which needs a separate ``.task`` model
file (downloaded when the Docker image is built).

Runs on CPU (XNNPACK), which works on Apple Silicon / ARM64 Linux without any
GPU assumptions.

NOTE: this class could not be exercised against a real model in the
environment where it was written. See DEVELOPMENT_STATUS.md.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .base import PoseDetection, PoseEstimator


class MediaPipePoseEstimator(PoseEstimator):
    def __init__(
        self,
        model_path: Path,
        num_poses: int = 2,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Pose model not found at {model_path}. Build the cv-service image "
                "(it downloads the model) or run scripts/download_pose_model.sh."
            )

        # Imported lazily so the rest of the service (and unit tests that use a
        # fake estimator) work without MediaPipe being importable.
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=num_poses,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_segmentation_masks=False,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self.name = f"mediapipe-pose-landmarker:{model_path.stem}"
        self._last_ts = -1

    def estimate(self, frame_bgr: np.ndarray, timestamp_ms: int) -> list[PoseDetection]:
        # VIDEO mode requires strictly increasing integer timestamps.
        timestamp_ms = max(int(timestamp_ms), self._last_ts + 1)
        self._last_ts = timestamp_ms

        rgb = np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        detections: list[PoseDetection] = []
        for pose in result.pose_landmarks or []:
            arr = np.array(
                [
                    [
                        lm.x,
                        lm.y,
                        lm.z,
                        lm.visibility if lm.visibility is not None else 0.0,
                        lm.presence if lm.presence is not None else 0.0,
                    ]
                    for lm in pose
                ],
                dtype=np.float32,
            )
            if arr.shape == (33, 5):
                detections.append(PoseDetection(landmarks=arr))
        return detections

    def close(self) -> None:
        self._landmarker.close()
