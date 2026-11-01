# Swing Coach: golf swing analysis from a phone video

Upload a short video of a golf swing. The app finds the golfer's joints and the club in every
frame, detects the swing phases (address, takeaway, top, impact, finish), measures posture,
tempo and swing plane, rates each measurement green, yellow or red, and writes plain-language
feedback with drills. The skeleton, club trail and swing plane are drawn over the video.

Everything runs in Docker on one machine. Videos are not sent to any cloud service.

For what has been tested, what is missing and the known problems, see
[DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md).

## Quick start

Requirements:

- Docker Desktop (macOS, or Windows with WSL 2) or Docker Engine with Compose v2 (Linux), with at
  least 6 GB of memory for Docker. All images build for both arm64 (Apple Silicon, ARM servers)
  and x86_64 (Intel/AMD PCs, Intel Macs, most cloud servers). On Windows, run the `scripts/`
  helpers from WSL or Git Bash; `docker compose` itself works from any terminal.
- About 8 GB of free disk space for the images, plus space for videos.
- Internet access for the first build (base images, packages and the two models).

```bash
git clone https://github.com/Andreaswiv/golf-swing-coach.git
cd golf-swing-coach
scripts/doctor.sh                 # optional: checks your system and Docker setup
docker compose up --build         # the first build takes 5-15 minutes
```

Open <http://localhost:5173> and upload a swing. The analysis takes from under a minute to a few
minutes, depending on the clip's length and your CPU.

Stop the stack with `Ctrl+C` or `docker compose down`. `docker compose down -v` also deletes
the database. Videos and keypoints stay in `./data` until you delete them in the app.

To check that every service is up and talking to the others:

```bash
scripts/verify.sh                         # health checks only
scripts/verify.sh ~/Movies/swing.mp4      # also uploads a video and waits for the result
ANGLE=down_the_line HAND=left scripts/verify.sh swing.mov
```

## Recording a video that analyses well

- **Camera position:** down-the-line (behind the golfer, looking along the target line) or
  face-on (in front, facing the chest). Choose the matching angle when you upload.
- **Framing:** the whole body and the club in view the whole time, with the camera on a tripod
  or held still.
- **Length:** at most 15 seconds. Trim the clip to a second or two either side of the swing.
- **Frame rate:** 60 fps or higher is best. 30 fps works but blurs impact, so impact values get
  lower confidence.
- **Slow motion:** supported. Durations in seconds are left out, but the tempo ratio is still
  measured unless the clip changes speed during the swing.
- **Conditions:** good light, and only the golfer in frame.

## What it measures

| | Down-the-line | Face-on |
|---|---|---|
| Posture | Spine angle at address, top and impact; trail knee flex | Shoulder tilt at address, top and impact; stance width |
| Movement | Spine angle change, rear hip toward the ball (early extension), head height | Hip and head shift (sway), lead arm bend |
| Club | Where the shaft points halfway down (on plane or over the top), hand path | Shaft past parallel at the top |
| Timing | Tempo ratio; backswing and downswing duration (not for slow motion) | Same |

How the numbers are calculated: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Where each
green/yellow/red limit comes from, with sources: [docs/RATING_SOURCES.md](docs/RATING_SOURCES.md).

## How it fits together

```
Browser ──> web (nginx :5173) ──/api──> api (ASP.NET Core :8080) ──HTTP──> cv-service (FastAPI :8000)
                                           │                                   │
                                           ├── PostgreSQL (:5432)              │
                                           └── ./data (videos, keypoints) ─────┘  shared folder
```

1. The browser uploads the video to the API. The API checks it (type, size, file header), saves
   it to `data/videos/`, creates an `Analysis` row and queues it.
2. A background worker sends the job to the CV service and copies its progress into the database.
3. The CV service runs the pose model on every frame and the club model on the frames around the
   swing. It writes the keypoints to `data/keypoints/{id}.json`, then runs the swing analysis:
   phases, measurements, ratings and feedback.
4. The browser polls for the status, then shows the video with the overlay and the results.

The swing analysis can be re-run on saved keypoints in about a second, without the models
("Re-analyse" on the analysis page, or `POST /api/analyses/{id}/reanalyze`). Do this after
changing analysis code or rating limits: ratings are stored when a swing is analysed.

## Technology

| Part | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite 7, Tailwind CSS 4, shadcn/ui (Radix), lucide icons |
| API | ASP.NET Core (.NET 10), EF Core with migrations, Npgsql |
| Computer vision | Python 3.12, FastAPI, OpenCV, MediaPipe Pose Landmarker (heavy), ONNX Runtime |
| Club detection | SwingTrace YOLO11m, converted to ONNX at build time |
| Database | PostgreSQL 16 (structured data only; videos and keypoints are files) |
| Runtime | Docker Compose |

Feedback comes from a fixed rules engine (`cv-service/app/swing/feedback.py`), not a language
model, so it can never claim something the measurements do not show.

## Folder structure

```
backend/        ASP.NET Core API (GolfCoach.Api) and its tests (GolfCoach.Api.Tests)
cv-service/     FastAPI service
  app/pose/       pose estimation (MediaPipe)
  app/club/       club detection (ONNX)
  app/swing/      series cleaning, phases, measurements, club analysis, ratings, feedback
  tests/          pytest suite; tests/fixtures holds a tour swing used as a regression test
frontend/       React app: src/pages, src/components (ui/ = shadcn components, home/ = homepage)
data/           videos/ and keypoints/ (git-ignored: personal data)
docs/           ARCHITECTURE.md, RATING_SOURCES.md
scripts/        doctor.sh, verify.sh, download_pose_model.sh
```

## Configuration

The defaults work as they are. To change something, copy `.env.example` to `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `POSE_MODEL_VARIANT` | `heavy` | `lite`, `full` or `heavy`. `full` is faster but swaps the arms more often from down-the-line. Rebuild after changing: `docker compose build cv-service` |
| `MAX_PROCESS_DIM` | `1280` | Longest video side used for pose estimation (lower is faster) |
| `NUM_POSES` | `2` | People the pose model may report per frame (for the multiple-people warning) |
| `UPLOAD_MAX_MB` | `500` | Upload size limit |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `golfcoach`, `golfcoach`, `golfcoach_dev` | Database settings. Change the password before running anywhere but your own computer |

The CV service also reads `CLUB_DETECTION=0` (turns club detection off) and `CLUB_MODEL_PATH`.

All ports bind to `127.0.0.1`, so the app is reachable only from the computer it runs on.

## Development

### Tests

```bash
# CV service (no model files needed: tests use fakes, a synthetic video and a saved tour swing)
cd cv-service && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && pytest

# The same, inside the built image, without a local Python setup:
docker run --rm -e PYTHONPATH=/src -v "$PWD/cv-service:/src" -w /src golfcoach-cv-service \
  sh -c "pip install -q pytest httpx && python -m pytest -q"

# API unit tests (needs the .NET 10 SDK)
cd backend && dotnet test GolfCoach.slnx

# Frontend type check and production build
cd frontend && npm install && npm run build
```

The tests cover logic and contracts. Trying real swing videos is still the real test of the pose
and club detection.

### Running services outside Docker

```bash
# 1. database only
docker compose up db

# 2. CV service (Python 3.12)
cd cv-service && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
../scripts/download_pose_model.sh heavy
POSE_MODEL_PATH=$PWD/models/pose_landmarker_heavy.task DATA_DIR=$PWD/../data CLUB_DETECTION=0 \
  uvicorn app.main:app --port 8000
# The club model is only built inside Docker (see cv-service/Dockerfile). To use it outside
# Docker, copy it out of the image:
#   docker create --name tmp golfcoach-cv-service
#   docker cp tmp:/app/models/club_swingtrace_yolo11m.onnx models/ && docker rm tmp
# then drop CLUB_DETECTION=0 and set CLUB_MODEL_PATH=$PWD/models/club_swingtrace_yolo11m.onnx

# 3. API
cd backend/GolfCoach.Api && dotnet run          # http://localhost:8080

# 4. frontend
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8080
```

After changing code in the Docker setup, rebuild only the part you changed, for example
`docker compose up -d --build cv-service` or `docker compose up -d --build web`.

## Limitations

- **2D, one camera.** All angles are measured in the video image, not in 3D, so they depend on
  where the camera stood. Rotation, club face, clubhead speed and ball flight are not measured.
- **Phases come from the hands.** Takeaway is when the hands start moving, a little after the
  club head, so the tempo reads slightly low. Chips and putts are reported as "no swing found".
- **Detection can fail** on heavy motion blur, loose clothing, dark backgrounds or a golfer who is
  small in frame. Low-confidence values are marked, and are never rated red.
- **Not checked yet:** camera movement, and whether the chosen camera angle matches the footage.
- **Browsers may not play HEVC (H.265).** Re-export as H.264 MP4 if the player stays black.
- **Single user.** There are no accounts: everyone who can open the app sees and can delete every
  swing. It is not ready to be put on the internet as it is; see
  [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md#before-deploying-publicly).

## Licence

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE). The club
detection model it builds on is AGPL-3.0 too, so a more permissive licence would not free the
app from AGPL's terms. If you run a modified version as a service, its users must be able to get
your source code.

## Third-party material

- **Club model:** [SwingTrace](https://github.com/nishsm/golf-club-detection-swingtrace) is
  AGPL-3.0, and Ultralytics (used to convert it at build time) is AGPL-3.0. The weights are
  downloaded during the Docker build, not stored in this repository.
- **Pose model:** MediaPipe Pose Landmarker, Apache-2.0.
- **Fonts:** Aspekta (SIL Open Font License) is self-hosted in `frontend/public/fonts`. Plus
  Jakarta Sans and JetBrains Mono come from Fontsource. No fonts are loaded from Google, so
  visitors' IP addresses are not sent there.
- **Swing data:** `cv-service/tests/fixtures` holds keypoints (joint coordinates only, no video)
  extracted from a publicly posted video of a professional's swing. It is used to check that a
  good swing gets no fault findings. Replace it with a swing you have the rights to before
  publishing the repository (see [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md)). The example
  numbers on the homepage are rounded and do not name any player. Do not use a real player's name
  or likeness to promote the app without their permission.
