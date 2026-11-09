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

/** Above this visibility a joint appears; the model is guessing below it (usually hidden behind the body). */
const SHOW_VISIBILITY = 0.5;
/** A joint that is showing stays until visibility drops below this, so it cannot flicker at the limit. */
const HIDE_VISIBILITY = 0.35;

// All in seconds, so that they hold at any frame rate.
const STILL_HALF_WINDOW_S = 0.2; // smoothing while a point is nearly still: removes the wobble
const MOVING_HALF_WINDOW_S = 0.05; // while it moves fast: keeps up with the swing
const MAX_GAP_S = 0.2; // missing detections up to this long are bridged
const VISIBILITY_HALF_WINDOW_S = 0.1;
const MIN_RUN_S = 0.25; // a joint appearing or vanishing for less than this is noise
// Speed in reference lengths (torso or shaft) per second: full smoothing below, light smoothing above.
const STILL_SPEED = 0.5;
const MOVING_SPEED = 1.5;

type Gappy = (number | null)[];

/** Linear interpolation across gaps of at most maxGap entries. Longer gaps stay empty. */
function bridgeGaps(values: Gappy, maxGap: number): Gappy {
  const out = [...values];
  let last = -1;
  values.forEach((v, i) => {
    if (v === null) return;
    if (last >= 0 && i - last > 1 && i - last - 1 <= maxGap) {
      const from = values[last] as number;
      for (let k = last + 1; k < i; k++) out[k] = from + ((v - from) * (k - last)) / (i - last);
    }
    last = i;
  });
  return out;
}

/** Savitzky-Golay weight (order 2) of the sample `i` steps from the centre of a window 2m+1 long. */
const savgolWeight = (i: number, m: number) =>
  (3 * (3 * m * m + 3 * m - 1 - 5 * i * i)) / ((2 * m + 3) * (2 * m + 1) * (2 * m - 1));

/** Centred smoothing: no lag. The window narrows at the ends of a run; gaps are never smoothed across. */
function savgol(values: Gappy, halfWindow: number): Gappy {
  return values.map((v, i) => {
    if (v === null) return null;
    let m = 0;
    while (m < halfWindow && values[i - m - 1] != null && values[i + m + 1] != null) m++;
    if (m < 2) return v;
    let sum = 0;
    for (let k = -m; k <= m; k++) sum += savgolWeight(k, m) * (values[i + k] as number);
    return sum;
  });
}

/**
 * Smooth a moving 2D point (normalised), strongly while it is nearly still and lightly while it moves.
 * `reference` is the body length (px) that speed is judged against; width/height make x and y comparable.
 */
function smoothPath(xs: Gappy, ys: Gappy, fps: number, width: number, height: number, reference: number): [Gappy, Gappy] {
  const half = (seconds: number) => Math.max(2, Math.round(fps * seconds));
  const gap = Math.round(fps * MAX_GAP_S);
  const x = bridgeGaps(xs, gap);
  const y = bridgeGaps(ys, gap);
  const [xLight, yLight] = [savgol(x, half(MOVING_HALF_WINDOW_S)), savgol(y, half(MOVING_HALF_WINDOW_S))];
  const [xHeavy, yHeavy] = [savgol(x, half(STILL_HALF_WINDOW_S)), savgol(y, half(STILL_HALF_WINDOW_S))];

  const speed = x.map((_, i) => {
    const [ax, ay, bx, by] = [xLight[i - 1], yLight[i - 1], xLight[i + 1], yLight[i + 1]];
    if (ax == null || ay == null || bx == null || by == null) return null;
    return (Math.hypot((bx - ax) * width, (by - ay) * height) * fps) / 2 / reference;
  });
  // The fastest speed nearby decides, so that smoothing eases off before a fast move starts.
  const reach = half(STILL_HALF_WINDOW_S);
  const moving = x.map((_, i) => {
    let top = 0;
    for (let k = i - reach; k <= i + reach; k++) top = Math.max(top, speed[k] ?? 0);
    return Math.min(1, Math.max(0, (top - STILL_SPEED) / (MOVING_SPEED - STILL_SPEED)));
  });
  const blend = (light: Gappy, heavy: Gappy): Gappy =>
    light.map((v, i) => (v === null ? null : v * moving[i] + (heavy[i] as number) * (1 - moving[i])));
  return [blend(xLight, xHeavy), blend(yLight, yHeavy)];
}

/** Remove on/off stretches shorter than minRun, gaps first: a joint would rather stay than blink. */
function dropShortRuns(flags: boolean[], minRun: number): boolean[] {
  const out = [...flags];
  for (const target of [false, true]) {
    let start = 0;
    for (let i = 1; i <= out.length; i++) {
      if (i < out.length && out[i] === out[start]) continue;
      if (out[start] === target && i - start < minRun && start > 0 && i < out.length) out.fill(!target, start, i);
      start = i;
    }
  }
  return out;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length ? sorted[sorted.length >> 1] : 0;
}

const frameRate = (file: KeypointsFile) => file.video.fps || 30;

/** One frame of the skeleton as drawn: smoothed positions, and whether each joint counts as reliable. */
export interface DisplayFrame {
  points: ([number, number] | null)[];
  sure: boolean[];
}

/**
 * The raw detections wobble and their confidence hovers around the limit, so drawing them directly
 * shakes and flickers. This makes the steady version for the player. The analysis does its own
 * cleaning; nothing here affects the measurements.
 */
export function displayFrames(file: KeypointsFile, rejected: Map<number, Set<number>>): DisplayFrame[] {
  const { frames, video } = file;
  const fps = frameRate(file);
  const landmark = (f: KeypointFrame, j: number) => (rejected.get(f.i)?.has(j) ? null : (f.lm?.[j] ?? null));
  const torso = median(
    frames.flatMap((f) =>
      f.lm
        ? [Math.hypot((f.lm[L.leftShoulder][0] - f.lm[L.leftHip][0]) * video.width, (f.lm[L.leftShoulder][1] - f.lm[L.leftHip][1]) * video.height)]
        : [],
    ),
  );
  const joints = file.landmark_names.map((_, j) => {
    const [x, y] = smoothPath(
      frames.map((f) => landmark(f, j)?.[0] ?? null),
      frames.map((f) => landmark(f, j)?.[1] ?? null),
      fps,
      video.width,
      video.height,
      torso || 1,
    );
    return { x, y, sure: steadyVisibility(frames.map((f) => landmark(f, j)?.[3] ?? 0), fps) };
  });
  return frames.map((_, k) => ({
    points: joints.map((p) => {
      const [x, y] = [p.x[k], p.y[k]];
      return x === null || y === null ? null : [x, y];
    }),
    sure: joints.map((p) => p.sure[k]),
  }));
}

function steadyVisibility(visibility: number[], fps: number): boolean[] {
  const half = Math.max(1, Math.round(fps * VISIBILITY_HALF_WINDOW_S));
  let on = false;
  const flags = visibility.map((_, i) => {
    const near = visibility.slice(Math.max(0, i - half), i + half + 1);
    const level = near.reduce((a, b) => a + b, 0) / near.length;
    on = on ? level >= HIDE_VISIBILITY : level >= SHOW_VISIBILITY;
    return on;
  });
  return dropShortRuns(flags, Math.max(3, Math.round(fps * MIN_RUN_S)));
}

/** The analysis' club track, steadied for drawing in the same way as the joints. */
export function smoothClubTrack(
  track: (ClubTrackPoint | null)[] | undefined,
  file: KeypointsFile,
): (ClubTrackPoint | null)[] | undefined {
  if (!track) return track;
  const fps = frameRate(file);
  const { width, height } = file.video;
  const column = (c: number) => track.map((t) => t?.[c] ?? null);
  const shaft = median(track.flatMap((t) => (t ? [Math.hypot((t[0] - t[2]) * width, (t[1] - t[3]) * height)] : [])));
  const [gx, gy] = smoothPath(column(0), column(1), fps, width, height, shaft || 1);
  const [hx, hy] = smoothPath(column(2), column(3), fps, width, height, shaft || 1);
  const found = dropShortRuns(track.map((t) => t?.[4] === 1), Math.max(3, Math.round(fps * MIN_RUN_S)));
  return track.map((_, i) => {
    const [a, b, c, d] = [gx[i], gy[i], hx[i], hy[i]];
    return a === null || b === null || c === null || d === null ? null : [a, b, c, d, found[i] ? 1 : 0];
  });
}

/** The club in frame `index`, from the analysis' cleaned track. */
export function clubLineAt(index: number, track: (ClubTrackPoint | null)[] | undefined): ShaftLine | null {
  const t = track?.[index];
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
