"""Video -> raw keypoints pipeline.

Responsibilities:
  * decode the video frame by frame
  * run a ``PoseEstimator`` on every frame
  * pick the golfer when several people are detected
  * find the swing from the pose and run the club detector only
    around it, in a second pass over the video
  * write the RAW (unsmoothed, unmirrored) keypoints to a JSON file
  * run the quality checks
  * run the swing analysis (``app.swing``) on the saved keypoints

Smoothing, left-handed mirroring, phases and measurements live in
``app.swing`` and read only the raw keypoints, so they can be re-run later
(POST /analyze) without reprocessing the video.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .club.detector import ClubDetector
from .landmarks import LANDMARK_FIELDS, LANDMARK_NAMES
from .pose.base import PoseDetection, PoseEstimator
from .quality import FrameObservation, QualityReport, assess_quality
from .swing import analyse_swing
from .swing.phases import NoSwingFound, detect_phases
from .swing.series import build_series
from .video import VideoError, VideoMetadata, open_video, probe_video

KEYPOINTS_FORMAT = "golfcoach.keypoints.v1"
BRIGHTNESS_SAMPLE_EVERY = 10
# Longest video accepted (video time, so a slow-motion export counts at its playback length).
# Keep in sync with MAX_VIDEO_SECONDS in frontend/src/api.ts.
MAX_VIDEO_SECONDS = 15.0
LENGTH_TOLERANCE_S = 0.05  # container rounding: a "15 s" phone clip can be 15.02 s
# Club detection runs from this long before the takeaway to this long after the finish.
CLUB_LEAD_S = 1.0
CLUB_TAIL_S = 0.3
CLUB_PASS_START_PCT = 70  # progress when the club pass starts (pose takes most of the time)

log = logging.getLogger("cv.pipeline")

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


def _check_length(seconds: float) -> None:
    if seconds > MAX_VIDEO_SECONDS + LENGTH_TOLERANCE_S:
        raise VideoError(
            f"The video is {seconds:.1f} seconds long. The limit is {MAX_VIDEO_SECONDS:.0f} seconds: "
            "trim it to just the swing."
        )


def _downscale(frame: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1.0:
        return frame
    return cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def club_frame_range(frames: list[dict], meta: VideoMetadata, camera_angle: str, handedness: str) -> tuple[int, int]:
    """Inclusive frame range to run the club detector on: the swing found from the pose, plus margins.

    From CLUB_LEAD_S before the takeaway (the address position, for the swing plane) to
    CLUB_TAIL_S after the finish. Video time, so slow-motion clips get the same margins in frames
    as they show on screen. Every frame when no swing is found: better slow than missing the club.
    """
    last = len(frames) - 1
    payload = {
        "frames": frames,
        "video": {"width": meta.width, "height": meta.height, "fps": meta.fps},
        "camera_angle": camera_angle,
        "handedness": handedness,
    }
    try:
        phases = detect_phases(build_series(payload))
    except NoSwingFound:
        return 0, last
    except Exception:  # noqa: BLE001 - a bug here must not cost the club tracking
        log.exception("Finding the swing for club tracking failed; checking every frame")
        return 0, last
    end_event = phases.frame("finish") if phases.frame("finish") is not None else phases.frame("impact")
    start_t = frames[phases.frame("takeaway")]["t"] - CLUB_LEAD_S
    end_t = frames[end_event]["t"] + CLUB_TAIL_S
    first = next((k for k, f in enumerate(frames) if f["t"] >= start_t), 0)
    end = max((k for k, f in enumerate(frames) if f["t"] <= end_t), default=last)
    return first, end


def _detect_club(
    video_path: Path,
    frames: list[dict],
    club_frames: tuple[int, int],
    detector: ClubDetector,
    max_process_dim: int,
    progress: ProgressCallback,
) -> None:
    """Second pass: add the best box per club part to the frames in ``club_frames`` (inclusive)."""
    first, last = club_frames
    stage = "Tracking the club"
    progress(CLUB_PASS_START_PCT, stage)
    cap = open_video(video_path)
    try:
        index = 0
        while index <= last:
            if index < first:  # advance without decoding the picture
                if not cap.grab():
                    break
                index += 1
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            small = _downscale(frame, max_process_dim)
            # Normalised [x1, y1, x2, y2, conf]; an absent part = checked but not found.
            frames[index]["club"] = {part: box.to_list() for part, box in detector.detect(small).items()}
            done = index - first + 1
            if done % 5 == 0:
                share = done / (last - first + 1)
                progress(CLUB_PASS_START_PCT + int((94 - CLUB_PASS_START_PCT) * share), stage)
            index += 1
    finally:
        cap.release()


def run_pipeline(
    video_path: Path,
    keypoints_path: Path,
    estimator: PoseEstimator,
    camera_angle: str,
    handedness: str,
    on_progress: ProgressCallback | None = None,
    max_process_dim: int = 1280,
    club_detector: ClubDetector | None = None,
) -> PipelineOutput:
    def progress(pct: int, stage: str) -> None:
        if on_progress:
            on_progress(min(max(pct, 0), 99), stage)

    progress(1, "Reading video")
    meta = probe_video(video_path)
    if meta.duration_seconds:
        _check_length(meta.duration_seconds)

    # Pose first, on every frame: it is how the swing is found. The club detector then only has
    # to run around the swing (second pass).
    pose_end = CLUB_PASS_START_PCT if club_detector else 94
    stage = "Detecting pose"
    progress(4, stage)
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

            small = _downscale(frame, max_process_dim)

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
            frame_out = {
                "i": index,
                "n": len(detections),
                "lm": np.round(lm, 5).tolist() if lm is not None else None,
            }
            frames_out.append(frame_out)
            index += 1

            if index % 10 == 0:
                progress(4 + int((pose_end - 4) * min(index / expected, 1.0)), stage)
    finally:
        cap.release()

    if not frames_out:
        raise VideoError("No frames could be decoded from the video.")

    times = _frame_timestamps_seconds(raw_ms, meta.fps)
    if not meta.duration_seconds:
        _check_length(times[-1])  # the container did not say; the decoded frames do
    for frame_dict, t in zip(frames_out, times):
        frame_dict["t"] = round(t, 4)
        # keep "t" right after "i" for readability
        frame_dict.update({k: frame_dict.pop(k) for k in ("n", "lm", "club") if k in frame_dict})

    club_frames = None
    if club_detector is not None:
        club_frames = club_frame_range(frames_out, meta, camera_angle, handedness)
        _detect_club(video_path, frames_out, club_frames, club_detector, max_process_dim, progress)

    progress(95, "Assessing video quality")
    quality = assess_quality(meta, observations, brightness)

    progress(97, "Saving keypoints")
    payload = {
        "format": KEYPOINTS_FORMAT,
        "pose_model": estimator.name,
        "club_model": club_detector.name if club_detector else None,
        # Inclusive frame range the club detector ran on; frames outside it have no "club" key.
        "club_frames": list(club_frames) if club_frames else None,
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
