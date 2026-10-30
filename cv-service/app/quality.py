"""Video quality assessment.

Quality checks never reject a video outright. They produce warnings and a
``temporal_resolution_factor`` that later analysis stages use to lower the
confidence of measurements affected by low frame rate / motion blur.

Implemented now: frame rate, resolution, lighting, pose detection rate,
key-joint visibility, golfer inside frame, multiple people.

Not implemented yet (listed in ``checks_not_run`` so the UI never implies they
passed): camera motion, camera-angle match.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .landmarks import FRAME_EDGE_LANDMARKS, KEY_JOINTS, LANDMARK_INDEX
from .video import VideoMetadata

VISIBILITY_THRESHOLD = 0.5


@dataclass
class FrameObservation:
    n_poses: int
    landmarks: np.ndarray | None  # (33, 5) of the selected golfer, or None


@dataclass
class QualityWarning:
    code: str
    severity: str  # "info" | "warning" | "high"
    message: str


@dataclass
class QualityReport:
    overall: str  # "good" | "warning" | "poor"
    warnings: list[QualityWarning] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    checks_not_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "warnings": [w.__dict__ for w in self.warnings],
            "stats": self.stats,
            "checks_not_run": self.checks_not_run,
        }


def temporal_resolution_factor(fps: float) -> float:
    """Multiplier (0..1) for confidence of speed/timing dependent measurements."""
    if fps >= 120:
        return 1.0
    if fps >= 60:
        return 0.9
    if fps >= 30:
        return 0.6
    return 0.4


def assess_quality(
    meta: VideoMetadata,
    observations: list[FrameObservation],
    brightness_samples: list[tuple[float, float]],
) -> QualityReport:
    warnings: list[QualityWarning] = []
    stats: dict = {}
    n_frames = len(observations)

    # --- frame rate -------------------------------------------------------
    factor = temporal_resolution_factor(meta.fps)
    stats["fps"] = meta.fps
    stats["temporal_resolution_factor"] = factor
    if meta.fps < 30:
        warnings.append(
            QualityWarning(
                "low_fps",
                "high",
                f"Frame rate is {meta.fps:.0f} FPS. A golf swing lasts about a second, so "
                "this leaves very few frames per phase and timing-related measurements "
                "(including impact) will be unreliable. Record at 60 FPS or higher, "
                "preferably 120 FPS.",
            )
        )
    elif meta.fps < 60:
        warnings.append(
            QualityWarning(
                "low_fps",
                "warning",
                f"Frame rate is {meta.fps:.0f} FPS. The analysis will run, but fast phases "
                "(downswing, impact) are sampled sparsely and may be blurred, so confidence "
                "is reduced. Record at 60 FPS or higher, preferably 120 FPS.",
            )
        )

    # --- resolution -------------------------------------------------------
    short_side = min(meta.width, meta.height)
    stats["resolution"] = f"{meta.width}x{meta.height}"
    if short_side < 540:
        warnings.append(
            QualityWarning(
                "low_resolution",
                "warning",
                f"Resolution is {meta.width}x{meta.height}. Joint detection is less accurate "
                "on small footage; 1080p is recommended.",
            )
        )

    # --- lighting ---------------------------------------------------------
    if brightness_samples:
        mean_luma = float(np.mean([b[0] for b in brightness_samples]))
        mean_contrast = float(np.mean([b[1] for b in brightness_samples]))
        stats["mean_brightness"] = round(mean_luma, 1)
        stats["mean_contrast"] = round(mean_contrast, 1)
        if mean_luma < 60:
            warnings.append(
                QualityWarning(
                    "poor_lighting",
                    "warning",
                    "The video is quite dark, which can make joint detection unstable. "
                    "Record in brighter conditions.",
                )
            )
        elif mean_luma > 205:
            warnings.append(
                QualityWarning(
                    "poor_lighting",
                    "warning",
                    "The video looks overexposed, which can hide the golfer's body outline.",
                )
            )
        elif mean_contrast < 20:
            warnings.append(
                QualityWarning(
                    "poor_lighting",
                    "info",
                    "The footage has low contrast; the golfer may blend into the background.",
                )
            )

    # --- pose detection ---------------------------------------------------
    detected = [o for o in observations if o.landmarks is not None]
    detection_rate = len(detected) / n_frames if n_frames else 0.0
    stats["frames_analysed"] = n_frames
    stats["frames_with_pose"] = len(detected)
    stats["pose_detection_rate"] = round(detection_rate, 3)
    if n_frames and detection_rate < 0.5:
        warnings.append(
            QualityWarning(
                "pose_not_detected",
                "high",
                f"A person was detected in only {detection_rate:.0%} of frames. Make sure the "
                "golfer is clearly visible, fully in frame and not too small.",
            )
        )
    elif n_frames and detection_rate < 0.9:
        warnings.append(
            QualityWarning(
                "pose_not_detected",
                "warning",
                f"A person was detected in {detection_rate:.0%} of frames. Missing frames reduce "
                "the reliability of swing phase detection.",
            )
        )

    if detected:
        lms = np.stack([o.landmarks for o in detected])  # (N, 33, 5)

        # --- key joint visibility -----------------------------------------
        low_joints: list[str] = []
        joint_vis: dict[str, float] = {}
        for name in KEY_JOINTS:
            vis = lms[:, LANDMARK_INDEX[name], 3]
            joint_vis[name] = round(float(np.median(vis)), 3)
            if float(np.mean(vis < VISIBILITY_THRESHOLD)) > 0.2:
                low_joints.append(name.replace("_", " "))
        stats["median_joint_visibility"] = joint_vis
        if low_joints:
            warnings.append(
                QualityWarning(
                    "joints_low_visibility",
                    "warning",
                    "These joints are often hard to see: "
                    + ", ".join(low_joints)
                    + ". Measurements that depend on them will have lower confidence.",
                )
            )

        # --- golfer inside frame ------------------------------------------
        outside = np.zeros(len(detected), dtype=bool)
        for name in FRAME_EDGE_LANDMARKS:
            x = lms[:, LANDMARK_INDEX[name], 0]
            y = lms[:, LANDMARK_INDEX[name], 1]
            outside |= (x < 0.0) | (x > 1.0) | (y < 0.0) | (y > 1.0)
        outside_rate = float(np.mean(outside))
        stats["frames_golfer_partly_outside"] = round(outside_rate, 3)
        if outside_rate > 0.1:
            warnings.append(
                QualityWarning(
                    "golfer_not_fully_visible",
                    "warning",
                    "Parts of the golfer (head, hands or feet) leave the frame in "
                    f"{outside_rate:.0%} of frames. Frame the whole body, club included, "
                    "throughout the swing.",
                )
            )

    # --- multiple people --------------------------------------------------
    multi_rate = (
        sum(1 for o in observations if o.n_poses >= 2) / n_frames if n_frames else 0.0
    )
    stats["frames_with_multiple_people"] = round(multi_rate, 3)
    if multi_rate > 0.2:
        warnings.append(
            QualityWarning(
                "multiple_people",
                "warning",
                f"More than one person was detected in {multi_rate:.0%} of frames. Tracking "
                "may jump to the wrong person; record with only the golfer in view.",
            )
        )

    if any(w.severity == "high" for w in warnings):
        overall = "poor"
    elif any(w.severity == "warning" for w in warnings):
        overall = "warning"
    else:
        overall = "good"

    return QualityReport(
        overall=overall,
        warnings=warnings,
        stats=stats,
        checks_not_run=["camera_motion", "camera_angle_match"],
    )
