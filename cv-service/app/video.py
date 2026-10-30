"""Video probing and frame iteration (OpenCV)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2


class VideoError(Exception):
    """The video cannot be read or decoded."""


@dataclass(frozen=True)
class VideoMetadata:
    width: int  # after applying rotation metadata, i.e. as displayed
    height: int
    fps: float
    declared_frame_count: int  # from the container; may be inaccurate
    duration_seconds: float
    orientation: str  # "landscape" | "portrait" | "square"
    rotation_degrees: int  # rotation flag stored in the file (already applied to frames)
    codec: str

    def to_dict(self) -> dict:
        return asdict(self)


def _fourcc_to_str(value: float) -> str:
    code = int(value)
    if code <= 0:
        return "unknown"
    chars = "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))
    return chars if chars.isprintable() else "unknown"


def open_video(path: Path) -> cv2.VideoCapture:
    if not path.is_file():
        raise VideoError(f"Video file not found: {path.name}")
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise VideoError(
            "The video could not be opened. The codec may be unsupported; "
            "try re-exporting it as H.264 MP4."
        )
    return cap


def probe_video(path: Path) -> VideoMetadata:
    """Read container metadata plus the real frame size from the first frame.

    OpenCV applies rotation metadata (e.g. iPhone portrait videos) when
    decoding, so the first decoded frame gives the size as displayed.
    """
    cap = open_video(path)
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        declared = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        rotation = int(cap.get(cv2.CAP_PROP_ORIENTATION_META) or 0)
        codec = _fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))

        ok, frame = cap.read()
        if not ok or frame is None:
            raise VideoError("The video was opened but no frames could be decoded.")
        height, width = frame.shape[:2]
    finally:
        cap.release()

    if fps <= 0 or fps > 1000:
        raise VideoError(f"The video reports an unusable frame rate ({fps}).")

    if width > height:
        orientation = "landscape"
    elif height > width:
        orientation = "portrait"
    else:
        orientation = "square"

    return VideoMetadata(
        width=width,
        height=height,
        fps=round(fps, 3),
        declared_frame_count=max(declared, 0),
        duration_seconds=round(declared / fps, 3) if declared > 0 else 0.0,
        orientation=orientation,
        rotation_degrees=rotation,
        codec=codec,
    )
