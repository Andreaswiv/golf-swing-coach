"""Swing phase detection from the hands' path.

All heuristics work in frames and in "torso lengths" (shoulder-centre to
hip-centre distance), never in seconds or pixels. That keeps them independent
of the frame rate, of slow-motion exports and of how big the golfer is.

  1. Downswing anchor: the frame where the hands move down fastest. Waggles
     and practice moves are slower, so this finds the real swing. If that
     does not lead to a believable swing (too small, or the hands rose to the
     "top" faster than any real backswing: a leftover detection glitch), the
     next-fastest downward movement is tried.
  2. Impact: the lowest hand position just after that anchor.
  3. Top: the end of the highest hand position before it. If the golfer pauses
     at the top, this is the moment the hands start down, not the start of the
     pause.
  4. Address: the hand position held longest before the top (with the hands
     down near impact height). Address is the middle of the last period at
     that position, so posture is measured in the settled setup. Position, not
     speed: at 30 fps the frame-to-frame jitter while standing still is as
     large as a slow takeaway.
  5. Takeaway: the first frame after that period, i.e. when the HANDS start
     moving. The club is not tracked, and the clubhead often starts earlier.
  6. Finish: the first frame after impact where the hands reach their highest
     follow-through position.

Confidence values are heuristic scores from 0 to 1, not probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..quality import temporal_resolution_factor
from .series import Series, weighted_point

MIN_SWING_RANGE = 0.5  # hands must rise at least half a torso length between impact and top
ADDRESS_RADIUS = 0.08  # torso lengths: hands within this of the address position count as "at address"
MIN_ADDRESS_FRAMES = 5  # the address position must be held at least this many frames
FINISH_TOLERANCE = 0.05  # torso lengths below the highest follow-through point
TOP_PAUSE_TOLERANCE = 0.05  # torso lengths: still "at the top" within this of the highest point
SLOW_MOTION_DOWNSWING_S = 0.6  # real downswings take roughly 0.25-0.45 s
# The hands' rise from near impact height to the top takes well over 0.3 s in real backswings
# (slow motion only makes it longer). Faster than this is a detection glitch, not a swing.
MIN_BACKSWING_RISE_S = 0.2
MAX_ANCHOR_CANDIDATES = 10

PHASE_ORDER = ["address", "takeaway", "top", "impact", "finish"]


class NoSwingFound(Exception):
    pass


@dataclass
class PhaseEvent:
    name: str
    frame: int
    method: str
    confidence: float  # how sure we are WHEN it happened (includes the frame-rate factor for impact)
    timing_factor: float = 1.0
    position_confidence: float = 0.0  # how well the body is visible there; used by measurements


@dataclass
class Phases:
    events: dict[str, PhaseEvent]
    torso_px: float
    notes: list[dict]
    slow_motion_suspected: bool
    # Inclusive frame ranges that measurements average over (address, top) or test stability on (impact).
    windows: dict[str, tuple[int, int]]

    def frame(self, name: str) -> int | None:
        event = self.events.get(name)
        return event.frame if event else None

    def confidence(self, name: str) -> float:
        event = self.events.get(name)
        return event.confidence if event else 0.0


def torso_length(s: Series) -> float:
    shoulders = (s.point("left_shoulder") + s.point("right_shoulder")) / 2
    hips = (s.point("left_hip") + s.point("right_hip")) / 2
    lengths = np.linalg.norm(shoulders - hips, axis=1)
    lengths = lengths[~np.isnan(lengths)]
    if len(lengths) == 0 or np.median(lengths) <= 1:
        raise NoSwingFound("The golfer's shoulders and hips were not found reliably enough to analyse the swing.")
    return float(np.median(lengths))


def hand_visibility_score(s: Series, frame: int) -> float:
    """0..1 from the better-visible wrist, averaged over the frame and its neighbours."""
    lo, hi = max(frame - 1, 0), min(frame + 2, s.frame_count)
    best = np.maximum(s.visibility("left_wrist")[lo:hi], s.visibility("right_wrist")[lo:hi])
    return float(np.clip((best.mean() - 0.3) / 0.5, 0.0, 1.0))


def _anchor_candidates(vy: np.ndarray) -> list[int]:
    """Peaks of downward hand speed, fastest first."""
    n = len(vy)
    peaks = [f for f in range(n) if vy[f] > 0 and (f == 0 or vy[f] >= vy[f - 1]) and (f == n - 1 or vy[f] > vy[f + 1])]
    return sorted(peaks, key=lambda f: -vy[f])[:MAX_ANCHOR_CANDIDATES]


def _swing_from_anchor(hy: np.ndarray, t: np.ndarray, anchor: int) -> tuple[int, int, int] | None:
    """(impact, highest, top) for the downswing through ``anchor``, or None if it is not a believable swing."""
    n = len(hy)
    # Impact: lowest hands between the anchor and the moment the hands come back up past
    # anchor height in the follow-through. Region searches, not slope following: at 30 fps
    # the hands jitter around the turning points and a slope walk stops too early.
    k = anchor + 1
    while k < n and hy[k] > hy[anchor]:
        k += 1
    impact = anchor + int(np.argmax(hy[anchor:k]))

    # Top: highest hands between the anchor and the last earlier frame where the hands were
    # back down near impact height (the start of this swing, not an earlier practice swing).
    near_impact = hy[impact] - 0.25 * (hy[impact] - hy[anchor])
    k = anchor
    while k > 0 and hy[k] < near_impact:
        k -= 1
    highest = k + int(np.argmin(hy[k : anchor + 1]))
    top = highest
    while top + 1 < anchor and hy[top + 1] <= hy[highest] + TOP_PAUSE_TOLERANCE:
        top += 1

    if hy[impact] - hy[top] < MIN_SWING_RANGE or not top < anchor <= impact:
        return None
    # k == 0: the clip starts mid-backswing, so the rise time is unknown, not short.
    if k > 0 and t[highest] - t[k] < MIN_BACKSWING_RISE_S:
        return None
    return impact, highest, top


def detect_phases(s: Series) -> Phases:
    if s.frame_count < 10:
        raise NoSwingFound("The clip is too short to contain a swing.")

    torso = torso_length(s)
    hands = weighted_point(s, ["left_wrist", "right_wrist"])
    known = ~np.isnan(hands[:, 0])
    if known.mean() < 0.5:
        raise NoSwingFound("The hands were not found in most frames.")
    idx = np.arange(s.frame_count)
    # Fill remaining holes for detection only; confidence uses visibility, which is 0 there.
    hx = np.interp(idx, idx[known], hands[known, 0]) / torso
    hy = np.interp(idx, idx[known], hands[known, 1]) / torso

    vy = np.gradient(hy)  # positive = hands moving down (image y grows downward)
    found = None
    for anchor in _anchor_candidates(vy):
        found = _swing_from_anchor(hy, s.t, anchor)
        if found is not None:
            break
    if found is None:
        raise NoSwingFound(
            "No full swing was found: the hands never rose clearly above impact height before a fast downswing."
        )
    impact, highest, top = found
    swing_range = hy[impact] - hy[top]

    notes: list[dict] = []
    low_band = hy[top] + 0.7 * swing_range
    low = np.array([f for f in range(top) if hy[f] >= low_band])
    address, address_conf = (int(low[0]) if len(low) else 0), 0.4
    rest_end = address
    if len(low):
        pts = np.stack([hx[low], hy[low]], axis=1)
        held = (np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2) <= ADDRESS_RADIUS).sum(axis=1)
        if held.max() >= MIN_ADDRESS_FRAMES:
            rest = pts[int(np.argmax(held))]
            at_rest = [f for f in range(top) if np.hypot(hx[f] - rest[0], hy[f] - rest[1]) <= ADDRESS_RADIUS]
            # Last period at rest; a frame or two of jitter outside the radius does not end it.
            run_end = run_start = at_rest[-1]
            for f in reversed(at_rest[:-1]):
                if run_start - f > 3:
                    break
                run_start = f
            address, address_conf, rest_end = (run_start + run_end) // 2, 1.0, run_end
    if address_conf < 1.0:
        notes.append(
            {
                "code": "address_not_still",
                "message": "The clip seems to start after the golfer began moving, so the address position is a guess.",
            }
        )
    takeaway = min(rest_end + 1, top)
    rest_start = run_start if address_conf == 1.0 else address

    events = {
        "address": PhaseEvent("address", address, "middle_of_last_rest_at_held_hand_position", address_conf),
        "takeaway": PhaseEvent("takeaway", takeaway, "hands_leave_address_position", 0.8 * address_conf),
        "top": PhaseEvent("top", top, "hands_start_down_from_highest_point", 1.0),
        "impact": PhaseEvent(
            "impact", impact, "lowest_hands_after_fastest_downswing", 1.0, temporal_resolution_factor(s.fps)
        ),
    }

    after = hy[impact:]
    if hy[impact] - after.min() >= 0.3:
        finish = impact + int(np.argmax(after <= after.min() + FINISH_TOLERANCE))
        cut_off = finish >= s.frame_count - 2
        events["finish"] = PhaseEvent("finish", finish, "hands_reach_highest_follow_through", 0.6 if cut_off else 1.0)
        if cut_off:
            notes.append(
                {
                    "code": "finish_at_end_of_clip",
                    "message": "The clip ends during the follow-through, so the finish may be later than shown.",
                }
            )
    else:
        notes.append({"code": "finish_not_found", "message": "No follow-through was found after impact."})

    for event in events.values():
        visible = hand_visibility_score(s, event.frame)
        event.position_confidence = round(event.confidence * visible, 2)
        event.confidence = round(event.confidence * event.timing_factor * visible, 2)

    downswing_s = float(s.t[impact] - s.t[top])
    slow = downswing_s > SLOW_MOTION_DOWNSWING_S
    if slow:
        notes.append(
            {
                "code": "slow_motion_suspected",
                "message": (
                    f"The downswing takes {downswing_s:.2f} s of video time, but real downswings take about "
                    "0.25 to 0.45 s. The clip was probably filmed in slow motion. Phone slow motion often changes "
                    "speed within the clip, so all timing values (durations and tempo ratio) are left out."
                ),
            }
        )

    # About one frame of a normal 30 fps phone video either side of impact.
    k = max(1, int(round(s.fps / 30)))
    windows = {
        "address": (rest_start, rest_end),
        "top": (highest, top),
        "impact": (max(impact - k, 0), min(impact + k, s.frame_count - 1)),
    }
    return Phases(events=events, torso_px=torso, notes=notes, slow_motion_suspected=slow, windows=windows)
