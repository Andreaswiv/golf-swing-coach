// Raw keypoints file (golfcoach.keypoints.v1) and helpers for drawing it.
import type { ClubTrackPoint } from "./api";
// Format: docs/ARCHITECTURE.md. Coordinates are 0..1 of the displayed frame.

/** [x, y, z, visibility, presence] */
export type Landmark = [number, number, number, number, number];

/** [x1, y1, x2, y2, confidence], normalised like the landmarks. */
export type ClubBox = [number, number, number, number, number];
export type ClubPart = "shaft" | "head" | "hands";

export interface KeypointFrame {
  i: number;
  t: number;
  n: number;
  lm: Landmark[] | null;
  /** Best box per club part. Absent when the club detector did not look at this frame (it only
   *  runs around the swing); present but without a part when it looked and did not find it. */
  club?: Partial<Record<ClubPart, ClubBox>>;
}

export interface KeypointsFile {
  format: string;
  landmark_names: string[];
  video: { width: number; height: number; fps: number; frame_count: number };
  club_model?: string | null;
  /** Inclusive frame range the club detector ran on (null/absent in older files: every frame). */
  club_frames?: [number, number] | null;
  frames: KeypointFrame[];
}

export async function loadKeypoints(url: string): Promise<KeypointsFile> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load keypoints (${res.status})`);
  const data = (await res.json()) as KeypointsFile;
  if (data.format !== "golfcoach.keypoints.v1") throw new Error(`Unknown keypoints format: ${data.format}`);
  return data;
}

/**
 * Index of the frame on screen at `time` (seconds): the last frame whose
 * timestamp is not after it. A small tolerance absorbs rounding in `t`.
 */
export function frameIndexAt(frames: KeypointFrame[], time: number): number {
  let lo = 0;
  let hi = frames.length - 1;
  const target = time + 0.001;
  if (hi < 0 || target < frames[0].t) return 0;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t <= target) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export type Side = "left" | "right" | "center";

// MediaPipe Pose landmark indices.
export const L = {
  nose: 0,
  leftEar: 7,
  rightEar: 8,
  leftShoulder: 11,
  rightShoulder: 12,
  leftElbow: 13,
  rightElbow: 14,
  leftWrist: 15,
  rightWrist: 16,
  leftHip: 23,
  rightHip: 24,
  leftKnee: 25,
  rightKnee: 26,
  leftAnkle: 27,
  rightAnkle: 28,
  leftHeel: 29,
  rightHeel: 30,
  leftFootIndex: 31,
  rightFootIndex: 32,
} as const;

/** Body segments to draw. Hands and most face points are left out: they add clutter, not information. */
export const SEGMENTS: [number, number, Side][] = [
  [L.leftShoulder, L.rightShoulder, "center"],
  [L.leftHip, L.rightHip, "center"],
  [L.leftShoulder, L.leftHip, "left"],
  [L.rightShoulder, L.rightHip, "right"],
  [L.leftShoulder, L.leftElbow, "left"],
  [L.leftElbow, L.leftWrist, "left"],
  [L.rightShoulder, L.rightElbow, "right"],
  [L.rightElbow, L.rightWrist, "right"],
  [L.leftHip, L.leftKnee, "left"],
  [L.leftKnee, L.leftAnkle, "left"],
  [L.leftAnkle, L.leftHeel, "left"],
  [L.leftHeel, L.leftFootIndex, "left"],
  [L.leftAnkle, L.leftFootIndex, "left"],
  [L.rightHip, L.rightKnee, "right"],
  [L.rightKnee, L.rightAnkle, "right"],
  [L.rightAnkle, L.rightHeel, "right"],
  [L.rightHeel, L.rightFootIndex, "right"],
  [L.rightAnkle, L.rightFootIndex, "right"],
  [L.leftEar, L.rightEar, "center"],
];

export const JOINTS: [number, Side][] = [
  [L.nose, "center"],
  ...Object.entries(L)
    .filter(([name]) => name !== "nose")
    .map(([name, idx]): [number, Side] => [idx, name.startsWith("left") ? "left" : "right"]),
];

/** Below this visibility the model is guessing (usually the joint is hidden behind the body). */
export const CONFIDENT_VISIBILITY = 0.5;

/** Club boxes below this confidence are ignored, as in the analysis (cv-service/app/swing/club.py). */
export const CLUB_MIN_CONF = 0.5;

/** The club in frame `index`: from the analysis' cleaned track when there is one, else from the raw boxes. */
export function clubLineAt(
  frame: KeypointFrame,
  index: number,
  track: (ClubTrackPoint | null)[] | undefined,
  aspect: number,
): ShaftLine | null {
  if (!track) return shaftLine(frame, aspect);
  const t = track[index];
  return t ? { grip: [t[0], t[1]], head: [t[2], t[3]], headFound: t[4] === 1 } : null;
}

/** Frame index -> landmark indices the analysis dropped there (by landmark name). */
export function rejectedByFrame(
  file: KeypointsFile,
  rejected: Record<string, number[]> | undefined,
): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>();
  for (const [name, frames] of Object.entries(rejected ?? {})) {
    const j = file.landmark_names.indexOf(name);
    if (j < 0) continue;
    for (const f of frames) {
      if (!out.has(f)) out.set(f, new Set());
      out.get(f)!.add(j);
    }
  }
  return out;
}

export function hasClubData(file: KeypointsFile): boolean {
  return file.frames.some((f) => f.club && Object.keys(f.club).length > 0);
}

export interface ShaftLine {
  grip: [number, number];
  head: [number, number];
  /** False when the head end was inferred from the shaft box (the club head itself was not found). */
  headFound: boolean;
}

const center = (b: ClubBox): [number, number] => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];

/**
 * The club in one frame, the way the analysis reads it: grip = centre of the hands box (else the
 * mean of the wrists), head = centre of the head box, else the far end of the shaft box (the corner
 * of the box diagonal that does not start next to the grip). Null when there is no club to draw.
 * `aspect` (width / height) makes "nearest" a pixel distance, as in the analysis.
 */
export function shaftLine(frame: KeypointFrame, aspect = 1): ShaftLine | null {
  const club = frame.club;
  if (!club) return null;
  const part = (p: ClubPart) => {
    const b = club[p];
    return b && b[4] >= CLUB_MIN_CONF ? b : undefined;
  };
  const hands = part("hands");
  const head = part("head");
  const shaft = part("shaft");

  let grip: [number, number] | null = hands ? center(hands) : null;
  if (!grip && frame.lm) {
    const a = frame.lm[L.leftWrist];
    const b = frame.lm[L.rightWrist];
    grip = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  }
  if (!grip) return null;
  if (head) return { grip, head: center(head), headFound: true };
  if (!shaft) return null;

  const g = grip;
  const corners: [number, number][][] = [
    [[shaft[0], shaft[1]], [shaft[2], shaft[3]]],
    [[shaft[0], shaft[3]], [shaft[2], shaft[1]]],
  ];
  let best: { d: number; far: [number, number] } | null = null;
  for (const [a, b] of corners) {
    for (const [near, far] of [[a, b], [b, a]]) {
      const d = Math.hypot((near[0] - g[0]) * aspect, near[1] - g[1]);
      if (!best || d < best.d) best = { d, far };
    }
  }
  return { grip, head: best!.far, headFound: false };
}
