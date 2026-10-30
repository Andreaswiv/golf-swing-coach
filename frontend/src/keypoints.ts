// Raw keypoints file (golfcoach.keypoints.v1) and helpers for drawing it.
// Format: docs/ARCHITECTURE.md. Coordinates are 0..1 of the displayed frame.

/** [x, y, z, visibility, presence] */
export type Landmark = [number, number, number, number, number];

export interface KeypointFrame {
  i: number;
  t: number;
  n: number;
  lm: Landmark[] | null;
}

export interface KeypointsFile {
  format: string;
  landmark_names: string[];
  video: { width: number; height: number; fps: number; frame_count: number };
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
