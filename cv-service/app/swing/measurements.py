"""2D measurements at the detected phases.

Conventions (after left-handed golfers have been mirrored):
  * lead side = "left_*" landmarks, trail side = "right_*".
  * Angles are in degrees in the image plane. They are 2D projections, not
    true 3D joint angles, and depend on where the camera stood.
  * Distances are percentages of the golfer's torso length, so they do not
    depend on resolution or how far away the camera was.
  * Directions come from the golfer's own setup, not from assumptions about
    the camera: "toward the ball" is the side the hands hang on at address
    (down-the-line), "toward the target" is the lead shoulder's side (face-on).

Robustness (what makes a value trustworthy):
  * Address and top are positions the golfer holds, so their values are the
    median over the frames held (the rest at address, the pause at the top),
    not a single frame.
  * Impact is a single instant. Its value is checked for stability: it is
    recomputed one real frame earlier and later; the more it changes, the
    lower its confidence. A value that does not depend on the exact impact
    frame is reliable even at 30 fps.

type: "measured" = read directly from keypoints.
      "estimated" = depends on detected phase timing (tempo, durations).
confidence: heuristic 0..1 = hand visibility at the phases x joint visibility x stability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np

from .phases import Phases
from .series import Series, weighted_point

SHOULDERS = ["left_shoulder", "right_shoulder"]
HIPS = ["left_hip", "right_hip"]
HEAD = ["nose", "left_ear", "right_ear"]

# Change across the impact window that drops stability to its floor.
STABILITY_TOLERANCE = {"deg": 8.0, "% torso": 10.0, "ratio": 0.3}
STABILITY_FLOOR = 0.3


@dataclass
class Measurement:
    name: str
    phase: str | None
    frame_index: int
    value: float
    unit: str
    type: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


FrameFn = Callable[[int], float]


class _Context:
    def __init__(self, s: Series, phases: Phases) -> None:
        self.s = s
        self.p = phases
        self.torso = phases.torso_px
        self.shoulder_mid = weighted_point(s, SHOULDERS)
        self.hip_mid = weighted_point(s, HIPS)
        self.head = weighted_point(s, HEAD)
        self.hands = weighted_point(s, ["left_wrist", "right_wrist"])

    def window(self, phase: str) -> list[int]:
        lo, hi = self.p.windows.get(phase, (self.p.frame(phase), self.p.frame(phase)))
        return list(range(lo, hi + 1))

    def visibility_score(self, joints: list[str], frames: list[int]) -> float:
        v = np.mean([self.s.visibility(j)[f] for j in joints for f in frames])
        return float(np.clip((v - 0.3) / 0.5, 0.0, 1.0))

    def held_value(self, phase: str, fn: FrameFn) -> float:
        vals = np.array([fn(f) for f in self.window(phase)], dtype=float)
        vals = vals[np.isfinite(vals)]
        return float(np.median(vals)) if len(vals) else float("nan")

    def make(
        self,
        name: str,
        phase: str,
        fn: FrameFn,
        unit: str,
        joints: list[str],
        relative_to_address: bool = False,
    ) -> Measurement | None:
        frame = self.p.frame(phase)
        if frame is None or (relative_to_address and self.p.frame("address") is None):
            return None
        base = self.held_value("address", fn) if relative_to_address else 0.0

        stability = 1.0
        if phase == "impact":
            vals = np.array([fn(f) for f in self.window("impact")], dtype=float)
            value = fn(frame)
            if np.isfinite(vals).all():
                spread = float(vals.max() - vals.min())
                stability = max(STABILITY_FLOOR, 1.0 - spread / STABILITY_TOLERANCE[unit])
        else:
            value = self.held_value(phase, fn)
        value -= base
        if not np.isfinite(value):
            return None

        phases = ["address", phase] if relative_to_address else [phase]
        frames = [f for ph in phases for f in self.window(ph)]
        conf = min(self.p.events[ph].position_confidence for ph in phases)
        conf *= self.visibility_score(joints, frames) * stability
        digits = 2 if unit == "ratio" else 1
        return Measurement(name, phase, int(frame), round(float(value), digits), unit, "measured", round(conf, 2))


def _forward_bend(low: np.ndarray, high: np.ndarray, direction: float) -> float:
    """Angle of the low->high line from vertical; positive = leaning toward ``direction`` (+1 = +x)."""
    v = high - low
    return float(np.degrees(np.arctan2(v[0] * direction, -v[1])))


def _joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    u, w = a - b, c - b
    cos = np.dot(u, w) / (np.linalg.norm(u) * np.linalg.norm(w))
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def _sign(value: float) -> float:
    return 1.0 if value >= 0 else -1.0


def _timing(c: _Context, phases: Phases) -> list[Measurement]:
    f, s = phases.frame, c.s
    t_take, t_top, t_imp = f("takeaway"), f("top"), f("impact")
    back, down = s.t[t_top] - s.t[t_take], s.t[t_imp] - s.t[t_top]
    # Slow-motion clips are left out entirely: phone slow motion often ramps speed within the
    # clip, which distorts the tempo ratio as well as the durations.
    if down <= 0 or back <= 0 or phases.slow_motion_suspected:
        return []
    conf = round(min(phases.confidence(n) for n in ("takeaway", "top", "impact")), 2)
    return [
        Measurement("tempo_ratio", "top", int(t_top), round(back / down, 2), "ratio", "estimated", conf),
        Measurement("backswing_duration", "top", int(t_top), round(back, 2), "s", "estimated", conf),
        Measurement("downswing_duration", "impact", int(t_imp), round(down, 2), "s", "estimated", conf),
    ]


def measure(s: Series, phases: Phases, camera_angle: str) -> list[Measurement]:
    c = _Context(s, phases)
    out: list[Measurement | None] = list(_timing(c, phases))
    point = s.point

    if camera_angle == "down_the_line":
        toward_ball = _sign(c.held_value("address", lambda f: c.hands[f, 0] - c.hip_mid[f, 0]))

        def spine(f):
            return _forward_bend(c.hip_mid[f], c.shoulder_mid[f], toward_ball)

        def rear_hip(f):
            # The hip joint farthest from the ball: a stand-in for the backside line coaches use.
            # The hip centre would move toward the ball just from the hips rotating open.
            return min(point("left_hip")[f, 0] * toward_ball, point("right_hip")[f, 0] * toward_ball) / c.torso * 100

        def head_height(f):
            return -c.head[f, 1] / c.torso * 100  # image y grows downward

        def trail_knee_flex(f):
            return 180.0 - _joint_angle(point("right_hip")[f], point("right_knee")[f], point("right_ankle")[f])

        trunk = SHOULDERS + HIPS
        for phase in ("address", "top", "impact"):
            out.append(c.make(f"spine_angle_{phase}", phase, spine, "deg", trunk))
        out.append(c.make("spine_angle_change_impact", "impact", spine, "deg", trunk, relative_to_address=True))
        out.append(c.make("trail_knee_flex_address", "address", trail_knee_flex, "deg", ["right_hip", "right_knee", "right_ankle"]))
        out.append(c.make("rear_hip_toward_ball_impact", "impact", rear_hip, "% torso", HIPS, relative_to_address=True))
        for phase in ("top", "impact"):
            out.append(c.make(f"head_rise_{phase}", phase, head_height, "% torso", HEAD, relative_to_address=True))

    elif camera_angle == "face_on":
        toward_target = _sign(c.held_value("address", lambda f: point("left_shoulder")[f, 0] - point("right_shoulder")[f, 0]))

        def tilt(f):
            lead, trail = point("left_shoulder")[f], point("right_shoulder")[f]
            return float(np.degrees(np.arctan2(trail[1] - lead[1], abs(lead[0] - trail[0]))))

        def hip_x(f):
            return c.hip_mid[f, 0] * toward_target / c.torso * 100

        def head_x(f):
            return c.head[f, 0] * toward_target / c.torso * 100

        def lead_arm_bend(f):
            return 180.0 - _joint_angle(point("left_shoulder")[f], point("left_elbow")[f], point("left_wrist")[f])

        def stance(f):
            shoulders = np.linalg.norm(point("left_shoulder")[f] - point("right_shoulder")[f])
            ankles = np.linalg.norm(point("left_ankle")[f] - point("right_ankle")[f])
            return ankles / shoulders if shoulders > 0 else float("nan")

        for phase in ("address", "top", "impact"):
            out.append(c.make(f"shoulder_tilt_{phase}", phase, tilt, "deg", SHOULDERS))
        for phase in ("top", "impact"):
            out.append(c.make(f"hip_shift_{phase}", phase, hip_x, "% torso", HIPS, relative_to_address=True))
            out.append(c.make(f"head_shift_{phase}", phase, head_x, "% torso", HEAD, relative_to_address=True))
        out.append(c.make("lead_arm_bend_top", "top", lead_arm_bend, "deg", ["left_shoulder", "left_elbow", "left_wrist"]))
        out.append(c.make("stance_width_address", "address", stance, "ratio", ["left_ankle", "right_ankle", *SHOULDERS]))

    return [m for m in out if m is not None]
