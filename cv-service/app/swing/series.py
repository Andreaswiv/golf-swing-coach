"""Raw keypoint frames -> clean per-joint time series in pixels.

Steps, in order:
  1. Convert normalised coordinates to pixels, so angles are not distorted by
     the frame's aspect ratio (a 360x640 portrait clip squashes x otherwise).
  2. Mirror left-handed golfers (flip x and swap left/right landmarks), so all
     later code can assume a right-handed swing: lead side = "left".
  3. Fill short gaps where nobody was detected by linear interpolation.
  4. Smooth with a Savitzky-Golay filter. It keeps peaks (top of backswing,
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

    window = smoothing_window(fps)
    for j in range(xy.shape[1]):
        for c in range(2):
            xy[:, j, c] = savgol_runs(fill_gaps(xy[:, j, c], MAX_GAP_FRAMES), window, POLYORDER)

    t = np.array([float(f["t"]) for f in frames])
    return Series(t=t, xy=xy, vis=vis, width=width, height=height, fps=fps, mirrored=mirrored, window=window)


def fill_gaps(y: np.ndarray, max_gap: int) -> np.ndarray:
    """Linearly interpolate interior NaN runs of at most ``max_gap`` frames."""
    y = y.copy()
    missing = np.isnan(y)
    if not missing.any() or missing.all():
        return y
    k, n = 0, len(y)
    while k < n:
        if not missing[k]:
            k += 1
            continue
        start = k
        while k < n and missing[k]:
            k += 1
        if start > 0 and k < n and k - start <= max_gap:
            y[start:k] = np.interp(np.arange(start, k), [start - 1, k], [y[start - 1], y[k]])
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
    valid = ~np.isnan(y)
    k, n = 0, len(y)
    while k < n:
        if not valid[k]:
            k += 1
            continue
        start = k
        while k < n and valid[k]:
            k += 1
        if k - start >= window:
            out[start:k] = savgol(y[start:k], window, order)
    return out


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
