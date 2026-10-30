# Architecture notes

## Services

| Service | Port | Responsibility |
|---|---|---|
| `web` (nginx) | 5173 | Serves the built React app; proxies `/api` to the API; streams uploads |
| `api` (ASP.NET Core) | 8080 | Upload and validation, database, job queue and worker, file serving, delete |
| `cv-service` (FastAPI) | 8000 | Video probing, pose estimation, quality checks, writes keypoints |
| `db` (PostgreSQL) | 5432 | Videos, analyses, keypoint-file pointers, phases, measurements |

The API and the CV service share the `./data` folder. Every path in the database and in messages between services is **relative** to that folder (`videos/{id}.mp4`, `keypoints/{id}.json`). The CV service refuses any path that resolves outside it, and so does the API.

## Decisions and their trade-offs

- **Files, not rows, for videos and keypoints.** A 3-second 120 fps swing has about 360 frames x 33 landmarks. As JSON that is a few MB and loads in one request; as database rows it would be about 12,000 per video.
- **MediaPipe Tasks API** (`PoseLandmarker`), not the legacy `mp.solutions.pose`, which current MediaPipe releases no longer ship. It needs a `.task` model file, downloaded when the image is built.
- **Polling, not queues.** The API worker submits to the CV service and polls its job every second, copying progress into PostgreSQL. The browser polls the API. No Redis or RabbitMQ. Unfinished analyses are re-queued from the database on API start; if the CV service restarts and forgets a job, the worker resubmits it (up to 3 times).
- **One job at a time.** Pose estimation is CPU-bound; running videos in parallel would only slow each one down.
- **Raw keypoints are stored.** Smoothing, left-hand mirroring, phase detection and measurements (`cv-service/app/swing`) are computed from the saved file, so improving them never requires re-running the pose model: `POST /api/analyses/{id}/reanalyze` re-runs them in under a second.
- **EF Core migrations** (`backend/GolfCoach.Api/Data/Migrations`), applied on API start. Databases created by the earlier `EnsureCreated` are baselined: the `Initial` migration is recorded as applied without running it. New migration: `dotnet ef migrations add <Name> --output-dir Data/Migrations` in `backend/GolfCoach.Api` (the .NET 10 SDK and `dotnet-ef` are needed; the `mcr.microsoft.com/dotnet/sdk:10.0` image works).
- **Ollama runs on the host, not in Compose** (when it is added). Docker on macOS cannot use the Apple GPU, so a containerised model would be CPU-only and much slower.

## API (`/api`)

| Method and path | Purpose |
|---|---|
| `POST /analyses` | multipart: `video`, `cameraAngle` (`face_on`\|`down_the_line`), `handedness` (`right`\|`left`), optional `club`. Returns `201` with the analysis |
| `GET /analyses` | newest first |
| `GET /analyses/{id}` | status, progress, stage, error, video details, quality report, swing analysis |
| `GET /analyses/{id}/video` | the original file, with HTTP range support for seeking |
| `GET /analyses/{id}/keypoints` | the raw keypoints JSON |
| `POST /analyses/{id}/reanalyze` | re-runs the swing analysis from the saved keypoints and replaces phases and measurements; `409` if not completed |
| `DELETE /analyses/{id}` | removes rows and files; `409` while still processing |
| `GET /health/live`, `GET /health` | liveness; dependency readiness (database, CV service, model file) |

Errors use RFC 7807 problem details (`title`, `detail`). Status values: `queued`, `processing`, `completed`, `failed`.

## CV service

| Method and path | Purpose |
|---|---|
| `POST /jobs` | body: `analysis_id`, `video_path`, `keypoints_path`, `camera_angle`, `handedness`. `202` with the job |
| `GET /jobs/{id}` | `status`, `progress`, `stage`, `error`, `result`; `404` if unknown (after a restart) |
| `POST /analyze` | body: `keypoints_path`. Runs the swing analysis on a saved keypoints file and returns it (synchronous, no pose model) |
| `GET /health` | model and data folder presence |

`PoseEstimator` (`cv-service/app/pose/base.py`) is the only thing the pipeline knows about pose models. To try another model, implement `estimate()` returning 33 MediaPipe-layout landmarks and pass it to `JobManager`.

## Keypoints file (`golfcoach.keypoints.v1`)

```json
{
  "format": "golfcoach.keypoints.v1",
  "pose_model": "mediapipe-pose-landmarker:pose_landmarker_full",
  "coordinate_space": "normalized_image",
  "landmark_names": ["nose", "left_eye_inner", "..."],
  "landmark_fields": ["x", "y", "z", "visibility", "presence"],
  "video": {"width": 1920, "height": 1080, "fps": 60.0, "frame_count": 180, "rotation_degrees": 0},
  "camera_angle": "face_on",
  "handedness": "right",
  "frames": [{"i": 0, "t": 0.0, "n": 1, "lm": [[0.51, 0.2, -0.1, 0.99, 1.0], "... 33 rows"]}]
}
```

`x`, `y` are 0..1 across the displayed frame with the origin at the top left. `z` is a relative depth hint from the model, not a measurement. `t` is the frame's timestamp in seconds (taken from the container so variable-frame-rate phone footage stays in sync with the browser player). `n` is how many people were detected; `lm` is the chosen golfer, or `null` when nobody was found. The data is raw: not smoothed and not mirrored for left-handed golfers.

## Swing analysis (`swing-0.3`)

`cv-service/app/swing`, run at the end of every job and by `POST /analyze`:

1. **Series** (`series.py`): coordinates to pixels (so angles are not distorted by the aspect ratio), left-handed golfers mirrored (x flipped, left/right landmarks swapped; afterwards lead side = `left_*`), gaps of up to 6 frames interpolated, Savitzky-Golay smoothing (window about 0.1 s, at least 5 frames, order 2).
2. **Phases** (`phases.py`), from the hands' path in torso lengths and frames, never seconds: downswing anchor = fastest downward hand movement; impact = lowest hands after it; top = end of the highest hand position before it; address = middle of the last rest at the hand position held longest; takeaway = first frame after that rest (hands, not clubhead); finish = first frame at the highest follow-through position.
3. **Measurements** (`measurements.py`), 2D, per camera angle. Down-the-line: spine angle at address/top/impact and its change, trail knee flex, rear hip (backside line) toward the ball, head height change. Address and top values are medians over the held frames; impact values are checked one real frame either side and lose confidence if they change. Face-on: shoulder tilt, hip and head shift, lead arm bend, stance width. Both: tempo ratio and durations, left out when slow motion is suspected (downswing longer than 0.6 s of video time), because phone slow motion often changes speed within a clip.

4. **Feedback** (`feedback.py`), a rules engine: each rule compares measurements with a broad typical range (constants at the top of the file) and fills a fixed text template, so every sentence traces back to a number. Kinds: `strength` (in range, confidence >= 0.5; strengths on uncertain data are left out), `improve` (clearly out of range, confidence >= 0.5), `watch` (mildly out of range, or clearly out on uncertain data). Each finding has a title, what was seen, why it matters and a drill, plus the frame to show. A summary sentence and a "not judged from this video" list (camera-angle blind spots, slow-motion timing, club not tracked) come with it. A local language model (Ollama) may later rephrase this text; it must not change the findings.

Result: `version`, `status` (`ok`, `no_swing_found`, `error`), `phases[]` (`name`, `frame_index`, `timestamp_s`, `method`, `confidence`), `measurements[]` (`name`, `phase`, `frame_index`, `value`, `unit` in `deg`/`% torso`/`ratio`/`s`, `type` `measured`/`estimated`, `confidence`), `notes[]` (`code`, `message`), `feedback` (`summary`, `findings[]`, `not_checked[]`; `null` when no swing was found). Confidence is a heuristic 0..1 score (phase confidence times a joint visibility score; impact also times the frame-rate factor), not a probability. The analysis never fails a job: problems become a status and a note.

## Database

`Videos` (file, camera angle, handedness, club, resolution, fps, duration, frames) 1 to many `Analyses` (status, progress, stage, pipeline version, pose model, quality JSON) 1 to 1 `KeypointSets` (file path, frame count, format), and 1 to many `Phases` and `Measurements`. `Analyses.SwingJson` holds the whole swing analysis result (passed through to the frontend as `swing`); `Phases` and `Measurements` hold the same numbers as rows for querying across swings, replaced on every re-analysis. Deleting an analysis cascades; the video is deleted with its last analysis.

Planned extensions (not built): `Users` (add `UserId` to Videos), `Findings`, `Drills`, `Recommendations`, `Comparisons`.
