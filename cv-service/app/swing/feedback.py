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
    def __init__(self, measurements: list[dict]) -> None:
        self.m = {x["name"]: x for x in measurements}
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


def build_feedback(measurements: list[dict], camera_angle: str, notes: list[dict]) -> dict:
    rules = _Rules(measurements)
    if camera_angle == "down_the_line":
        rules.setup_posture()
        rules.posture_through_impact()
        rules.head_height()
    elif camera_angle == "face_on":
        rules.sway()
        rules.weight_shift()
        rules.lead_arm()
        rules.stance()
    rules.tempo()

    findings = sorted(rules.out, key=lambda f: (ORDER[f.kind], -f.confidence))
    return {
        "summary": _summary(findings),
        "findings": [f.to_dict() for f in findings],
        "not_checked": _not_checked(camera_angle, notes),
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


def _not_checked(camera_angle: str, notes: list[dict]) -> list[str]:
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
    items.append("The club is not tracked, so club path, face angle and swing plane are not judged.")
    return items
