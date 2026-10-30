# Development status

Last updated: 2026-10-30

## Read this first: what has actually been verified

The code was written in a cloud container that could not install packages or run Docker. On 2026-10-30 the full stack was built and run on the target Mac (Apple Silicon, Docker Desktop, linux/arm64 images).

| Area | Verified (ran and passed) | Not verified |
|---|---|---|
| Docker | All four images build natively on arm64; `docker compose up --build` starts cleanly; `scripts/verify.sh` passes | |
| CV service | 54/54 pytest tests, including the HTTP tests, swing-analysis and feedback-rule tests, and a regression test on a tour professional's swing; the real MediaPipe `full` model loads and runs (and the image build runs a smoke test that loads it) | |
| Backend | Build, 19/19 unit tests (.NET 10 SDK in Docker), migrations on PostgreSQL (including baselining the existing database without data loss), re-analyse endpoint, upload, validation (fake MP4 rejected with 400), worker, status polling, video range requests (206), keypoints download, delete (rows and both files removed) | |
| Frontend | Type check, production build, nginx serving, SPA deep links, `/api` proxy; skeleton overlay checked on screen by the user; redesigned pages checked in headless Chromium screenshots at desktop and phone width | Playback inside the headless screenshots (no H.264 there); Safari and Firefox |
| End to end | One real down-the-line swing (360x640, 30 fps, slow motion): 100% pose detection, all five phases checked by eye against the video frames, results stored as rows and JSON, identical between a fresh upload and a re-analysis | Face-on swings, left-handed swings and normal-speed (non-slow-motion) footage on real video: covered only by synthetic tests so far |

### Fixed during the first run
1. Frontend build failed: `vite.config.ts` uses `process` without Node types. Added `@types/node` and the `node` types entry; `package-lock.json` is now committed (generated in `node:22-alpine`, the image the build uses).
2. **Every analysis failed** with `OSError: libEGL.so.1`: the MediaPipe Tasks runtime loads EGL/GLES even on CPU. Added `libegl1` and `libgles2` to the cv-service image, plus a build-time smoke test that loads the model, so this kind of error now fails the build. `verify.sh`'s health checks had all passed despite this bug, because `/health` only checks that the model file exists.
3. API logged `libgssapi_krb5.so.2` missing at startup (Npgsql probes GSSAPI): installed `libgssapi-krb5-2`. Removed `ASPNETCORE_URLS`, which overrode the image's own port setting (8080) and logged a warning.
4. EF Core version conflict between the API (10.0.14) and the test project (10.0.4). NuGet versions are now pinned exactly, with `Microsoft.EntityFrameworkCore.Relational` referenced directly.

## Completed

**Milestone 1: project foundation (verified end to end)**
- Repository layout, `.gitignore` (videos and keypoints are never committed), `.env.example`.
- React/TypeScript/Tailwind/Vite app, ASP.NET Core API, FastAPI service, PostgreSQL, Docker Compose.
- Health endpoints on every service plus `scripts/verify.sh` to check the links between them.

**Milestone 2: video processing (verified end to end with a synthetic clip; real swing still to test)**
- Upload form with drag and drop, camera angle with placement diagrams, handedness, optional club, recording tips.
- API upload validation (extension, size, file header), storage, queue, background worker, status polling, delete.
- CV pipeline: metadata (duration, resolution, fps, frames, orientation, rotation), per-frame pose extraction behind a `PoseEstimator` interface, golfer selection when several people appear, raw keypoints saved as JSON, timestamps taken from the container.
- Quality report: frame rate, resolution, lighting, detection rate, joint visibility, golfer inside frame, multiple people. Low frame rate lowers a `temporal_resolution_factor` instead of rejecting the video.
- Pages: Dashboard (real counts, honest empty states), Analyse Swing, Processing, Analysis (video with slow-motion speeds, details, quality report, keypoints download).

**Milestone 4, part 1: skeleton overlay (built)**
- Canvas over the video, redrawn on every presented frame (`requestVideoFrameCallback`, with a `requestAnimationFrame` fallback) using the frame timestamps from the keypoints file. Handles letterboxing and resizing.
- Left side in blue, right side in gold, so swapped joints are easy to spot. Joints with visibility below 0.5 are drawn faded and dashed, and can be hidden.
- Frame-by-frame stepping, current frame number and time, and a "no person detected" note per frame.
- Verified: frame lookup tested against a real 328-frame swing; the same coordinates rendered onto the decoded video frames sit on the golfer from address to finish. Not verified: the canvas drawing itself in a real browser (it type-checks and builds, but has not been looked at on screen yet).

**Milestone 3: swing phases and measurements (built)**
- `cv-service/app/swing`: pixel-space series, left-handed mirroring, gap filling, Savitzky-Golay smoothing; phases address, takeaway, top, impact, finish from the hands' path; 2D measurements per camera angle with type (measured or estimated) and confidence; notes. Details in `docs/ARCHITECTURE.md`.
- Runs at the end of every job and on demand (`POST /api/analyses/{id}/reanalyze`, about a second, no pose model). Results are stored as `Analyses.SwingJson` and as `Phases`/`Measurements` rows.
- EF Core migrations replace `EnsureCreated`; existing databases are baselined on startup.
- Analysis page: phase markers and buttons under the video, measurements grouped by phase with meaning, confidence and type, and notes. Selecting a phase or measurement shows its frame.
- Tuned on the real swing, where three first attempts failed and were fixed: (1) following the hand path frame by frame stopped on 30 fps jitter, so impact and top now use region searches; (2) a pause at the top made "highest point" mark the start of the pause, so the top is now when the hands start down; (3) per-frame hand speed could not separate standing still from a slow takeaway, so address now uses the hand position held longest. Takeaway follows the hands; on that clip the clubhead starts about 0.3 s earlier, and the club is not tracked.
- Slow motion: real downswings take about 0.25 to 0.45 s. If the downswing lasts more than 0.6 s of video time, slow motion is suspected and **all** timing values are left out, including the tempo ratio: on the real clip the tempo came out at 0.92 (backswing faster than downswing), which shows that phone slow motion changes speed within a clip.

**Rules engine: written feedback (built, swing-0.2)**
- `cv-service/app/swing/feedback.py` turns measurements into findings with a title, what was seen, why it matters and a drill, labelled "Work on this", "Worth checking" or "Strength", plus a summary and a list of what the video could not show.
- Uncertain data never produces a firm fault or praise: clear faults on confidence below 0.5 become "Worth checking"; strengths below 0.5 are left out.
- Thresholds are broad typical ranges chosen from common coaching guidance, not validated against measured data. They are constants at the top of the file, meant to be tuned as more swings are analysed.
- The analysis page leads with the feedback; the measurements are folded away below it. Older results show a link to re-run the analysis.
- Tests: 9 rule tests (good swing, clear and mild faults, uncertain data, face-on, tempo, no placeholder text in the output). On the real swing: setup posture is a strength; early extension and a head drop at impact are "Worth checking" because impact is blurred at 30 fps.

**Reliability pass and redesign (swing-0.3)**
- Calibrated with a tour professional's swing (Rory McIlroy, down-the-line, slow motion), which got two false "Worth checking" findings in swing-0.2. Causes and fixes:
  1. Early extension used the hip *centre*, which moves toward the ball just from the hips rotating open. It now uses the rear hip (the backside line coaches use).
  2. Thresholds were stricter than what good players do. They now follow 3D tour data: up to ~12° less forward bend, ~7.5 cm of pelvis toward the ball and ~10 cm of head drop at impact are normal.
  3. Confidence: address and top values are medians over the held frames; impact values are tested one real frame either side, and confidence drops only if the value changes. On the tour swing, impact confidence rose from 0.48 to 0.70-0.79.
- The tour swing's keypoints are a test fixture (`cv-service/tests/fixtures`): it must be found correctly and must get no fault findings. One swing cannot prove the rules catch real faults; that needs clips with known faults.
- Frontend redesign: light theme with a green brand colour, cards, icons; analysis page with video and feedback side by side, a verdict, finding cards with drills, and technical details folded away; dashboard with verdicts and the most-flagged issue; step-by-step upload page.

## Current implementation

Upload a video, watch it process, then see the video with the detected skeleton and swing phases, jump to any phase, and read plain-language feedback with drills, backed by the 2D measurements, plus notes, metadata and the quality report. Older analyses get phases and measurements with one click (re-analysis from the saved keypoints).

## Not done yet

- **Milestone 4 (rest):** Recharts graphs of joint angles and hand path over time (Recharts is not installed yet). The phase timeline and measurement list are done.
- **Milestone 5:** testing with real swings, pose failure analysis, refinement, performance.
- Quality checks for camera movement and camera-angle match (listed in the report as "not checked").
- After the milestones: a larger drill library, Ollama rephrasing of the feedback, swing comparison.

## Known bugs and risks

1. Phase detection and measurements have been checked on one real swing. They need face-on, left-handed and normal-speed clips before the thresholds (in `phases.py`) can be trusted more widely.
2. Phases come from the hands only. A swing where the hands barely rise (chips, putts) is reported as "no swing found". Practice swings in the same clip: the fastest downswing wins.
3. Measurements depend on the selected camera angle being right; the "camera angle matches the footage" check is still not implemented.
4. `/health` reports whether the model *file* exists, not whether it loads. The build-time smoke test covers the image, but an environment outside Docker can still pass health and then fail on the first job.
5. Upload progress uses XHR; very large uploads through nginx have a 600 MB cap and 300 s timeouts.
6. The host has Docker Engine 20.10 / Compose 2.15 (old, but it works). The host .NET SDK is 9.0, so build the backend outside Docker only after installing .NET 10.

## Next steps

1. Read the feedback for your swing in the browser and tell me if anything is wrong, unclear or off in tone.
2. Record a few more clips if possible: face-on, normal speed (not slow motion, ideally 60 or 120 fps at 1080p), and a left-handed swing if you can. Each one tests a part only synthetic data has covered so far.
3. Most useful for certainty: a few clips with known faults (to prove the rules catch them), and normal-speed footage at 120-240 fps and 1080p. The `heavy` pose model (`POSE_MODEL_VARIANT=heavy`) is worth comparing on the same clips. Then Milestone 4's graphs.
