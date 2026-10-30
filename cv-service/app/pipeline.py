"""Video -> raw keypoints pipeline.

Responsibilities:
  * decode the video frame by frame
  * run a ``PoseEstimator`` on every frame
  * pick the golfer when several people are detected
  * write the RAW (unsmoothed, unmirrored) keypoints to a JSON file
  * run the quality checks
  * run the swing analysis (``app.swing``) on the saved keypoints

Smoothing, left-handed mirroring, phases and measurements live in
``app.swing`` and read only the raw keypoints, so they can be re-run later
(POST /analyze) without reprocessing the video.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .landmarks import LANDMARK_FIELDS, LANDMARK_NAMES
from .pose.base import PoseDetection, PoseEstimator
from .quality import FrameObservation, QualityReport, assess_quality
from .swing import analyse_swing
from .video import VideoError, VideoMetadata, open_video, probe_video

KEYPOINTS_FORMAT = "golfcoach.keypoints.v1"
BRIGHTNESS_SAMPLE_EVERY = 10

ProgressCallback = Callable[[int, str], None]


@dataclass
class PipelineOutput:
    video: VideoMetadata
    frame_count: int
    pose_model: str
    quality: QualityReport
    swing: dict


def select_golfer(detections: list[PoseDetection]) -> PoseDetection | None:
    """Pick the golfer when several people are present.

    Heuristic: the person with the largest on-screen body extent (confidently
    visible landmarks only). This favours the subject filmed up close over
    bystanders in the background. It can fail if a bystander is closer to the
    camera than the golfer; that case is reported via the multiple-people warning.
    """
    if not detections:
        return None
    if len(detections) == 1:
        return detections[0]

    def extent(d: PoseDetection) -> float:
        lm = d.landmarks
        vis = lm[:, 3] >= 0.5
        if vis.sum() < 4:
            return 0.0
        xs, ys = lm[vis, 0], lm[vis, 1]
        return float((xs.max() - xs.min()) * (ys.max() - ys.min()))

    return max(detections, key=extent)


def _frame_timestamps_seconds(raw_ms: list[float], fps: float) -> list[float]:
    """Convert OpenCV per-frame timestamps to seconds starting at 0.

    Falls back to index / fps when the container timestamps are unusable
    (all zero or not increasing). Using real timestamps keeps variable-frame-rate
    footage (e.g. iPhone slow-motion clips) in sync with the browser player.
    """
    n = len(raw_ms)
    fallback = [i / fps for i in range(n)]
    if n < 2:
        return fallback
    arr = np.asarray(raw_ms, dtype=np.float64)
    if not np.all(np.diff(arr) > 0):
        return fallback
    return [float(v) for v in (arr - arr[0]) / 1000.0]


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    os.replace(tmp, path)


def run_pipeline(
    video_path: Path,
    keypoints_path: Path,
    estimator: PoseEstimator,
    camera_angle: str,
    handedness: str,
    on_progress: ProgressCallback | None = None,
    max_process_dim: int = 1280,
) -> PipelineOutput:
    def progress(pct: int, stage: str) -> None:
        if on_progress:
            on_progress(min(max(pct, 0), 99), stage)

    progress(1, "Reading video")
    meta = probe_video(video_path)
    if meta.duration_seconds and meta.duration_seconds > 120:
        raise VideoError(
            "The video is longer than 2 minutes. Trim it to the swing (a few seconds)."
        )

    progress(4, "Detecting pose")
    cap = open_video(video_path)
    observations: list[FrameObservation] = []
    frames_out: list[dict] = []
    raw_ms: list[float] = []
    brightness: list[tuple[float, float]] = []
    expected = max(meta.declared_frame_count, 1)

    try:
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            raw_ms.append(float(cap.get(cv2.CAP_PROP_POS_MSEC)))

            h, w = frame.shape[:2]
            scale = max_process_dim / max(h, w)
            small = (
                cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
                if scale < 1.0
                else frame
            )

            if index % BRIGHTNESS_SAMPLE_EVERY == 0:
                gray = cv2.cvtColor(
                    cv2.resize(small, (160, max(1, round(160 * small.shape[0] / small.shape[1])))),
                    cv2.COLOR_BGR2GRAY,
                )
                brightness.append((float(gray.mean()), float(gray.std())))

            # Estimator timestamps need to be monotonic integers; derive from
            # the frame rate here, the estimator enforces strict increase.
            detections = estimator.estimate(small, int(round(index * 1000.0 / meta.fps)))
            golfer = select_golfer(detections)
            lm = golfer.landmarks if golfer is not None else None

            observations.append(FrameObservation(n_poses=len(detections), landmarks=lm))
            frames_out.append(
                {
                    "i": index,
                    "n": len(detections),
                    "lm": np.round(lm, 5).tolist() if lm is not None else None,
                }
            )
            index += 1

            if index % 10 == 0:
                progress(4 + int(90 * min(index / expected, 1.0)), "Detecting pose")
    finally:
        cap.release()

    if not frames_out:
        raise VideoError("No frames could be decoded from the video.")

    times = _frame_timestamps_seconds(raw_ms, meta.fps)
    for frame_dict, t in zip(frames_out, times):
        frame_dict["t"] = round(t, 4)
        # keep "t" right after "i" for readability
        frame_dict.update({k: frame_dict.pop(k) for k in ("n", "lm")})

    progress(95, "Assessing video quality")
    quality = assess_quality(meta, observations, brightness)

    progress(97, "Saving keypoints")
    payload = {
        "format": KEYPOINTS_FORMAT,
        "pose_model": estimator.name,
        "coordinate_space": "normalized_image",  # x,y in 0..1, origin top-left, as displayed
        "landmark_names": LANDMARK_NAMES,
        "landmark_fields": LANDMARK_FIELDS,
        "note": "Raw detections: not smoothed and not mirrored for left-handed golfers.",
        "video": {
            "width": meta.width,
            "height": meta.height,
            "fps": meta.fps,
            "frame_count": len(frames_out),
            "rotation_degrees": meta.rotation_degrees,
        },
        "camera_angle": camera_angle,
        "handedness": handedness,
        "frames": frames_out,
    }
    _write_json_atomic(keypoints_path, payload)

    progress(98, "Analysing swing")
    swing = analyse_swing(payload)

    return PipelineOutput(
        video=meta,
        frame_count=len(frames_out),
        pose_model=estimator.name,
        quality=quality,
        swing=swing,
    )
