"""Club measurements from the per-frame club boxes (shaft, head, hands) in the keypoints file.

Everything is in the same pixel space as ``Series`` (mirrored for left-handed golfers),
and distances are in % of torso length.

Shaft line per frame: grip -> club head.
  * grip  = centre of the detector's "hands" box (it sits on the grip; MediaPipe's wrist
            point is a few centimetres up the forearm), else the visibility-weighted wrists.
  * head  = centre of the "head" box, else the far end of the shaft box (the box diagonal
            whose corner is nearest the grip).

Swing plane (down-the-line): the shaft line at address, from the ball through the grip,
extended; drawn on the video and used as the reference for the hand path. "Outside" is the side
away from the golfer's hips. "Address" for the club is where the CLUB HEAD rested longest before
the takeaway, with the club pointing down to near foot height (club_address). Not the hands' last
still moment: the club head starts back before the hands, and some golfers settle, waggle or
press forward after a long wait at address. No plane when no believable address is found.

Over the top is judged the way coaches do from behind: where the SHAFT points halfway down.
Extended to the ground it should point between the toes and the ball; a steep, over-the-top
downswing points beyond the ball. (Distance of the hands or club head from the plane line is
not used: at hip height that line runs well in front of the body, so even tour players' hands
sit "above" it. Measured on a tour swing.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .measurements import Measurement
from .phases import NoSwingFound, Phases, torso_length
from .series import Series, fill_gaps, weighted_point

MIN_CONF = 0.5
MAX_GAP = 2  # frames of missing club detection bridged by interpolation
# Plausibility (torso lengths): see build_club_series.
HANDS_MAX_FROM_WRISTS = 0.6
SHAFT_MAX_FROM_GRIP = 0.8  # the hands cover the top of the shaft, so its box often stops short of the grip
MAX_CLUB_TORSO = 2.6  # a driver is ~2.3 torso lengths for an adult; no club is longer
MAX_LENGTH_FACTOR = 1.25
HEAD_STILL_RADIUS = 0.1  # torso lengths: club head within this of its address spot counts as still
# Address checks (see club_address). Torso lengths, degrees.
MIN_ADDRESS_CLUB_FRAMES = 3
CLEAR_CORNER_RATIO = 0.25  # see ClubSeries.corner_ratio
ADDRESS_HEAD_BELOW_HANDS = 0.3
ADDRESS_HEAD_FROM_FEET = 0.8
ADDRESS_ANGLE = (25.0, 80.0)  # shaft up from horizontal, as seen from behind; irons ~55-65, driver ~45


@dataclass
class ClubSeries:
    grip: np.ndarray  # (F, 2) px
    head: np.ndarray  # (F, 2) px, NaN where unknown
    head_conf: np.ndarray  # (F,) detector confidence of the head end (0 if estimated from the shaft box)
    shaft_found: np.ndarray  # (F,) bool
    checked: np.ndarray  # (F,) bool: the club detector ran on this frame (only around the swing)
    share: dict[str, float]  # share of the CHECKED frames where each part was found (and kept)
    rejected: np.ndarray  # (F,) bool: a detection in this frame was thrown out as physically impossible
    # (F,) for a head inferred from the shaft box: distance from the grip to the nearest box corner
    # over the box diagonal. Small = the grip sits at a corner, so the shaft direction is clear.
    corner_ratio: np.ndarray
    length_px: float  # the club's full length as seen in this video (grip to head), px


def _center(box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _distance_to_box(p: np.ndarray, corners: list[tuple[float, float]]) -> float:
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    dx = max(min(xs) - p[0], 0.0, p[0] - max(xs))
    dy = max(min(ys) - p[1], 0.0, p[1] - max(ys))
    return float(np.hypot(dx, dy))


def build_club_series(payload: dict, s: Series) -> ClubSeries | None:
    """Per-frame grip and club head, keeping only detections that are physically possible.

    The detector sometimes finds a "shaft" in straight lines elsewhere (power lines, nets, the
    edge of the mat) and the club head in round things. The club is a rigid stick held in the
    hands, so:
      * the hands box must be at the wrists;
      * the shaft box must reach the grip (the shaft starts in the hands);
      * the club can look shorter on video (pointing toward the camera) but never longer than it
        is: grip to head may not exceed its length in this video (measured from the reliable
        frames) by more than MAX_LENGTH_FACTOR.
    """
    frames = payload["frames"]
    if not any("club" in f for f in frames):
        return None
    w, h = s.width, s.height
    n = len(frames)
    try:
        torso = torso_length(s)
    except NoSwingFound:
        return None
    grip = np.full((n, 2), np.nan)
    head = np.full((n, 2), np.nan)
    head_conf = np.zeros(n)
    shaft_found = np.zeros(n, dtype=bool)
    rejected = np.zeros(n, dtype=bool)
    corner_ratio = np.full(n, np.nan)
    checked = np.array(["club" in f for f in frames])

    def px(x, y):
        return (w - x * w if s.mirrored else x * w), y * h

    wrists = weighted_point(s, ["left_wrist", "right_wrist"])
    hands_ok = np.zeros(n, dtype=bool)
    head_boxes: list = [None] * n
    shaft_boxes: list = [None] * n
    for k, f in enumerate(frames):
        parts = {p: b for p, b in (f.get("club") or {}).items() if b[4] >= MIN_CONF}
        if "hands" in parts:
            c = np.array(px(*_center(parts["hands"])))
            if np.isnan(wrists[k, 0]) or np.hypot(*(c - wrists[k])) <= HANDS_MAX_FROM_WRISTS * torso:
                grip[k], hands_ok[k] = c, True
            else:
                rejected[k] = True
        if not hands_ok[k]:
            grip[k] = wrists[k]
        if "head" in parts:
            head_boxes[k] = (np.array(px(*_center(parts["head"]))), parts["head"][4])
        if "shaft" in parts and not np.isnan(grip[k, 0]):
            b = parts["shaft"]
            corners = [px(b[0], b[1]), px(b[2], b[3]), px(b[0], b[3]), px(b[2], b[1])]
            if _distance_to_box(grip[k], corners) <= SHAFT_MAX_FROM_GRIP * torso:
                shaft_boxes[k] = ((corners[0], corners[1]), (corners[2], corners[3]))
                shaft_found[k] = True
            else:
                rejected[k] = True

    # The club's length in this video: the long end of grip-to-head distances where both the hands
    # and the head were found (shorter = the club points toward or away from the camera).
    lengths = [
        np.hypot(*(head_boxes[k][0] - grip[k])) for k in range(n) if hands_ok[k] and head_boxes[k] is not None
    ]
    lengths = [x for x in lengths if x <= MAX_CLUB_TORSO * torso]
    length_px = float(np.percentile(lengths, 90)) if len(lengths) >= 5 else MAX_CLUB_TORSO * torso
    max_len = MAX_LENGTH_FACTOR * length_px

    for k in range(n):
        if np.isnan(grip[k, 0]):
            continue
        if head_boxes[k] is not None:
            centre, conf = head_boxes[k]
            if np.hypot(*(centre - grip[k])) <= max_len:
                head[k], head_conf[k] = centre, conf
                continue
            rejected[k] = True
        if shaft_boxes[k] is not None:
            # Far end of the shaft: the diagonal with a corner nearest the grip, its other corner.
            best = None
            for a, b in shaft_boxes[k]:
                for near, far in ((a, b), (b, a)):
                    d = np.hypot(near[0] - grip[k, 0], near[1] - grip[k, 1])
                    if best is None or d < best[0]:
                        best = (d, far)
            if np.hypot(best[1][0] - grip[k, 0], best[1][1] - grip[k, 1]) <= max_len:
                head[k], head_conf[k] = best[1], 0.0
                (a, b), _ = shaft_boxes[k]
                diag = np.hypot(b[0] - a[0], b[1] - a[1])
                corner_ratio[k] = best[0] / diag if diag > 0 else np.nan
            else:
                shaft_found[k] = False
                rejected[k] = True

    for arr in (grip, head):
        for c in range(2):
            arr[:, c] = fill_gaps(arr[:, c], MAX_GAP)
    n_checked = max(int(checked.sum()), 1)
    share = {
        "shaft": round(int(shaft_found.sum()) / n_checked, 3),
        "head": round(int((head_conf > 0).sum()) / n_checked, 3),
        "hands": round(int(hands_ok.sum()) / n_checked, 3),
    }
    return ClubSeries(
        grip=grip, head=head, head_conf=head_conf, shaft_found=shaft_found, checked=checked, share=share,
        rejected=rejected, length_px=length_px, corner_ratio=corner_ratio,
    )


def club_track(c: ClubSeries, s: Series) -> list:
    """Per frame, the club the analysis used, for drawing: [grip x, grip y, head x, head y, head found]
    in original normalised image coordinates (not mirrored), or None where there is no club."""
    out: list = []
    for k in range(len(c.checked)):
        g, hd = c.grip[k], c.head[k]
        if not c.checked[k] or np.isnan(g).any() or np.isnan(hd).any():
            out.append(None)
            continue

        def norm(p):
            x = (s.width - p[0]) if s.mirrored else p[0]
            return [round(float(x / s.width), 4), round(float(p[1] / s.height), 4)]

        out.append(norm(g) + norm(hd) + [1 if c.head_conf[k] > 0 else 0])
    return out


def _median_point(arr: np.ndarray, frames: list[int]) -> np.ndarray:
    pts = arr[frames]
    pts = pts[~np.isnan(pts[:, 0])]
    return np.median(pts, axis=0) if len(pts) else np.array([np.nan, np.nan])


class Plane:
    """Address shaft line; signed distance to it, positive = outside (away from the hips)."""

    def __init__(self, ball: np.ndarray, grip: np.ndarray, inside_point: np.ndarray, torso: float) -> None:
        self.ball, self.grip, self.torso = ball, grip, torso
        d = grip - ball
        self.unit = d / np.linalg.norm(d)
        self.inside_sign = np.sign(self._cross(inside_point)) or 1.0

    def _cross(self, p: np.ndarray) -> float:
        v = p - self.ball
        return float(self.unit[0] * v[1] - self.unit[1] * v[0])

    def outside(self, p: np.ndarray) -> float:
        """Distance outside (above) the plane in % torso; negative = inside (under)."""
        return -self.inside_sign * self._cross(p) / self.torso * 100


@dataclass
class AddressSetup:
    """The club at address, in Series pixels: where the plane line starts and runs through."""

    frames: list[int]
    ball: np.ndarray  # club head at rest = the ball
    grip: np.ndarray
    hip: np.ndarray
    toes: np.ndarray


def club_address(c: ClubSeries, s: Series, takeaway: int, torso: float) -> AddressSetup | None:
    """The club at rest at address, or None when it cannot be found reliably (then: no plane).

    Only frames up to the takeaway (never the top: in slow motion the club rests longest there),
    where the club points down from the hands to near foot height. Of those, the spot the club
    head held longest. The result must look like an address: shaft between ADDRESS_ANGLE degrees
    from horizontal, the head further from the hips than the hands. A wrong plane is worse than
    none, because the over-the-top and inside-out verdicts are measured against it.
    """
    feet = weighted_point(s, ["left_ankle", "right_ankle", "left_foot_index", "right_foot_index"])
    hips = weighted_point(s, ["left_hip", "right_hip"])
    last = min(takeaway, len(c.checked) - 1)
    frames = []
    for k in range(last + 1):
        head, grip = c.head[k], c.grip[k]
        if not c.checked[k] or np.isnan(head).any() or np.isnan(grip).any() or np.isnan(feet[k]).any():
            continue
        pointing_down = head[1] - grip[1] >= ADDRESS_HEAD_BELOW_HANDS * torso
        near_feet = abs(head[1] - feet[k, 1]) <= ADDRESS_HEAD_FROM_FEET * torso
        if pointing_down and near_feet:
            frames.append(k)
    if len(frames) < MIN_ADDRESS_CLUB_FRAMES:
        return None

    pts = c.head[frames]
    radius = HEAD_STILL_RADIUS * torso
    near = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2) <= radius
    held = near.sum(axis=1)
    if held.max() < MIN_ADDRESS_CLUB_FRAMES:
        return None
    spot = np.median(pts[near[int(np.argmax(held))]], axis=0)
    frames = [k for k, p in zip(frames, pts) if np.hypot(*(p - spot)) <= radius]

    setup = AddressSetup(
        frames=frames,
        ball=_median_point(c.head, frames),
        grip=_median_point(c.grip, frames),
        hip=_median_point(hips, frames),
        toes=_median_point(weighted_point(s, ["left_foot_index", "right_foot_index"]), frames),
    )
    if np.isnan(setup.ball).any() or np.isnan(setup.grip).any() or np.isnan(setup.hip).any():
        return None
    shaft = setup.grip - setup.ball
    angle = np.degrees(np.arctan2(-shaft[1], abs(shaft[0])))  # up from horizontal
    if not ADDRESS_ANGLE[0] <= angle <= ADDRESS_ANGLE[1]:
        return None
    if abs(setup.ball[0] - setup.hip[0]) <= abs(setup.grip[0] - setup.hip[0]):
        return None  # the club head must be further out from the body than the hands
    return setup


def mid_downswing_frame(grip: np.ndarray, top: int, impact: int) -> int:
    """First frame after the top where the grip has come halfway down to its impact height."""
    half = (grip[top, 1] + grip[impact, 1]) / 2
    for f in range(top, impact + 1):
        if grip[f, 1] >= half:
            return f
    return (top + impact) // 2


def measure_club(c: ClubSeries, s: Series, phases: Phases, camera_angle: str) -> tuple[list[Measurement], dict]:
    """Club measurements plus a summary for the frontend (plane line in original image coordinates)."""
    out: list[Measurement] = []
    info: dict = {
        "tracked": True,
        "found_share": c.share,
        "frames_checked": int(c.checked.sum()),
        "frames_total": len(c.checked),
        "rejected_frames": int(c.rejected.sum()),
        "track": club_track(c, s),
        "plane": None,
    }
    torso = phases.torso_px
    f = phases.frame
    top, impact = f("top"), f("impact")

    def conf(frames: list[int], base: float) -> float:
        found = np.mean([c.shaft_found[k] for k in frames]) if frames else 0.0
        head = np.mean([min(1.0, c.head_conf[k] / 0.8) if c.head_conf[k] else 0.6 for k in frames]) if frames else 0.0
        return round(float(base * found * head), 2)

    if camera_angle == "down_the_line" and top is not None and impact is not None:
        setup = club_address(c, s, f("takeaway"), torso)
        if setup is not None:
            ball, hip0, toes, address_frames = setup.ball, setup.hip, setup.toes, setup.frames
            plane = Plane(ball, setup.grip, hip0, torso)
            info["plane"] = _plane_for_display(plane, s)
            base = min(phases.events["address"].position_confidence, phases.events["top"].position_confidence)
            plane_conf = conf(address_frames, base)

            mid = mid_downswing_frame(c.grip, top, impact)
            points = _shaft_points_downswing(c, ball, hip0, torso, top, impact)
            if points is not None:
                value, frames = points
                info["toes_from_ball"] = (
                    None if np.isnan(toes).any() else round(float((toes[0] - ball[0]) * np.sign(ball[0] - hip0[0]) / torso * 100), 1)
                )
                out.append(
                    Measurement("shaft_points_downswing", "downswing", int(mid), round(value, 1), "% torso", "measured",
                                round(min(plane_conf, conf(frames, base)), 2))
                )

            path = _hand_path_difference(c.grip, plane, f("takeaway"), top, impact)
            if path is not None:
                out.append(
                    Measurement("hand_path_downswing", "downswing", int(mid), round(path, 1), "% torso", "measured",
                                round(plane_conf * min(1.0, phases.events["impact"].position_confidence + 0.2), 2))
                )

    elif camera_angle == "face_on" and top is not None:
        toward_target = 1.0 if (s.point("left_shoulder")[f("address"), 0] - s.point("right_shoulder")[f("address"), 0]) >= 0 else -1.0
        lo, hi = phases.windows["top"]
        frames = list(range(lo, hi + 1))
        angles = []
        for k in frames:
            v = c.head[k] - c.grip[k]
            if not np.isnan(v).any() and np.hypot(*v) > 1:
                angles.append(float(np.degrees(np.arctan2(v[1], v[0] * toward_target))))
        if angles:
            out.append(
                Measurement("shaft_past_parallel_top", "top", int(top), round(float(np.median(angles)), 1), "deg",
                            "estimated", conf(frames, phases.events["top"].position_confidence))
            )
    return out, info


def _shaft_points_downswing(
    c: ClubSeries, ball: np.ndarray, hip: np.ndarray, torso: float, top: int, impact: int
) -> tuple[float, list[int]] | None:
    """Where the shaft points on the ground in the middle of the downswing.

    The shaft line (club head -> grip) is extended to the ball's height. Result: % torso beyond
    the ball, measured away from the golfer (positive = outside the ball: steep / over the top;
    negative = between the ball and the golfer: on plane or shallow).

    Only the middle of the descent is used (hands 30-70% of the way down), and only frames where
    the shaft is at least 45 degrees from horizontal: when it gets flatter, small angle errors move
    the ground point a long way. The club head is usually a blur here; then the shaft box gives the
    direction, if the grip sits at one of its corners (otherwise either diagonal could be the shaft).
    """
    y_top, y_imp = c.grip[top, 1], c.grip[impact, 1]
    if np.isnan(y_top) or np.isnan(y_imp) or y_imp <= y_top:
        return None
    away = np.sign(ball[0] - hip[0]) or 1.0
    vals, used = [], []
    for k in range(top, impact + 1):
        g, h = c.grip[k], c.head[k]
        if np.isnan(g).any() or np.isnan(h).any():
            continue
        progress = (g[1] - y_top) / (y_imp - y_top)
        v = g - h  # head -> grip: the butt end points at the ground in the downswing
        if not 0.3 <= progress <= 0.7 or v[1] <= 0:
            continue
        steepness = np.degrees(np.arctan2(v[1], abs(v[0])))
        if steepness < 45:
            continue
        if c.head_conf[k] == 0 and not c.corner_ratio[k] <= CLEAR_CORNER_RATIO:
            continue  # head inferred from a shaft box whose direction is ambiguous (or interpolated)
        x = h[0] + (ball[1] - h[1]) / v[1] * v[0]
        vals.append((x - ball[0]) * away / torso * 100)
        used.append(k)
    if len(vals) < 2:
        return None
    return float(np.clip(np.median(vals), -300, 300)), used


def _hand_path_difference(grip: np.ndarray, plane: Plane, takeaway: int, top: int, impact: int) -> float | None:
    """How far outside the backswing path the hands come down, in % torso (positive = outside).

    Compared at the same hand heights, over the middle half of the height range between the
    impact and top positions (where an over-the-top loop shows; near the top and bottom the
    two paths meet anyway).
    """
    y_top, y_imp = grip[top, 1], grip[impact, 1]
    if any(np.isnan(v) for v in (y_top, y_imp)) or y_imp - y_top <= 0:
        return None
    heights = np.linspace(y_top + 0.25 * (y_imp - y_top), y_top + 0.75 * (y_imp - y_top), 9)

    def outside_at(frames: range) -> np.ndarray:
        pts = grip[list(frames)]
        ok = ~np.isnan(pts[:, 0])
        pts = pts[ok]
        if len(pts) < 3:
            return np.full(len(heights), np.nan)
        order = np.argsort(pts[:, 1])
        dist = np.array([plane.outside(p) for p in pts[order]])
        return np.interp(heights, pts[order, 1], dist, left=np.nan, right=np.nan)

    back = outside_at(range(takeaway, top + 1))
    down = outside_at(range(top, impact + 1))
    diff = down - back
    diff = diff[~np.isnan(diff)]
    return float(np.mean(diff)) if len(diff) >= 3 else None


def _plane_for_display(plane: Plane, s: Series) -> dict:
    """Two points on the plane line in ORIGINAL normalised image coordinates (undo mirroring)."""
    far = plane.ball + plane.unit * 3.5 * plane.torso  # extend well past the grip

    def norm(p):
        x = (s.width - p[0]) if s.mirrored else p[0]
        return [round(float(x / s.width), 4), round(float(p[1] / s.height), 4)]

    return {"from": norm(plane.ball), "to": norm(far)}
