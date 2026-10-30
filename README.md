# Swing Coach: AI golf swing analysis

Upload a golf swing video and the app finds your body joints in every frame using computer vision, checks the video quality, detects the swing phases, measures posture and movement, and turns that into plain-language feedback with drills. Everything runs on your own computer. Videos are never sent to a cloud service.

**Status:** Milestones 1 to 3 plus written feedback (foundation, upload, pose extraction, skeleton overlay, swing phases, 2D measurements, rules-based feedback) run end to end on Apple Silicon and have been checked against one real down-the-line swing. See [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) for exactly what has and has not been tested.

## Technology stack

| Part | Technology | Why |
|---|---|---|
| Frontend | React 19, TypeScript, Tailwind CSS 4, Vite | Fast dev loop; Recharts is added in Milestone 4 when the first graph exists |
| API | ASP.NET Core (net10.0), EF Core, Npgsql | Owns uploads, the database, and job orchestration |
| Computer vision | Python 3.12, FastAPI, OpenCV, MediaPipe Pose Landmarker | CPU-only, runs on Apple Silicon and x86_64 |
| Database | PostgreSQL 16 | Structured data only; videos and keypoints are files |
| Runtime | Docker Compose | One command starts everything |
| Coaching feedback | Rules engine (built); Ollama later | Fixed rules turn measurements into findings and drills; a language model may later rephrase them, never produce them |

## How it fits together

```
Browser ──> web (nginx :5173) ──/api──> api (ASP.NET :8080) ──HTTP──> cv-service (FastAPI :8000)
                                           │                              │
                                           ├── PostgreSQL (:5432)         │
                                           └── ./data (videos, keypoints) ┘  shared folder
```

1. The browser uploads the video to the API. The API validates it, saves it to `data/videos/`, creates an `Analysis` row and queues it.
2. A background worker sends the job to the CV service and polls its progress, copying it into the database.
3. The CV service decodes the video, runs MediaPipe on every frame, writes raw keypoints to `data/keypoints/{id}.json`, and returns video metadata and a quality report.
4. The browser polls the API for status, then shows the video, details and quality report.

More detail, API reference and data formats: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Folder structure

```
backend/                 ASP.NET Core API (GolfCoach.Api) and tests (GolfCoach.Api.Tests)
cv-service/              Python FastAPI service: app/ (pipeline, pose, quality, jobs) and tests/
frontend/                React + TypeScript + Tailwind app (src/pages, src/components, src/api.ts)
data/                    videos/ and keypoints/ (git-ignored; your personal data)
scripts/                 doctor.sh, verify.sh, download_pose_model.sh
docs/                    architecture and data-format notes
docker-compose.yml       the full local stack
```

## Requirements

- **Docker Desktop** for Mac (Apple Silicon build), with at least 6 GB of memory assigned to Docker.
- About 5 GB of free disk space for images, plus space for your videos.
- Internet access on the first build only (base images, packages, the pose model).

Node, Python and the .NET SDK are only needed if you want to run a service outside Docker.

Check your machine first:

```bash
scripts/doctor.sh
```

## Configuration

Defaults work out of the box. To change anything, copy `.env.example` to `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `POSE_MODEL_VARIANT` | `full` | `lite`, `full` or `heavy`. Needs `docker compose build cv-service` after a change |
| `MAX_PROCESS_DIM` | `1280` | Longest video side used for pose estimation (lower is faster) |
| `NUM_POSES` | `2` | People the model may report per frame (used for the multiple-people warning) |
| `UPLOAD_MAX_MB` | `500` | Upload limit |
| `POSTGRES_*` | `golfcoach` | Database name, user and password |

All ports bind to `127.0.0.1`, so the app is reachable only from your computer.

## Run it

```bash
docker compose up --build        # first run takes a few minutes
```

Then open <http://localhost:5173>. In a second terminal:

```bash
scripts/verify.sh                       # checks every service and the links between them
scripts/verify.sh ~/Movies/swing.mp4    # also uploads a real video and waits for the result
ANGLE=down_the_line HAND=left scripts/verify.sh swing.mov
```

Stop with `Ctrl+C` (or `docker compose down`). To delete the database too: `docker compose down -v`. Delete a video and its analysis from the app with the Delete buttons; that removes the video file, the keypoints file and the database rows.

### Running services outside Docker (optional)

```bash
# 1. database only
docker compose up db

# 2. CV service (Python 3.12 recommended)
cd cv-service && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
../scripts/download_pose_model.sh full
POSE_MODEL_PATH=$PWD/models/pose_landmarker_full.task DATA_DIR=$PWD/../data \
  uvicorn app.main:app --port 8000

# 3. API (needs the .NET 10 SDK)
cd backend/GolfCoach.Api && dotnet run          # http://localhost:8080

# 4. frontend
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8080
```

## Tests

```bash
# CV service (no model file needed; tests use a fake pose estimator and a synthetic video)
cd cv-service && pip install -r requirements-dev.txt && pytest

# API unit tests
cd backend && dotnet test GolfCoach.slnx

# Frontend type check and production build
cd frontend && npm install && npm run build
```

The tests cover logic and contracts. They do **not** replace trying a real swing video, which is the real test of the pose estimation.

## Recording a good video

60 fps or higher (120 fps is better), the whole body and club in frame, a steady tripod, bright even light, only the golfer in view, and the camera either face-on (in front, facing your chest) or down-the-line (behind the ball, looking along the target line). The app warns about problems but never rejects a video for low frame rate alone; it lowers its confidence instead.

## Known limitations

- Joint positions come from ordinary 2D video. The app does not measure 3D rotation, club path, swing plane, clubhead speed or forces, and will not claim to.
- MediaPipe can lose or swap joints on fast motion, motion blur, loose clothing, dark backgrounds, or when the golfer is small in frame. The quality report shows how often a person was detected.
- Two quality checks are **not implemented yet**: camera movement and whether the selected camera angle matches the footage. The report lists them as "not checked" so a clean report is not mistaken for a pass.
- The skeleton overlay draws the raw, unsmoothed joint positions, so some jitter is expected. Phases and measurements use smoothed positions.
- Measurements are 2D projections from one camera, not true 3D angles, and the club is not tracked: takeaway is when the hands start moving, and impact is the hands' lowest point.
- Phone slow-motion clips saved at normal speed are detected from the downswing duration; timing values (tempo, durations) are then left out.
- Feedback comes from fixed rules with broad typical ranges, not a coach or a trained model. It only covers what one 2D camera angle can show, and says what it could not judge. Graphs are Milestone 4.
- Browsers may not play HEVC (H.265) video. Re-export as H.264 MP4 if the player stays black.
- No user accounts. The app assumes a single local user.
