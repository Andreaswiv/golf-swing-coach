"""The numeric limits behind the feedback rules and the ratings, in one place to review and tune.

Thresholds are set so that what good players normally do is NOT a fault. Where a published source
gives numbers (address posture, tempo, durations, face-on hip shift and shoulder tilt), the limits
follow it; the rest are calibrated so a tour player's swing (tests/fixtures) comes out without
"improve" findings. docs/RATING_SOURCES.md lists the source and evidence level for every limit.
"""

from __future__ import annotations

RELIABLE = 0.5  # measurements below this confidence are never a clear fault, nor praised
AVERAGE_TORSO_CM = 50  # shoulder-centre to hip-centre for an average adult; only used to make % readable

# Typical ranges (2D, degrees or % of torso length). (mild, clear) limits.
SPINE_ADDRESS_RANGE = (28.0, 48.0)  # pros 41.5 ± 2.9 (5-iron, Kim et al. 2018); tour ~29 with driver (GOLFTEC)
KNEE_FLEX_RANGE = (12.0, 38.0)  # pros' trail knee 24.4 ± 5.5 (Kim et al. 2018): about mean ± 2 SD
SPINE_LOSS = (12.0, 18.0)  # degrees more upright at impact than at address
REAR_HIP_TOWARD_BALL = (15.0, 25.0)  # % torso (15% ~ 7.5 cm)
HEAD_DROP = (20.0, 30.0)  # % torso lower than address (20% ~ 10 cm)
HEAD_LIFT = (8.0, 15.0)  # % torso higher than address
SWAY = (8.0, 15.0)  # % torso away from the target at the top
HIP_SHIFT_IMPACT_MIN = 5.0  # % torso toward the target at impact; below 0 the hips are behind address
LEAD_ARM_BEND = (20.0, 35.0)  # degrees of bend at the top
STANCE_RANGE = (0.85, 1.6)  # ankle distance / shoulder width
TEMPO_RANGE = (2.3, 4.0)  # backswing : downswing; pros 2.4-3.4, 10-25 handicaps 1.9-2.1 (Grober 2010)
# Club (down-the-line). Shaft pointing beyond the ball halfway down (% torso; 40% ~ 20 cm).
SHAFT_OUTSIDE = (40.0, 80.0)
# Praise only up to here (% torso beyond the ball). Good downswings point between the toes and the
# ball (tour swings measured -10 and -21); from here up to SHAFT_OUTSIDE there is no verdict.
ON_PLANE_MAX = 15.0
HAND_PATH_OUTSIDE = (10.0, 20.0)  # downswing hands outside the backswing path (% torso)
# Downswing hands under the backswing path (% torso). Slightly inside is normal and good (a tour swing
# measured 0); this is well past that.
HAND_PATH_INSIDE = (12.0, 22.0)
SHAFT_INSIDE_TOES_CLEAR = 40.0  # % torso the shaft points inside the toes before it is a clear fault
PAST_PARALLEL = 15.0  # degrees past parallel at the top (face-on) before it counts as an overswing
SHORT_OF_PARALLEL = -45.0  # degrees at the top (negative = short of parallel); shorter gets no praise


def limits_for_display() -> dict:
    """The limits the frontend draws or writes out (the tempo dial, head movement in cm)."""
    return {
        "average_torso_cm": AVERAGE_TORSO_CM,
        "tempo_good": list(TEMPO_RANGE),
        "head_drop": HEAD_DROP[0],
        "head_lift": HEAD_LIFT[0],
    }
