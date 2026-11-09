"""Raw keypoint frames -> clean per-joint time series in pixels.

Steps, in order:
  1. Convert normalised coordinates to pixels, so angles are not distorted by
     the frame's aspect ratio (a 360x640 portrait clip squashes x otherwise).
  2. Mirror left-handed golfers (flip x and swap left/right landmarks), so all
     later code can assume a right-handed swing: lead side = "left".
  3. Drop detection glitches: a joint that jumps away and comes straight back
     within about 0.05 s (MediaPipe sometimes puts a hidden wrist somewhere
     else for a few frames, with high visibility). Real body parts cannot do
     that, and one glitch can look faster than the real downswing.
     Also drop a joint where its limb gets impossibly long: on video a forearm or
     shin can look shorter (pointing at the camera) but never longer than it is.
  4. Fill short gaps (no detection, or a dropped glitch) by linear interpolation.
  5. Smooth with a Savitzky-Golay filter. It keeps peaks (top of backswing,
     impact) sharper than a moving average of the same width.

Visibility is kept raw. Interpolated frames keep visibility 0, so anything
measured from them gets a low confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..landmarks import LANDMARK_INDEX, LANDMARK_NAMES

MAX_GAP_FRAMES = 6
POLYORDER = 2
# Glitch = a joint leaves by at least SPIKE_MIN_JUMP torso lengths and is back within SPIKE_RETURN
# of where it left, all within SPIKE_MAX_S. At impact the hands also move fast, but they do not
# come back to the same place 0.05 s later.
SPIKE_MAX_S = 0.05
SPIKE_MIN_JUMP = 0.25
SPIKE_RETURN = 0.1
# (parent, child): the child is dropped when the limb between them is more than MAX_BONE_FACTOR
# times its usual length in this clip. Ordered from the body outward, so a dropped elbow is not
# also used to judge the wrist.
BONES = [
    ("left_shoulder", "left_elbow"), ("right_shoulder", "right_elbow"),
    ("left_elbow", "left_wrist"), ("right_elbow", "right_wrist"),
    ("left_hip", "left_knee"), ("right_hip", "right_knee"),
    ("left_knee", "left_ankle"), ("right_knee", "right_ankle"),
    ("left_ankle", "left_heel"), ("right_ankle", "right_heel"),
    ("left_ankle", "left_foot_index"), ("right_ankle", "right_foot_index"),
]
MAX_BONE_FACTOR = 1.4  # the "usual" length is the 90th percentile, so this leaves room for noise
WRISTS = ["left_wrist", "right_wrist"]


@dataclass
class Series:
    t: np.ndarray  # (F,) seconds, video time
    xy: np.ndarray  # (F, 33, 2) pixels after mirroring and smoothing; NaN where unknown
    vis: np.ndarray  # (F, 33) raw visibility; 0 where the frame had no detection
    width: int
    height: int
    fps: float
    mirrored: bool
    window: int  # smoothing window in frames
    rejected: np.ndarray  # (F, 33) bool: detection dropped as impossible (a glitch or an over-long limb)

    @property
    def frame_count(self) -> int:
        return len(self.t)

    def point(self, name: str) -> np.ndarray:
        return self.xy[:, LANDMARK_INDEX[name]]

    def visibility(self, name: str) -> np.ndarray:
        return self.vis[:, LANDMARK_INDEX[name]]


def mirror_permutation() -> np.ndarray:
    """Index permutation that swaps every left_* landmark with its right_* twin."""
    perm = np.arange(len(LANDMARK_NAMES))
    for name, i in LANDMARK_INDEX.items():
        if name.startswith("left_"):
            j = LANDMARK_INDEX["right_" + name[len("left_") :]]
            perm[i], perm[j] = j, i
    return perm


def smoothing_window(fps: float) -> int:
    """About 0.1 s of frames, odd, at least 5."""
    w = max(5, int(round(fps * 0.1)))
    return w if w % 2 == 1 else w + 1


def build_series(payload: dict) -> Series:
    frames = payload["frames"]
    video = payload["video"]
    width, height, fps = int(video["width"]), int(video["height"]), float(video["fps"] or 30.0)
    n = len(frames)

    xy = np.full((n, len(LANDMARK_NAMES), 2), np.nan)
    vis = np.zeros((n, len(LANDMARK_NAMES)))
    for k, frame in enumerate(frames):
        lm = frame.get("lm")
        if lm is None:
            continue
        a = np.asarray(lm, dtype=float)
        xy[k, :, 0] = a[:, 0] * width
        xy[k, :, 1] = a[:, 1] * height
        vis[k] = a[:, 3]

    mirrored = payload.get("handedness") == "left"
    if mirrored:
        xy[:, :, 0] = width - xy[:, :, 0]
        perm = mirror_permutation()
        xy, vis = xy[:, perm], vis[:, perm]

    rejected = np.zeros(vis.shape, dtype=bool)
    scale = median_torso_length(xy)
    if scale is not None:
        max_len = max(1, int(round(fps * SPIKE_MAX_S)))
        for j in range(xy.shape[1]):
            rejected[:, j] = find_spikes(xy[:, j], max_len, SPIKE_MIN_JUMP * scale, SPIKE_RETURN * scale)
        xy[rejected] = np.nan
        for parent, child in BONES:
            a, b = LANDMARK_INDEX[parent], LANDMARK_INDEX[child]
            too_long = overlong_bone(xy[:, a], xy[:, b])
            xy[too_long, b] = np.nan
            rejected[too_long, b] = True
        vis[rejected] = 0.0

    window = smoothing_window(fps)
    for j in range(xy.shape[1]):
        for c in range(2):
            xy[:, j, c] = savgol_runs(fill_gaps(xy[:, j, c], MAX_GAP_FRAMES), window, POLYORDER)

    t = np.array([float(f["t"]) for f in frames])
    return Series(
        t=t, xy=xy, vis=vis, width=width, height=height, fps=fps, mirrored=mirrored, window=window, rejected=rejected
    )


def rejected_landmarks(s: Series) -> dict[str, list[int]]:
    """Frames where each landmark was dropped, by its name in the RAW keypoints (mirroring undone)."""
    perm = mirror_permutation() if s.mirrored else np.arange(len(LANDMARK_NAMES))
    out: dict[str, list[int]] = {}
    for j in range(s.rejected.shape[1]):
        frames = np.flatnonzero(s.rejected[:, j])
        if len(frames):
            out[LANDMARK_NAMES[perm[j]]] = [int(f) for f in frames]
    return out


def median_torso_length(xy: np.ndarray) -> float | None:
    """Median shoulder-centre to hip-centre distance in px; None if unknown. ``xy``: (F, 33, 2)."""
    shoulders = (xy[:, LANDMARK_INDEX["left_shoulder"]] + xy[:, LANDMARK_INDEX["right_shoulder"]]) / 2
    hips = (xy[:, LANDMARK_INDEX["left_hip"]] + xy[:, LANDMARK_INDEX["right_hip"]]) / 2
    lengths = np.linalg.norm(shoulders - hips, axis=1)
    lengths = lengths[~np.isnan(lengths)]
    return float(np.median(lengths)) if len(lengths) and np.median(lengths) > 1 else None


def overlong_bone(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Frames where the segment a-b is more than MAX_BONE_FACTOR times its usual (90th percentile) length."""
    lengths = np.linalg.norm(b - a, axis=1)
    known = ~np.isnan(lengths)
    if known.sum() < 10:
        return np.zeros(len(a), dtype=bool)
    usual = np.percentile(lengths[known], 90)
    with np.errstate(invalid="ignore"):
        return known & (lengths > MAX_BONE_FACTOR * usual)


def find_spikes(p: np.ndarray, max_len: int, min_jump: float, max_return: float) -> np.ndarray:
    """Frames where a point jumps away and comes back within ``max_len`` frames.

    ``p``: (F, 2) positions, NaN where unknown. A run of 1..max_len frames is a spike when the
    frames on either side are within ``max_return`` of each other and some frame in the run is at
    least ``min_jump`` away from both of them. Returns a boolean mask.
    """
    n = len(p)
    out = np.zeros(n, dtype=bool)
    known = ~np.isnan(p[:, 0])
    found = np.zeros(n, dtype=bool)  # frames before a spike already found: only the shortest one counts
    for length in range(1, max_len + 1):
        a = np.flatnonzero(known[: max(n - length - 1, 0)] & ~found[: max(n - length - 1, 0)])
        b = a + length + 1
        back = known[b] & (np.linalg.norm(p[b] - p[a], axis=1) <= max_return)
        a, b = a[back], b[back]
        if not len(a):
            continue
        run = a[:, None] + np.arange(1, length + 1)  # (candidates, length) frame numbers
        away = np.minimum(
            np.linalg.norm(p[run] - p[a, None], axis=2),
            np.linalg.norm(p[run] - p[b, None], axis=2),
        )
        spike = np.nan_to_num(away, nan=-np.inf).max(axis=1) >= min_jump
        out[run[spike]] = True
        found[a[spike]] = True
    return out


def _true_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) of every run of True values; ``end`` is exclusive."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(int), [0]))))
    return [(int(start), int(end)) for start, end in zip(edges[::2], edges[1::2])]


def fill_gaps(y: np.ndarray, max_gap: int) -> np.ndarray:
    """Linearly interpolate interior NaN runs of at most ``max_gap`` frames."""
    y = y.copy()
    missing = np.isnan(y)
    if not missing.any() or missing.all():
        return y
    for start, end in _true_runs(missing):
        if start > 0 and end < len(y) and end - start <= max_gap:
            y[start:end] = np.interp(np.arange(start, end), [start - 1, end], [y[start - 1], y[end]])
    return y


def savgol(y: np.ndarray, window: int, order: int) -> np.ndarray:
    """Savitzky-Golay smoothing of a NaN-free array (edges: polynomial fit, like scipy's mode='interp')."""
    n = len(y)
    if n < window:
        return y.copy()
    h = window // 2
    centred = np.vander(np.arange(-h, h + 1), order + 1, increasing=True)
    coeffs = np.linalg.pinv(centred)[0]
    out = np.empty(n)
    out[h : n - h] = np.convolve(y, coeffs[::-1], mode="valid")

    edge = np.vander(np.arange(window), order + 1, increasing=True)
    fit = np.linalg.pinv(edge)
    out[:h] = (edge @ (fit @ y[:window]))[:h]
    out[n - h :] = (edge @ (fit @ y[n - window :]))[window - h :]
    return out


def savgol_runs(y: np.ndarray, window: int, order: int) -> np.ndarray:
    """Smooth each NaN-free run separately; runs shorter than the window stay raw."""
    out = y.copy()
    for start, end in _true_runs(~np.isnan(y)):
        if end - start >= window:
            out[start:end] = savgol(y[start:end], window, order)
    return out


def visibility_confidence(visibility: float) -> float:
    """Map a mean landmark visibility to a 0..1 confidence score."""
    return float(np.clip((visibility - 0.3) / 0.5, 0.0, 1.0))


def weighted_point(s: Series, names: list[str], floor: float = 0.05) -> np.ndarray:
    """Per-frame visibility-weighted mean of several landmarks, shape (F, 2).

    Hidden joints still count a little (``floor``): MediaPipe's guess for an
    occluded wrist is usually close, and it beats having no position at all.
    """
    pts = np.stack([s.point(n) for n in names], axis=1)  # (F, k, 2)
    w = np.stack([np.maximum(s.visibility(n), floor) for n in names], axis=1)  # (F, k)
    w = np.where(np.isnan(pts[:, :, 0]), 0.0, w)
    total = w.sum(axis=1)
    summed = np.nansum(pts * w[:, :, None], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = summed / total[:, None]
    out[total == 0] = np.nan
    return out
