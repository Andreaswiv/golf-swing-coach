# Development status

Last updated: 2026-11-01. Swing analysis version: `swing-0.5`.

This file is for anyone picking up the project: what works, how well it has been checked, what is
missing and where the risks are. Setup instructions are in [README.md](README.md).

## Summary

The app runs end to end on one machine with Docker. A user uploads a swing (up to 15 seconds),
the CV service finds the joints and the club, the swing analysis detects the phases, measures
posture, tempo and swing plane, rates each value and writes feedback. The browser shows the video
with the skeleton, club trail and swing plane, plus the results. It is a working single-user
prototype, **not** ready to be put on the internet (see [Before deploying publicly](#before-deploying-publicly)).

## What has been verified

| Area | Verified | Not verified |
|---|---|---|
| Docker | All four images build and run on Apple Silicon (linux/arm64); `scripts/verify.sh` passes | Running the whole stack on a real x86_64 machine (on 2026-11-01 all three images were built for linux/amd64 under emulation, the CV image's build loaded and ran both models, and the 92 CV tests passed inside it) |
| CV service | 92/92 pytest tests on 2026-11-01: pipeline, HTTP API, series cleaning, phases, measurements, club analysis, ratings, feedback, slow-motion tempo, and a regression test on a tour professional's swing. The image build loads both models and runs them on one frame | |
| API | 19/19 unit tests on 2026-11-01 (.NET 10 SDK in Docker). Upload, validation, queue, worker, re-analyse, range requests for video, keypoints download and delete checked by hand | |
| Frontend | Type check and production build; all pages used by hand in a desktop browser on macOS | Other browsers, and real phones (the layout is responsive; an earlier version was checked at phone width in headless Chromium) |
| End to end | Real down-the-line swings (normal speed and slow motion), including a tour professional's slow-motion clip: phases checked by eye against the video frames | Face-on and left-handed swings on real video (covered by synthetic tests only); clips with known faults (to prove the rules catch them) |

## Features

**Upload and processing**
- Upload page with camera angle (with placement diagrams), handedness, optional club and
  recording tips. Files over 15 seconds or the size limit are refused in the browser.
- API validation (extension, size, file header), storage in `data/videos`, a background queue
  (one job at a time), progress polling and a running clock on the processing page.
- Quality report: frame rate, resolution, lighting, detection rate, joint visibility, golfer in
  frame, multiple people. Low frame rate lowers confidence instead of rejecting the video.

**Computer vision** (`cv-service/app/pose`, `cv-service/app/club`)
- MediaPipe Pose Landmarker **heavy** on every frame (the `full` model swapped the arms from
  down-the-line), with golfer selection when several people are in view.
- SwingTrace YOLO11m club detection (shaft, head, hands), run only from 1 s before the swing to
  0.3 s after it. Detections far from the hands or longer than the club are rejected (this fixed
  power lines being detected as shafts).

**Swing analysis** (`cv-service/app/swing`, details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md))
- Cleaning: left-handed mirroring, glitch removal (joints that jump away and back, limbs that get
  impossibly long), gap filling, smoothing.
- Phases from the hands' path: address, takeaway, top, impact, finish. Waggles and practice swings
  are skipped (the fastest believable downswing wins).
- Measurements per camera angle, each with a confidence score; club measurements (swing plane,
  shaft pointing halfway down, hand path, inside-out and over-the-top) from behind.
- Slow motion: detected from the downswing duration. Durations are left out, the tempo ratio is
  kept unless the clip changes speed mid-swing.
- Ratings (green/yellow/red) for every measurement and rules-based feedback with drills. Limits and
  their sources: [docs/RATING_SOURCES.md](docs/RATING_SOURCES.md).

**Frontend** (React, shadcn/ui)
- Homepage: animated example analysis (a stick figure, not a real person), a "every swing,
  measured" bento with ratings across your swings, and your swing list with video stills.
- Analysis page: video player with custom controls, frame stepping, skeleton/club/plane overlay
  that stays in sync while scrubbing and in fullscreen, phase markers, feedback cards, rated
  measurements with low-confidence warnings, re-analyse and delete.

## Not done

- **User accounts.** There is no login; every visitor sees and can delete every swing.
- **Quality checks** for camera movement and for whether the chosen camera angle matches the
  footage (shown as "not checked" in the report).
- **Graphs over time** of joint angles and hand path within a swing.
- **More validation data:** face-on, left-handed, and clips with known faults.
- Ideas for later: swing comparison side by side, a larger drill library, a language model that
  rephrases (never invents) the feedback.

## Known problems and risks

1. **Tempo reads a little low.** Takeaway is when the hands start moving; the club head starts
   about 0.1-0.3 s earlier. A club-based takeaway would raise the ratio by about 0.2-0.5, and
   `TEMPO_RANGE` would then need recalibrating.
2. **Several rating limits have no published source** (spine angle change, rear hip toward the
   ball, hand path, head shift, shaft past parallel). They are calibrated so the tour swing fixture
   gets no faults. See [docs/RATING_SOURCES.md](docs/RATING_SOURCES.md).
3. **Ratings are stored at analysis time.** After changing limits or analysis code, older swings
   keep their old results until "Re-analyse" is clicked. A bulk re-analyse does not exist yet.
4. **Long videos are only stopped after upload.** The browser refuses clips over 15 seconds, and the
   CV service fails the job with a clear message if one gets through, but the API itself does not
   check the length, so the file is uploaded and stored first.
5. **Analysis speed depends on the CPU.** The heavy pose model plus club detection takes from
   under a minute to a few minutes per clip on an M-series Mac; a small cloud CPU will be slower.
   Jobs run one at a time.
6. **Phases come from the hands only.** Chips and putts (hands barely rise) give "no swing found".
7. **`/health` checks that the model files exist, not that they load.** The image build's smoke test
   covers Docker; a setup outside Docker can pass health and fail on the first job.
8. **Browsers may not play HEVC.** iPhone videos usually play, but a black player means the clip
   should be re-exported as H.264.

## Before deploying publicly

The current setup assumes one trusted user on their own computer. Before putting it online:

1. **Accounts and access control:** each user sees only their own swings (or at least a login in
   front of everything).
2. **HTTPS** through a reverse proxy (for example Caddy) or the hosting platform. Expose only the
   web container; keep the API, CV service and database internal.
3. **Secrets:** a real `POSTGRES_PASSWORD` in `.env`.
4. **Rate limiting** on uploads, and ideally a length check in the API before the file is stored
   (problem 4 above).
5. **Storage:** backups of `data/` and the database, and cleanup of old videos.
6. **GDPR:** videos of people are personal data. Needs a privacy policy, deletion on request (the
   delete button covers a single swing), and hosting in the EU/EEA.
7. **AGPL:** the project is licensed AGPL-3.0 (`LICENSE`), matching the club model. Users of the
   hosted app must be able to get the source code; a public repository satisfies this.

## History

- **swing-0.1 to 0.2:** foundation, upload, pose extraction, skeleton overlay, phases, 2D
  measurements, rules-based feedback.
- **swing-0.3:** calibrated on a tour swing; held-position medians and impact stability checks for
  confidence; first redesign.
- **swing-0.4 and 0.5:** club detection, swing plane, shaft pointing and hand path, inside-out
  check, plausibility filters for club and joints, club detection limited to the swing window,
  ratings for every measurement, tempo in slow motion with speed-change detection,
  heavy pose model, shadcn/ui redesign with the animated homepage, player sync fixes, rating limits
  checked against published sources (shoulder tilt at impact widened, downswing duration
  tightened).
