"""A traffic-light rating for each measurement, using the same limits as the feedback rules.

Adds to each measurement dict:
  * ``rating``: "good", "watch" (slightly off), "bad" (clearly off), or None for a measurement
    without a rule (none at the moment; spine angle at top/impact needs the address angle);
  * ``typical``: what good swings show, in words, or None.

Low confidence: a clear fault is only "watch", as in the feedback rules. The frontend says the
confidence is low next to the rating.

Ranges not used by the feedback rules (durations, face-on shoulder tilt and head shift at impact)
are common coaching ranges for 2D video, not measured on reference swings like the others.
"""

from __future__ import annotations

from typing import Callable

from .feedback import (
    HAND_PATH_INSIDE,
    HAND_PATH_OUTSIDE,
    HEAD_DROP,
    HEAD_LIFT,
    KNEE_FLEX_RANGE,
    LEAD_ARM_BEND,
    ON_PLANE_MAX,
    PAST_PARALLEL,
    RELIABLE,
    REAR_HIP_TOWARD_BALL,
    SHAFT_INSIDE_TOES_CLEAR,
    SHAFT_OUTSIDE,
    SPINE_ADDRESS_RANGE,
    SPINE_LOSS,
    STANCE_RANGE,
    SWAY,
    TEMPO_RANGE,
)

Rule = Callable[[float], str]


def _range(lo: float, hi: float, slack_lo: float, slack_hi: float) -> Rule:
    """Good inside [lo, hi]; watch within the slack outside it; bad beyond."""

    def rate(v: float) -> str:
        if lo <= v <= hi:
            return "good"
        return "watch" if lo - slack_lo <= v <= hi + slack_hi else "bad"

    return rate


def _at_most(mild: float, clear: float) -> Rule:
    return lambda v: "good" if v <= mild else ("watch" if v <= clear else "bad")


def _head_height(v: float) -> str:
    if v < -HEAD_DROP[1] or v > HEAD_LIFT[1]:
        return "bad"
    if v < -HEAD_DROP[0] or v > HEAD_LIFT[0]:
        return "watch"
    return "good"


def _hand_path(v: float) -> str:
    if v > HAND_PATH_OUTSIDE[1] or v < -HAND_PATH_INSIDE[1]:
        return "bad"
    if v > HAND_PATH_OUTSIDE[0] or v < -HAND_PATH_INSIDE[0]:
        return "watch"
    return "good"


def _shaft_points(toes: float | None) -> Rule:
    def rate(v: float) -> str:
        if v > SHAFT_OUTSIDE[1] or (toes is not None and v < toes - SHAFT_INSIDE_TOES_CLEAR):
            return "bad"
        if v > ON_PLANE_MAX or (toes is not None and v < toes):
            return "watch"
        return "good"

    return rate


def _rules(toes: float | None) -> dict[str, tuple[Rule, str]]:
    deg = "°"
    spine_lo, spine_hi = SPINE_ADDRESS_RANGE
    knee_lo, knee_hi = KNEE_FLEX_RANGE
    return {
        "tempo_ratio": (
            lambda v: "good" if TEMPO_RANGE[0] <= v <= TEMPO_RANGE[1] else "watch",
            f"{TEMPO_RANGE[0]:.1f} to {TEMPO_RANGE[1]:.0f} : 1 (about 3 : 1)",
        ),
        "spine_angle_address": (_range(spine_lo, spine_hi, 6, 6), f"{spine_lo:.0f}{deg} to {spine_hi:.0f}{deg}"),
        "trail_knee_flex_address": (_range(knee_lo, knee_hi, 6, 8), f"{knee_lo:.0f}{deg} to {knee_hi:.0f}{deg}"),
        "spine_angle_change_impact": (
            lambda v: _at_most(*SPINE_LOSS)(-v),
            f"less than {SPINE_LOSS[0]:.0f}{deg} more upright",
        ),
        "rear_hip_toward_ball_impact": (
            _at_most(*REAR_HIP_TOWARD_BALL),
            f"less than {REAR_HIP_TOWARD_BALL[0]:.0f}% toward the ball",
        ),
        "head_rise_top": (_head_height, f"between {HEAD_DROP[0]:.0f}% lower and {HEAD_LIFT[0]:.0f}% higher"),
        "head_rise_impact": (_head_height, f"between {HEAD_DROP[0]:.0f}% lower and {HEAD_LIFT[0]:.0f}% higher"),
        "hip_shift_top": (lambda v: _at_most(*SWAY)(-v), f"less than {SWAY[0]:.0f}% away from the target"),
        "head_shift_top": (lambda v: _at_most(*SWAY)(-v), f"less than {SWAY[0]:.0f}% away from the target"),
        "hip_shift_impact": (
            lambda v: "good" if v >= 5 else ("watch" if v >= 0 else "bad"),
            "at least 5% toward the target",
        ),
        "lead_arm_bend_top": (_at_most(*LEAD_ARM_BEND), f"less than {LEAD_ARM_BEND[0]:.0f}{deg} of bend"),
        "stance_width_address": (
            lambda v: "good" if STANCE_RANGE[0] <= v <= STANCE_RANGE[1] else "watch",
            f"{STANCE_RANGE[0]:.2f} to {STANCE_RANGE[1]:.1f} × shoulder width",
        ),
        "shaft_points_downswing": (
            _shaft_points(toes),
            "between your toes and the ball"
            + (f" ({toes:.0f}% to {ON_PLANE_MAX:.0f}%)" if toes is not None else f" (up to {ON_PLANE_MAX:.0f}%)"),
        ),
        "hand_path_downswing": (
            _hand_path,
            f"between {HAND_PATH_INSIDE[0]:.0f}% inside and {HAND_PATH_OUTSIDE[0]:.0f}% outside",
        ),
        # Real-time durations (left out for slow motion). The backswing starts when the HANDS move,
        # a little after the club head, so it reads shorter than a club-based timing.
        "backswing_duration": (_range(0.55, 1.2, 0.13, 0.3), "0.55 to 1.2 s"),
        # Pros take about 0.25 s, 10-25 handicaps about 0.4 s (Grober 2010).
        "downswing_duration": (_range(0.22, 0.35, 0.04, 0.1), "0.22 to 0.35 s"),
        # Face-on. Shoulder tilt: positive = lead shoulder higher (2D, from horizontal).
        "shoulder_tilt_address": (
            _range(3, 18, 5, 7),
            f"lead shoulder 3{deg} to 18{deg} higher (the trail hand sits lower on the grip)",
        ),
        "shoulder_tilt_top": (
            _range(-55, -10, 10, 10),
            f"lead shoulder 10{deg} to 55{deg} lower (the shoulders turn on a tilt, not flat)",
        ),
        # Tour average 39°, high handicaps 27.5° (GOLFTEC SwingTRU).
        "shoulder_tilt_impact": (_range(10, 45, 5, 10), f"lead shoulder 10{deg} to 45{deg} higher"),
        "head_shift_impact": (
            _range(-15, 5, 10, 7),
            "from 15% behind to 5% ahead of its address position (the head stays behind the ball)",
        ),
        "shaft_past_parallel_top": (
            lambda v: "watch" if v > PAST_PARALLEL or v < -45 else "good",
            f"from 45{deg} short of parallel to {PAST_PARALLEL:.0f}{deg} past",
        ),
    }


def _spine_vs_address(address: float) -> tuple[Rule, str]:
    """Spine angle at the top / impact: judged by how much more upright it is than at address
    (the raw angle depends on the setup), with the posture-through-impact limits."""
    deg = "\u00b0"
    return (
        lambda v: _at_most(*SPINE_LOSS)(address - v),
        f"at most {SPINE_LOSS[0]:.0f}{deg} more upright than at address ({address:.0f}{deg}), so at least "
        f"{address - SPINE_LOSS[0]:.0f}{deg}",
    )


def rate_measurements(measurements: list[dict], club: dict | None = None) -> None:
    """Add ``rating`` and ``typical`` to each measurement dict, in place."""
    rules = _rules((club or {}).get("toes_from_ball"))
    address = next((m for m in measurements if m["name"] == "spine_angle_address"), None)
    if address is not None:
        rules["spine_angle_top"] = rules["spine_angle_impact"] = _spine_vs_address(address["value"])
    for m in measurements:
        rule = rules.get(m["name"])
        if rule is None:
            m["rating"], m["typical"] = None, None
            continue
        rate, typical = rule
        rating = rate(m["value"])
        confidence = m.get("confidence", 0.0)
        if m["name"] in ("spine_angle_top", "spine_angle_impact") and address is not None:
            confidence = min(confidence, address.get("confidence", 0.0))
        if confidence < RELIABLE and rating == "bad":
            rating = "watch"
        m["rating"], m["typical"] = rating, typical
