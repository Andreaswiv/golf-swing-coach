# Where the rating limits come from

The limits live in `cv-service/app/swing/limits.py` (shared ranges) and
`cv-service/app/swing/ratings.py` (ranges used only for ratings). This file lists, per
measurement, what each limit is based on and how strong that basis is.

Read the comparisons with these caveats in mind:

* **2D, not 3D.** The app measures angles in the video image. The studies use 3D motion
  capture or sensors. A 2D angle from behind is close to a 3D angle only when the camera
  stands square on the target line.
* **Different definitions.** For example, Kim et al. measure trunk flexion from the 7th
  neck vertebra to the pelvis. The app measures from the hip centre to the shoulder centre.
* **Torso units.** Distances are % of torso length; 1% ≈ 0.5 cm for an average adult
  (`AVERAGE_TORSO_CM = 50`).
* **Hands-based phase timing.** Takeaway is when the hands start moving, a little after the
  club head starts, so the measured backswing is slightly shorter than a club-based one.

Evidence levels:

* **A**: peer-reviewed or instrumented measurements of skilled golfers.
* **B**: large company data sets (GOLFTEC) or a teaching body, with methods not published.
* **C**: coaching convention only.
* **Calibrated**: no number found in a source; the limit was set so the tour swings in
  `tests/fixtures` come out without faults.

## Down-the-line

| Measurement | App limit (good / watch / bad) | Source data | Level | Fit |
|---|---|---|---|---|
| Spine angle at address | good 28–48°, watch ±6° | 11 male pros, 5-iron: trunk flexion **41.5 ± 2.9°** [1]. GOLFTEC tour average with driver: **29°** shoulder bend [3]; a GOLFTEC coach quotes ~40° [4] | A + B | Good: the range covers drivers (~29°) to irons (~41°) |
| Trail knee flex at address | good 12–38°, watch −6/+8° | Same pros: right knee **24.4 ± 5.5°** [1], so ±2 SD = 13–35° | A | Good: matches ±2 SD |
| Spine angle change at impact | less than 12° more upright, bad from 18° | Loss of posture is the most common fault in TPI's database (64%) [6], but no source gives a limit in degrees | Calibrated | No numeric source |
| Rear hip toward ball at impact | below 15% (≈7.5 cm), bad from 25% | Early extension is defined (hips move toward the ball, torso rises) [6, 7]; 64% of players do it [6]; no limit in cm found | Calibrated | No numeric source |
| Head height, top and impact | between 20% (≈10 cm) lower and 8% (≈4 cm) higher | Skilled golfers moved the head ~2 cm (sagittal) and ~5.5 cm (frontal) at the top, against 12 cm for high handicappers [8] | A (preliminary) | Partly: the source is at the top only. The tour fixture's head drops 16% (≈8 cm) at impact, so the allowance is kept |
| Shaft points, halfway down | good between toes and ball (up to 15% outside), bad beyond 40% | Instruction: butt end points at the ball or the line behind it halfway down; pointing outside it is steep [9, 10]. Tour swings in the fixtures measured −10% and −21% | C + calibrated | Agrees with instruction |
| Hand path, downswing vs backswing | within 10% outside / 12% inside | Coaching idea of the over-the-top loop; a tour swing measured 0 | Calibrated | No numeric source |

## Face-on

| Measurement | App limit | Source data | Level | Fit |
|---|---|---|---|---|
| Shoulder tilt at address | lead shoulder 3–18° higher | Pros' 3D shoulder side-bend at address: **12.0 ± 2.6°** [1] | A (related) | Good |
| Shoulder tilt at top | lead shoulder 10–55° lower | Tour **36°**, high handicappers **29.6°** [2] | B | Fits, but does not separate tour from high handicappers |
| Shoulder tilt at impact | lead shoulder 10–45° higher, watch to 55° | Tour **39°**, high handicappers **27.5°** [2] | B | Good: tour average is well inside |
| Hip shift at top (sway) | under 8% (≈4 cm) away from target | Tour hips move **~10 cm toward** the target (measured at the tailbone); less skilled players' shoulders sit 16 cm further back [2, 5] | B | Agrees in direction |
| Hip shift at impact | good ≥5% (≈2.5 cm) toward target, bad <0 | Tour **+4 cm** (≈8%), high handicappers **−1 cm** (≈−2%) [2] | B | Good: tour average is good, high-handicap average is bad |
| Head shift at top / impact | see `ratings.py` | No numeric source found; "head stays behind the ball" is coaching convention | C | No numeric source |
| Lead arm bend at top | under 20°, bad from 35° | GOLFTEC example: 10° good, 76° too much [11]; an unsourced claim of ~15° average in 3D capture [11] | B/C | Plausible, weak |
| Stance width (ankles / shoulders) | 0.85–1.6 | Teaching body: driver ≈ 5 cm outside each shoulder, 9-iron ≈ 5 cm inside [12] | C | Covers the range |
| Shaft past parallel at top | 45° short to 15° past | Coaching convention | C | No numeric source |

## Timing

| Measurement | App limit | Source data | Level | Fit |
|---|---|---|---|---|
| Tempo ratio | good 2.3–4.0, else watch | Sensor-measured [13]: pros **2.8** and **2.9**, collegiate golfer **3.4**, long-drive competitor **2.4**; 10-handicap **2.1**, 25-handicap **1.9**. "Tour Tempo" 3 : 1 [14] | A (small sample) | Good: separates the pros from the amateurs. The hands-based takeaway reads a little low |
| Backswing duration | good 0.55–1.2 s | Pros 0.72–0.73 s, all five golfers 0.69–0.83 s [13] | A (small sample) | Good |
| Downswing duration | good 0.22–0.35 s, watch 0.18–0.45 s | Pros **0.25–0.26 s**, long drive 0.31, 10-handicap 0.39, 25-handicap 0.43 [13] | A (small sample) | Good: pros are good, the handicappers are watch |

## Changes made after this review

1. **Shoulder tilt at impact:** good widened from 10–40° to 10–45°, so the tour average (39°)
   is no longer at the edge.
2. **Downswing duration:** good tightened from 0.22–0.45 s to 0.22–0.35 s (watch up to 0.45 s).
3. **Head drop: not changed.** A tighter limit (~12%) was considered, but the tour swing in
   `tests/fixtures` drops its head 16% at impact, and the source only measured the top.

Still open: the unsourced limits (spine change, rear hip, hand path, head shift, past parallel)
are calibrated, not sourced. Calibrating them on more tour swings would make them stronger.

## Sources

1. Kim, S.-E. et al. (2018). Ball-position effects on address position variables and club-head
   kinematics in professional golfers. *Journal of Sports Science and Medicine* 17(4), 589–598.
   11 male professionals, Vicon 3D capture, 5-iron. Tables 1–2.
   <https://jssm.org/jssm-17-589.xml-Fulltext>
2. GOLFTEC SwingTRU Motion Study, as reported by Golf Digest: "GolfTEC tested 30,000 players to
   find out what makes a great swing great".
   <https://golfdigestme.com/swing-numbers-new-study-unlocks-6-swing-secrets/>
   See also <https://www.pga.com/archive/golftecs-swingtru-motion-study-illustrates-big-swing-differences-between>
3. GOLFTEC: "Explaining the head drop during the golf swing" (tour averages, driver setup).
   <https://scramble.golftec.com/blog/2015/04/explaining-head-drop-golf-swing/>
4. Golf.com, "The secret to a consistent swing" (J. Troyer, GOLFTEC).
   <https://golf.com/instruction/secret-consistent-swing-focus-this-key/>
5. GOLFTEC: "Golf science: motion measurement, sways".
   <https://scramble.golftec.com/blog/2016/01/golf-science-motion-measurement-sways/>
6. TPI swing characteristics prevalence, via Powers Health CME presentation (2024).
   <https://powershealth.org/-/media/files/pdfs/cme/2024/the-body-swing-connection.ashx>
7. Titleist: "Improve your golf posture and your consistency".
   <https://www.titleist.eu/instruction/swing-in-posture>
8. University of Limerick, ISBS proceedings: head displacement by skill category (preliminary).
   <https://researchrepository.ul.ie/entities/publication/c292f0be-319e-4569-817c-a15a2b783a88>
9. RotarySwing: "Golf downswing forearm and shaft alignment / plane".
   <https://rotaryswing.com/golf-instruction/swingfundamentals/golf-shaft-forearm-plane>
10. The Korea Times: "Let your handle point toward the target line".
    <https://www.koreatimes.co.kr/amp/sports/20160120/let-your-handle-point-toward-the-target-line>
11. GOLFTEC: "Straightening your lead arm leads to consistent contact".
    <https://scramble.golftec.com/blog/2023/03/keep-your-lead-arm-straight-throughout-your-swing/>
12. US Golf Teachers Federation, stance width by club. <https://www.usgtf.com/?p=6248>
13. Grober, R. D. (2010). Measuring tempo, rhythm, timing, and the torques that generate power in
    the golf swing. arXiv:1001.1137. <https://arxiv.org/abs/1001.1137>
14. Novosel, J. & Garrity, J. (2004). *Tour Tempo*. Doubleday.
