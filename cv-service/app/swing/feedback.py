"""Rules engine: measurements -> readable feedback.

Every sentence is generated from a measurement with a fixed template, so the
feedback can never claim something the numbers do not show.

Thresholds are set so that what good players normally do is NOT a fault.
3D studies of tour players show, from address to impact, roughly 5-12 degrees
less forward bend, the pelvis moving a few centimetres toward the ball and the
head lowering about 5-10 cm. A faulty swing goes clearly beyond that. The
limits were sanity-checked against a tour player's swing (tests/fixtures),
which must come out without "improve" findings. They are listed at the top so
they are easy to review and tune.

Each finding gets a kind:
  * "strength": within the typical range, and the data is reliable (confidence >= 0.5).
  * "improve": clearly outside the range, and the data is reliable.
  * "watch":   mildly outside the range, or clearly outside but on uncertain data.
Strengths on uncertain data are left out rather than praised.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

RELIABLE = 0.5
AVERAGE_TORSO_CM = 50  # shoulder-centre to hip-centre for an average adult; only used to make % readable

# Typical ranges (2D, degrees or % of torso length). (mild, clear) limits.
SPINE_ADDRESS_RANGE = (28.0, 48.0)
KNEE_FLEX_RANGE = (12.0, 38.0)
SPINE_LOSS = (12.0, 18.0)  # degrees more upright at impact than at address
REAR_HIP_TOWARD_BALL = (15.0, 25.0)  # % torso (15% ~ 7.5 cm)
HEAD_DROP = (20.0, 30.0)  # % torso lower than address (20% ~ 10 cm)
HEAD_LIFT = (8.0, 15.0)  # % torso higher than address
SWAY = (8.0, 15.0)  # % torso away from the target at the top
LEAD_ARM_BEND = (20.0, 35.0)  # degrees of bend at the top
STANCE_RANGE = (0.85, 1.6)  # ankle distance / shoulder width
TEMPO_RANGE = (2.3, 4.0)  # backswing : downswing
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


@dataclass
class Finding:
    code: str
    kind: str
    title: str
    detail: str
    headline: str  # lower-case clause used in the summary
    why: str | None = None
    drill: str | None = None
    phase: str | None = None
    frame_index: int | None = None
    confidence: float = 0.0
    measurements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("headline")
        return d


def _cm(pct: float) -> str:
    return f"about {abs(pct):.0f}% of your torso length (roughly {abs(pct) * AVERAGE_TORSO_CM / 100:.0f} cm for an average adult)"


def _issue_kind(clear: bool, confidence: float) -> str:
    return "improve" if clear and confidence >= RELIABLE else "watch"


class _Rules:
    def __init__(self, measurements: list[dict], club: dict | None = None) -> None:
        self.m = {x["name"]: x for x in measurements}
        self.club = club or {}
        self.out: list[Finding] = []

    def get(self, *names: str) -> list[dict] | None:
        found = [self.m.get(n) for n in names]
        return None if any(x is None for x in found) else found

    def add(self, code, kind, title, detail, headline, used, why=None, drill=None):
        conf = min(x["confidence"] for x in used)
        if kind == "strength" and conf < RELIABLE:
            return
        main = used[0]
        self.out.append(
            Finding(
                code=code,
                kind=kind,
                title=title,
                detail=detail,
                headline=headline,
                why=why,
                drill=drill,
                phase=main.get("phase"),
                frame_index=main.get("frame_index"),
                confidence=round(conf, 2),
                measurements=[x["name"] for x in used],
            )
        )

    # ---- down-the-line -------------------------------------------------------------------
    def setup_posture(self):
        found = self.get("spine_angle_address", "trail_knee_flex_address")
        if not found:
            return
        spine, knee = found
        a, k = spine["value"], knee["value"]
        lo, hi = SPINE_ADDRESS_RANGE
        klo, khi = KNEE_FLEX_RANGE
        ok = True
        if a < lo:
            ok = False
            self.add(
                "upright_setup", _issue_kind(a < lo - 6, spine["confidence"]), "You stand quite upright at address",
                f"Your upper body leans forward about {a:.0f}° from vertical. Most good setups are somewhere "
                f"between {lo:.0f}° and {hi:.0f}°.",
                "you stand quite upright at address", [spine],
                why="Standing tall leaves your arms little room to swing and makes it harder to turn your chest, "
                "so the swing tends to get flat and arm-driven.",
                drill="Hold a club across the crease of your hips and push your backside back until your arms "
                "hang straight down below your shoulders. That hinge is your setup.",
            )
        elif a > hi:
            ok = False
            self.add(
                "bent_over_setup", _issue_kind(a > hi + 6, spine["confidence"]), "You bend over a lot at address",
                f"Your upper body leans forward about {a:.0f}° from vertical. Most good setups are somewhere "
                f"between {lo:.0f}° and {hi:.0f}°.",
                "you bend over a lot at address", [spine],
                why="A lot of forward bend makes it hard to keep your posture during the swing; many golfers stand "
                "up through impact to make room.",
                drill="Stand a little taller with your chest up, then hinge from the hips only until your arms "
                "hang naturally. Check it side-on in a mirror.",
            )
        if k < klo:
            ok = False
            self.add(
                "straight_legs", _issue_kind(k < klo - 6, knee["confidence"]), "Your legs are quite straight at address",
                f"Your trail knee is flexed about {k:.0f}°. A relaxed, athletic setup usually has around "
                f"{klo:.0f}° to {khi:.0f}°.",
                "your legs are quite straight at address", [knee],
                why="Straight legs make it hard to turn your hips and keep your balance.",
                drill="Flex your knees just enough that you could jump straight up from your setup.",
            )
        elif k > khi:
            ok = False
            self.add(
                "squatting", _issue_kind(k > khi + 8, knee["confidence"]), "You sit down a lot at address",
                f"Your trail knee is flexed about {k:.0f}°. A relaxed, athletic setup usually has around "
                f"{klo:.0f}° to {khi:.0f}°.",
                "you sit down a lot at address", [knee],
                why="Too much knee bend lowers you toward the ball and often leads to standing up in the downswing.",
                drill="Straighten your legs a little and get your forward lean from hinging at the hips instead.",
            )
        if ok:
            self.add(
                "good_setup_posture", "strength", "Solid setup posture",
                f"You lean forward about {a:.0f}° and flex your trail knee about {k:.0f}° at address. Both are "
                "within the usual range for an athletic setup.",
                "your setup posture is solid", [spine, knee],
            )

    def posture_through_impact(self):
        found = self.get("spine_angle_change_impact", "rear_hip_toward_ball_impact")
        if not found:
            return
        spine, hips = found
        loss, hip = -spine["value"], hips["value"]
        parts, clear = [], False
        if loss > SPINE_LOSS[0]:
            parts.append(f"your upper body became about {loss:.0f}° more upright")
            clear |= loss > SPINE_LOSS[1]
        if hip > REAR_HIP_TOWARD_BALL[0]:
            parts.append(f"your backside moved toward the ball by {_cm(hip)}")
            clear |= hip > REAR_HIP_TOWARD_BALL[1]
        if not parts:
            self.add(
                "kept_posture", "strength", "You hold your posture through impact",
                f"From address to impact your forward bend changes by about {abs(loss):.0f}° and your backside "
                f"moves {_cm(hip)} {'toward' if hip >= 0 else 'away from'} the ball. Both are within what good "
                "players do, so your arms keep room to swing through.",
                "you hold your posture through impact", [spine, hips],
            )
            return
        conf = min(spine["confidence"], hips["confidence"])
        self.add(
            "early_extension", _issue_kind(clear, conf), "Your posture changes through impact",
            "From address to impact, " + " and ".join(parts) + ". That is more than good players usually move; "
            "golf coaches call it early extension.",
            "your posture changes through impact (early extension)",
            [hips, spine] if hip > REAR_HIP_TOWARD_BALL[0] else [spine, hips],
            why="When the hips move toward the ball and the chest rises, your arms get crowded and you have to "
            "save the shot with your hands. It is a common cause of blocks, hooks and inconsistent contact.",
            drill="Set up with your backside lightly touching a wall or chair. Make slow half swings: your trail "
            "side stays on the wall going back, and your lead side touches it at impact. If you lose contact, "
            "your hips moved toward the ball.",
        )

    def head_height(self):
        found = self.get("head_rise_top", "head_rise_impact")
        if not found:
            return
        top, imp = found
        worst = min(found, key=lambda x: x["value"]) if min(top["value"], imp["value"]) < -HEAD_DROP[0] else None
        lifted = max(found, key=lambda x: x["value"]) if max(top["value"], imp["value"]) > HEAD_LIFT[0] else None
        if worst:
            v = -worst["value"]
            when = "at impact" if worst["name"].endswith("impact") else "at the top"
            self.add(
                "head_drop", _issue_kind(v > HEAD_DROP[1], worst["confidence"]), "Your head drops during the swing",
                f"Your head is lower {when} than at address by {_cm(v)}. Good players' heads drop a little too, "
                "but this much usually means your whole upper body is moving down.",
                f"your head drops {when}", [worst],
                why="Moving down changes where the club bottoms out, which can lead to fat shots, or to "
                "standing up late to compensate.",
                drill="Make half swings while a friend holds a club shaft just touching the top of your cap. "
                "Keep the same light contact until after impact.",
            )
        elif lifted:
            v = lifted["value"]
            when = "at impact" if lifted["name"].endswith("impact") else "at the top"
            self.add(
                "head_lift", _issue_kind(v > HEAD_LIFT[1], lifted["confidence"]), "Your head rises during the swing",
                f"Your head is higher {when} than at address by {_cm(v)}.",
                f"your head rises {when}", [lifted],
                why="Rising during the swing raises the low point of the club and often causes thin or topped shots.",
                drill="Keep your eyes on the back of the ball until it has gone, and feel your chest stay over "
                "the ball through impact.",
            )
        else:
            lowest = min(found, key=lambda x: x["value"])
            moved = (
                f"Your head is at most {_cm(lowest['value'])} lower than at address"
                if lowest["value"] < -3
                else "Your head stays close to its address height"
            )
            self.add(
                "steady_head", "strength", "Your head height stays steady",
                f"{moved} at the top and at impact. That is within the normal range: good players' heads drop a "
                "little through impact too.",
                "your head height stays steady", [top, imp],
            )

    # ---- face-on ------------------------------------------------------------------------
    def sway(self):
        found = self.get("hip_shift_top", "head_shift_top")
        if not found:
            return
        hip, head = found
        away = max(-hip["value"], -head["value"])
        if away > SWAY[0]:
            used = [hip] if -hip["value"] >= -head["value"] else [head]
            part = "hips" if used[0] is hip else "head"
            self.add(
                "sway", _issue_kind(away > SWAY[1], used[0]["confidence"]), "You sway away from the target",
                f"At the top of the backswing your {part} has moved away from the target by {_cm(away)}. "
                "Ideally you turn around a fairly steady centre instead of sliding.",
                "you sway away from the target in the backswing", used,
                why="Sliding back means you have to slide forward again in the downswing, which makes the low "
                "point and contact inconsistent.",
                drill="Push an alignment stick or umbrella into the ground just outside your trail foot. Turn "
                "back without your trail hip touching it.",
            )
        else:
            self.add(
                "centred_turn", "strength", "You turn without swaying",
                "Your hips and head stay close to their address position in the backswing, so you are turning "
                "rather than sliding.",
                "you turn without swaying", [hip, head],
            )

    def weight_shift(self):
        found = self.get("hip_shift_impact")
        if not found:
            return
        (hip,) = found
        v = hip["value"]
        if v < 5:
            self.add(
                "hanging_back", _issue_kind(v < 0, hip["confidence"]), "Your hips stay back at impact",
                f"At impact your hip centre is {'behind' if v < 0 else 'only slightly ahead of'} where it was at "
                f"address ({_cm(v)}). Good players' hips are usually clearly toward the target by impact.",
                "your hips stay back at impact", [hip],
                why="Without a shift toward the target, the club tends to bottom out behind the ball: fat and "
                "thin shots, and a flipping release.",
                drill="Make swings where you feel your lead hip move toward the target before your arms start "
                "down; finish with almost all your weight on your lead foot and your trail heel up.",
            )
        else:
            self.add(
                "good_weight_shift", "strength", "You shift toward the target",
                f"Your hips move toward the target by {_cm(v)} from address to impact.",
                "you shift toward the target", [hip],
            )

    def lead_arm(self):
        found = self.get("lead_arm_bend_top")
        if not found:
            return
        (arm,) = found
        v = arm["value"]
        if v > LEAD_ARM_BEND[0]:
            self.add(
                "bent_lead_arm", _issue_kind(v > LEAD_ARM_BEND[1], arm["confidence"]), "Your lead arm bends at the top",
                f"Your lead arm is bent about {v:.0f}° at the top of the backswing. A small bend is normal.",
                "your lead arm bends at the top", [arm],
                why="A collapsing lead arm shortens the swing radius and adds a variable you have to time back "
                "out in the downswing.",
                drill="Make three-quarter backswings and stop when your lead arm would start to bend. Feel width: "
                "hands as far from your chest as is comfortable.",
            )
        else:
            self.add(
                "wide_backswing", "strength", "Your lead arm stays wide",
                f"Your lead arm is close to straight at the top (about {v:.0f}° of bend).",
                "your lead arm stays wide at the top", [arm],
            )

    def stance(self):
        found = self.get("stance_width_address")
        if not found:
            return
        (st,) = found
        v = st["value"]
        lo, hi = STANCE_RANGE
        if v < lo or v > hi:
            narrow = v < lo
            self.add(
                "stance_width", "watch", f"Your stance is {'narrow' if narrow else 'wide'}",
                f"Your feet are about {v:.1f} times your shoulder width apart. Around {lo:.1f} to {hi:.1f} is "
                "typical (wider for a driver, narrower for short irons).",
                f"your stance is {'narrow' if narrow else 'wide'}", [st],
                why="A narrow stance limits balance; a very wide one limits how far your hips can turn.",
                drill=None,
            )

    # ---- club --------------------------------------------------------------------------
    def club_plane(self):
        # Either measurement can be missing: the shaft check needs a few sharp frames halfway down,
        # which a fast downswing filmed at 60 fps may not have.
        shaft = self.m.get("shaft_points_downswing")
        path = self.m.get("hand_path_downswing")
        if not shaft and not path:
            return
        v = shaft["value"] if shaft else None
        loop = path["value"] if path else None
        toes = self.club.get("toes_from_ball")
        steep = v is not None and v > SHAFT_OUTSIDE[0]
        outside_path = loop is not None and loop > HAND_PATH_OUTSIDE[0]
        inside_shaft = v is not None and toes is not None and v < toes
        inside_path = loop is not None and loop < -HAND_PATH_INSIDE[0]
        if steep or outside_path:
            parts, used = [], []
            if steep:
                parts.append(f"halfway down, your shaft points beyond the ball by {_cm(v)}")
                used.append(shaft)
            if outside_path:
                parts.append(f"your hands come down {_cm(loop)} outside the path they went back on")
                used.append(path)
            clear = (v is not None and v > SHAFT_OUTSIDE[1]) or (loop is not None and loop > HAND_PATH_OUTSIDE[1])
            self.add(
                "over_the_top", _issue_kind(clear, min(x["confidence"] for x in used)),
                "Your club comes down over the top",
                "Seen from behind: " + " and ".join(parts) + ". In a good downswing the shaft points between "
                "your toes and the ball at that point, and the hands drop slightly inside their backswing path.",
                "your club comes down over the top (steep, outside the swing plane)", used,
                why="When the club comes down steep and outside, it swings across the ball from out to in. That "
                "is the classic cause of slices and pulls, and of divots that point left.",
                drill="Put a headcover or towel just outside the ball, on the far side. Make slow swings that "
                "miss it: start the downswing by turning your hips while your arms and club drop down behind "
                "you, then swing out toward right field (left field if you are left-handed).",
            )
        elif inside_shaft or inside_path:
            parts, used = [], []
            if inside_shaft:
                parts.append(f"halfway down, your shaft points inside your toes, {_cm(v)} inside the ball")
                used.append(shaft)
            if inside_path:
                parts.append(f"your hands drop {_cm(loop)} inside (under) the path they went back on")
                used.append(path)
            clear = (inside_shaft and v < toes - SHAFT_INSIDE_TOES_CLEAR) or (
                inside_path and loop < -HAND_PATH_INSIDE[1]
            )
            self.add(
                "inside_out", _issue_kind(clear, min(x["confidence"] for x in used)),
                "Your club comes from too far inside",
                "Seen from behind: " + " and ".join(parts) + ". Dropping the club slightly inside is good, "
                "but this much makes it swing at the ball from the inside out.",
                "your club comes from too far inside (inside-out)", used,
                why="A club that comes from too far inside swings out to the right through impact (left for "
                "left-handers). That causes pushes and hooks, and thin or fat contact when the low point moves.",
                drill="Feel your arms stay more in front of your chest as you start down, and your chest keep "
                "turning through impact, so the club works down the same line it went back on. A headcover "
                "just inside the ball, on your side, punishes swings that come from too far inside.",
            )
        elif v is not None and v <= ON_PLANE_MAX:
            if v >= 0:
                where = "just beyond the ball"
            elif toes is not None:
                where = "between your toes and the ball"
            else:
                where = "inside the ball"
            used = [shaft] + ([path] if path else [])
            self.add(
                "on_plane", "strength", "Your club comes down on plane",
                f"Halfway down, your shaft points {where}: {_cm(v)} {'inside' if v < 0 else 'beyond'} the ball."
                + (" Your hands come down on or slightly inside the path they went back on." if path else "")
                + " That is what good downswings look like from behind.",
                "your club comes down on plane", used,
            )
        elif v is None and loop <= 3:
            self.add(
                "on_plane", "strength", "Your hands come down on plane",
                f"Your hands come down {'on' if loop > -3 else 'slightly inside'} the path they went back on. (Where the shaft points halfway down could not be measured: the club "
                "is too blurred in those frames. Slow motion would help.)",
                "your hands come down on plane", [path],
            )

    def backswing_length(self):
        found = self.get("shaft_past_parallel_top")
        if not found:
            return
        (top,) = found
        v = top["value"]
        if v > PAST_PARALLEL:
            self.add(
                "overswing", "watch", "Your backswing goes past parallel",
                f"At the top, the shaft is about {v:.0f}° past parallel to the ground. Past parallel is not "
                "wrong in itself, but it is often a sign of a collapsing lead arm or a lifted lead heel.",
                "your backswing goes past parallel", [top],
                why="A very long backswing is harder to time and often costs consistency more than it adds speed.",
                drill="Make swings where you stop when the shaft is parallel to the ground, keeping your lead "
                "arm extended; a three-quarter feel is usually closer to parallel than you think.",
            )
        elif v > -45:
            self.add(
                "controlled_length", "strength", "Controlled backswing length",
                f"At the top, the shaft is {'about parallel to' if abs(v) < 8 else ('about %.0f° short of' % -v if v < 0 else 'about %.0f° past' % v)} "
                "the ground.",
                "your backswing length is controlled", [top],
            )

    # ---- timing --------------------------------------------------------------------------
    def tempo(self):
        found = self.get("tempo_ratio")
        if not found:
            return
        (t,) = found
        v = t["value"]
        lo, hi = TEMPO_RANGE
        if v < lo:
            self.add(
                "quick_backswing", "watch", "Your backswing is quick",
                f"Your backswing takes about {v:.1f} times as long as your downswing. Most good swings are "
                "around 3 to 1.",
                "your backswing is quick compared with your downswing", [t],
                why="A rushed backswing often leads to a rushed transition and poor sequencing.",
                drill="Swing to a count: 'one-two-three' going back, 'four' coming down. A metronome app works too.",
            )
        elif v > hi:
            self.add(
                "slow_backswing", "watch", "Your backswing is slow",
                f"Your backswing takes about {v:.1f} times as long as your downswing. Most good swings are "
                "around 3 to 1.",
                "your backswing is slow compared with your downswing", [t],
                why="A very slow backswing or a long pause at the top can make the transition jerky.",
                drill="Swing to a steady count: 'one-two-three' back, 'four' down, without stopping at the top.",
            )
        else:
            self.add(
                "good_tempo", "strength", "Good rhythm",
                f"Your backswing takes about {v:.1f} times as long as your downswing, close to the 3 to 1 "
                "rhythm of most good swings.",
                "your rhythm is close to 3 to 1", [t],
            )


ORDER = {"improve": 0, "watch": 1, "strength": 2}


def build_feedback(measurements: list[dict], camera_angle: str, notes: list[dict], club: dict | None = None) -> dict:
    rules = _Rules(measurements, club)
    if camera_angle == "down_the_line":
        rules.setup_posture()
        rules.posture_through_impact()
        rules.head_height()
        rules.club_plane()
    elif camera_angle == "face_on":
        rules.sway()
        rules.weight_shift()
        rules.lead_arm()
        rules.stance()
        rules.backswing_length()
    rules.tempo()

    findings = sorted(rules.out, key=lambda f: (ORDER[f.kind], -f.confidence))
    return {
        "summary": _summary(findings),
        "findings": [f.to_dict() for f in findings],
        "not_checked": _not_checked(camera_angle, notes, club),
    }


def _join(clauses: list[str]) -> str:
    return clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + " and " + clauses[-1]


def _summary(findings: list[Finding]) -> str:
    strengths = [f.headline for f in findings if f.kind == "strength"]
    improve = [f for f in findings if f.kind == "improve"]
    watch = [f for f in findings if f.kind == "watch"]
    parts = []
    if strengths:
        parts.append("Good: " + _join(strengths[:3]) + ".")
    if improve:
        parts.append("The main thing to work on: " + improve[0].headline + ".")
        if len(improve) > 1:
            parts.append("After that: " + _join([f.headline for f in improve[1:3]]) + ".")
    if watch:
        lead = "Also worth checking" if improve else "Nothing stands out as a clear fault. Worth checking"
        parts.append(f"{lead}: " + _join([f.headline for f in watch[:3]]) + ".")
    if not improve and not watch:
        parts.append("No clear faults in what this camera angle can show.")
    if any(f.confidence < RELIABLE for f in improve + watch):
        parts.append("Some of this is uncertain, so look at the frames yourself before changing anything.")
    if not findings:
        return "There is not enough reliable data in this clip to give feedback."
    return " ".join(parts)


def _not_checked(camera_angle: str, notes: list[dict], club: dict | None = None) -> list[str]:
    items = []
    if any(n["code"] == "slow_motion_suspected" for n in notes):
        items.append("Tempo: the clip seems to be slow motion, so timing could not be judged.")
    if camera_angle == "down_the_line":
        items.append("Sway and weight shift toward the target can't be seen from behind. Film face-on to check them.")
    elif camera_angle == "face_on":
        items.append(
            "Posture changes toward the ball (early extension) can't be seen from the front. "
            "Film down-the-line to check them."
        )
    if club and club.get("tracked"):
        if camera_angle == "face_on":
            items.append("The swing plane is judged from behind. Film down-the-line to check over-the-top moves.")
        items.append(
            "Club path and face angle at impact in degrees can't be measured from phone video; the club head "
            "is a blur at impact. A launch monitor measures those."
        )
    else:
        items.append(
            "The club was not tracked for this video, so the swing plane and over-the-top moves are not judged. "
            "Process the video again to add club tracking."
        )
    return items
