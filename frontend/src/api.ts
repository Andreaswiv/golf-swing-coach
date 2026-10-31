// Typed client for the ASP.NET Core API. All paths are relative (/api/...):
// Vite proxies them in development and nginx proxies them in Docker.

export type CameraAngle = "face_on" | "down_the_line";
export type Handedness = "right" | "left";
export type AnalysisStatus = "queued" | "processing" | "completed" | "failed";

export interface QualityWarning {
  code: string;
  severity: "info" | "warning" | "high";
  message: string;
}

/** Produced by the Python service; keys are snake_case on purpose. */
export interface QualityReport {
  overall: "good" | "warning" | "poor";
  warnings: QualityWarning[];
  stats: Record<string, unknown>;
  checks_not_run: string[];
}

/** Swing analysis from the Python service (cv-service/app/swing); keys are snake_case on purpose. */
export type PhaseName = "address" | "takeaway" | "top" | "impact" | "finish";
/** A phase, or the stretch between top and impact (club measurements are taken halfway down). */
export type MomentName = PhaseName | "downswing";

export interface SwingPhase {
  name: PhaseName;
  frame_index: number;
  timestamp_s: number;
  method: string;
  confidence: number;
}

export interface SwingMeasurement {
  name: string;
  phase: MomentName | null;
  frame_index: number;
  value: number;
  unit: string;
  type: "measured" | "estimated";
  confidence: number;
  /** Traffic light from the feedback limits (swing-0.5+); null = no judgement (context, or too uncertain). */
  rating?: Rating | null;
  /** What good swings show, in words. */
  typical?: string | null;
}

export type Rating = "good" | "watch" | "bad";

export interface SwingFinding {
  code: string;
  kind: "strength" | "improve" | "watch";
  title: string;
  detail: string;
  why: string | null;
  drill: string | null;
  phase: MomentName | null;
  frame_index: number | null;
  confidence: number;
  measurements: string[];
}

export interface SwingFeedback {
  summary: string;
  findings: SwingFinding[];
  not_checked: string[];
}

/** Point in normalised image coordinates (0..1 of the video frame, not mirrored). */
export type ImagePoint = [number, number];

export type ClubTrackPoint = [number, number, number, number, 0 | 1];

/** Club tracking summary (cv-service/app/swing/club.py). */
export interface ClubSummary {
  /** False when the video was processed without the club detector. */
  tracked: boolean;
  /** Share of frames (0..1) where each part was found. */
  found_share?: { shaft: number; head: number; hands: number };
  /** Frames the club detector looked at (it only runs around the swing), out of all frames. */
  frames_checked?: number;
  frames_total?: number;
  /** Swing plane: the address shaft line from the ball through the grip, extended. Down-the-line only. */
  plane?: { from: ImagePoint; to: ImagePoint } | null;
  /** Frames where a club detection was thrown out as physically impossible. */
  rejected_frames?: number;
  /**
   * The club as the analysis used it, per frame (index = frame index): [grip x, grip y, head x,
   * head y, 1 if the head was detected / 0 if inferred], normalised, or null for no club. Detections
   * that cannot be real are already removed. Absent before swing-0.5.
   */
  track?: (ClubTrackPoint | null)[];
  /** Toes relative to the ball in % torso; negative = between the ball and the golfer. */
  toes_from_ball?: number | null;
}

export interface SwingAnalysis {
  version: string;
  status: "ok" | "no_swing_found" | "error";
  camera_angle: CameraAngle;
  mirrored_for_left_handed: boolean;
  smoothing: { method: string; window_frames: number; polyorder: number } | null;
  phases: SwingPhase[];
  measurements: SwingMeasurement[];
  notes: { code: string; message: string }[];
  /** Absent in results from swing-0.1 (re-run the analysis to get it). */
  feedback?: SwingFeedback | null;
  /** Absent before swing-0.4. */
  club?: ClubSummary;
  /** Frames where each joint (raw landmark name) was dropped as impossible. Absent before swing-0.5. */
  rejected_landmarks?: Record<string, number[]>;
}

export interface VideoInfo {
  id: string;
  originalFileName: string;
  cameraAngle: CameraAngle;
  handedness: Handedness;
  club: string | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  durationSeconds: number | null;
  orientation: string | null;
  uploadedAt: string;
}

export interface Analysis {
  id: string;
  status: AnalysisStatus;
  progress: number;
  stage: string;
  error: string | null;
  createdAt: string;
  completedAt: string | null;
  pipelineVersion: string | null;
  poseModel: string | null;
  video: VideoInfo;
  quality: QualityReport | null;
  keypoints: { frameCount: number; dataFormat: string } | null;
  swing: SwingAnalysis | null;
}

export interface HealthReport {
  status: "ok" | "degraded";
  database: boolean;
  cvService: boolean;
  poseModelPresent: boolean | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? body.title ?? body.error ?? `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(await readError(res), res.status);
  return (await res.json()) as T;
}

export const api = {
  health: () => fetch("/api/health").then(json<HealthReport>),
  list: () => fetch("/api/analyses").then(json<Analysis[]>),
  get: (id: string) => fetch(`/api/analyses/${id}`).then(json<Analysis>),
  async remove(id: string) {
    const res = await fetch(`/api/analyses/${id}`, { method: "DELETE" });
    if (!res.ok) throw new ApiError(await readError(res), res.status);
  },
  reanalyze: (id: string) => fetch(`/api/analyses/${id}/reanalyze`, { method: "POST" }).then(json<Analysis>),
  videoUrl: (id: string) => `/api/analyses/${id}/video`,
  keypointsUrl: (id: string) => `/api/analyses/${id}/keypoints`,

  /** XHR rather than fetch so we can report upload progress for large videos. */
  upload(
    form: { file: File; cameraAngle: CameraAngle; handedness: Handedness; club: string },
    onProgress: (fraction: number) => void,
  ): Promise<Analysis> {
    return new Promise((resolve, reject) => {
      const data = new FormData();
      data.append("video", form.file);
      data.append("cameraAngle", form.cameraAngle);
      data.append("handedness", form.handedness);
      if (form.club) data.append("club", form.club);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/analyses");
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onerror = () => reject(new ApiError("Could not reach the server. Is the API running?", 0));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) return resolve(xhr.response as Analysis);
        const body = xhr.response as { detail?: string; title?: string } | null;
        reject(new ApiError(body?.detail ?? body?.title ?? `Upload failed (${xhr.status})`, xhr.status));
      };
      xhr.send(data);
    });
  },
};

export const CLUBS = [
  "Driver",
  "Fairway wood",
  "Hybrid",
  "Long iron (3–5)",
  "Mid iron (6–7)",
  "Short iron (8–9)",
  "Wedge",
  "Putter",
] as const;

export const MAX_UPLOAD_MB = 500;
/** Longest video accepted. Keep in sync with MAX_VIDEO_SECONDS in cv-service/app/pipeline.py. */
export const MAX_VIDEO_SECONDS = 15;
export const ACCEPTED_EXTENSIONS = [".mp4", ".mov", ".m4v"];

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "–";
  return `${seconds.toFixed(1)} s`;
}

export function angleLabel(a: CameraAngle): string {
  return a === "face_on" ? "Face-on" : "Down-the-line";
}
