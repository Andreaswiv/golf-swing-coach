"""Pose estimator abstraction.

The rest of the pipeline only depends on this interface, so MediaPipe can be
replaced or supplemented (e.g. by RTMPose / ViTPose) without touching the
pipeline, quality checks or analysis code.

Every estimator must return landmarks in the 33-point MediaPipe layout
(see ``app.landmarks``) as an array of shape (33, 5) with columns
``x, y, z, visibility, presence``. ``x`` and ``y`` are normalised image
coordinates (0..1, origin top-left). ``z`` is a relative depth hint from the
model and must NOT be treated as a calibrated 3D measurement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PoseDetection:
    landmarks: np.ndarray  # shape (33, 5), float32


class PoseEstimator(ABC):
    #: Human readable identifier stored with each analysis.
    name: str

    @abstractmethod
    def estimate(self, frame_bgr: np.ndarray, timestamp_ms: int) -> list[PoseDetection]:
        """Return every person found in the frame (possibly an empty list).

        ``timestamp_ms`` is strictly increasing across calls for one video.
        """

    @abstractmethod
    def close(self) -> None:
        """Release model resources."""

    def __enter__(self) -> "PoseEstimator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
