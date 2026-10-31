import { useEffect, useId, useState, type ReactNode, type RefObject } from "react";
import { reducedMotion } from "@/lib/motion";

/*
  A soft white character with green joints, drawn from joint positions: the homepage shows swings
  as this figure instead of video. Positions are in pixels; z is MediaPipe's depth (larger = further).
*/

export type Joint = [number, number, number];
export type JointName = "nose" | "ls" | "rs" | "le" | "re" | "lw" | "rw" | "lh" | "rh" | "lk" | "rk" | "la" | "ra";
export type Pose = Record<JointName, Joint>;
export type Box = { x: number; y: number; w: number; h: number };

/** One frame around every pose (and any extra points), so the figure stays put while it moves. */
export function boundsOf(poses: (Pose | null)[], extra: [number, number][] = [], padShare = 0.12): Box | null {
  const pts = [...poses.flatMap((p) => (p ? Object.values(p).map(([x, y]) => [x, y] as [number, number]) : [])), ...extra];
  if (!pts.length) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const pad = (y1 - y0) * padShare;
  return { x: x0 - pad, y: y0 - pad, w: x1 - x0 + pad * 2, h: y1 - y0 + pad * 2 };
}

/**
 * Frame index playing through `count` frames over `swingMs`. With `once` it plays a single time and
 * holds the last frame, and plays again each time the element comes back after leaving the screen
 * completely; otherwise it holds the last frame for `holdMs` and starts again. Only runs while
 * `ref`'s element is on screen and the tab is visible.
 */
export function useSwingPlayback(
  count: number,
  swingMs: number,
  ref: RefObject<Element | null>,
  { once = false, holdMs = 0 }: { once?: boolean; holdMs?: number } = {},
) {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(false);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let onScreen = false;
    const update = () => setVisible(onScreen && document.visibilityState === "visible");
    const observer = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      // Not a single pixel left on screen: play from the start next time it comes into view.
      // (A hidden tab pauses but does not rewind.)
      if (!onScreen) setFinished(false);
      update();
    });
    observer.observe(el);
    document.addEventListener("visibilitychange", update);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, [ref]);

  useEffect(() => {
    if (count <= 0) return;
    if (reducedMotion()) return setIndex(count - 1);
    if (!visible || finished) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      if (once && elapsed >= swingMs) {
        setIndex(count - 1);
        setFinished(true);
        return;
      }
      const t = elapsed % (swingMs + holdMs);
      setIndex(Math.min(count - 1, Math.floor((t / swingMs) * count))); // same value: React skips the render
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [count, swingMs, holdMs, once, visible, finished]);
  return index;
}

const LIMBS: [JointName, JointName, number][] = [
  // [from, to, thickness as a share of torso length]
  ["ls", "le", 0.17],
  ["le", "lw", 0.13],
  ["rs", "re", 0.17],
  ["re", "rw", 0.13],
  ["lh", "lk", 0.26],
  ["lk", "la", 0.18],
  ["rh", "rk", 0.26],
  ["rk", "ra", 0.18],
];
const JOINTS: JointName[] = ["ls", "rs", "le", "re", "lh", "rh", "lk", "rk"];

export const torsoLength = (p: Pose) =>
  Math.hypot((p.ls[0] + p.rs[0] - p.lh[0] - p.rh[0]) / 2, (p.ls[1] + p.rs[1] - p.lh[1] - p.rh[1]) / 2);

type Props = {
  pose: Pose;
  box: Box;
  /** [grip x, grip y, head x, head y]: the club, drawn from the hands. */
  club?: [number, number, number, number] | null;
  /** Recent club-head positions, oldest first: a glowing trail. */
  trail?: [number, number][];
  label?: string;
  /** "dark": drawn on a dark background (darker shadow, light club). */
  tone?: "light" | "dark";
  /** Extra SVG drawn on top, in the same coordinates. */
  children?: ReactNode;
};

export function PoseFigure({ pose, box, club, trail = [], label = "A figure moving through a golf swing", tone = "light", children }: Props) {
  const shadow = tone === "dark" ? "#06140c" : "#cfd2cd";
  const clubColor = tone === "dark" ? "#e9ede7" : "#2b2b2b";
  const uid = useId().replace(/:/g, "");
  const torso = torsoLength(pose);
  const mid = (a: JointName, b: JointName) => [(pose[a][0] + pose[b][0]) / 2, (pose[a][1] + pose[b][1]) / 2];
  // Far limbs (larger z) first and paler, near limbs on top.
  const depth = ([a, b]: [JointName, JointName, number]) => pose[a][2] + pose[b][2];
  const limbs = [...LIMBS].sort((a, b) => depth(b) - depth(a));
  const zs = LIMBS.map(depth);
  const zMid = (Math.min(...zs) + Math.max(...zs)) / 2;
  const head = [pose.nose[0], pose.nose[1] - torso * 0.05];
  const neck = mid("ls", "rs");
  const torsoPath = (["ls", "rs", "rh", "lh"] as JointName[]).map((j, i) => `${i ? "L" : "M"}${pose[j][0]} ${pose[j][1]}`).join(" ") + " Z";
  const trailPts = trail.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} className="size-full overflow-visible" role="img" aria-label={label}>
      <defs>
        <linearGradient id={`${uid}-trail`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffd59a" />
          <stop offset="1" stopColor="#ff8a3d" />
        </linearGradient>
      </defs>

      {trail.length > 1 && (
        <g fill="none" strokeLinecap="round" strokeLinejoin="round">
          {/* Glow: wide, faint strokes under the line (a blur filter would be recomputed every frame). */}
          <polyline points={trailPts} stroke="#ff9a4d" strokeOpacity="0.12" strokeWidth={torso * 0.22} />
          <polyline points={trailPts} stroke="#ff9a4d" strokeOpacity="0.22" strokeWidth={torso * 0.11} />
          <polyline points={trailPts} stroke={`url(#${uid}-trail)`} strokeWidth={torso * 0.035} />
        </g>
      )}

      {/* Volume: a faint offset shadow in two widths under the body. */}
      <g transform={`translate(${torso * 0.05} ${torso * 0.06})`} strokeLinecap="round" strokeLinejoin="round">
        {[0.34, 0.12].map((extra, i) => (
          <g key={i} opacity={tone === "dark" ? (i ? 0.35 : 0.18) : i ? 0.3 : 0.15}>
            <path d={torsoPath} fill={shadow} stroke={shadow} strokeWidth={torso * (0.28 + extra)} />
            {LIMBS.map(([a, b, w]) => (
              <line key={`${a}${b}`} x1={pose[a][0]} y1={pose[a][1]} x2={pose[b][0]} y2={pose[b][1]} stroke={shadow} strokeWidth={torso * (w + extra)} />
            ))}
          </g>
        ))}
      </g>

      <g>
        {limbs.map(([a, b, w]) => {
          const far = depth([a, b, w]) > zMid;
          return (
            <line
              key={`${a}-${b}`}
              x1={pose[a][0]}
              y1={pose[a][1]}
              x2={pose[b][0]}
              y2={pose[b][1]}
              stroke={far ? "#ebedea" : "#ffffff"}
              strokeOpacity={far ? 0.85 : 1}
              strokeWidth={torso * w}
              strokeLinecap="round"
            />
          );
        })}
        <path d={torsoPath} fill="#ffffff" stroke="#ffffff" strokeWidth={torso * 0.28} strokeLinejoin="round" />
        <circle cx={head[0]} cy={head[1]} r={torso * 0.23} fill="#ffffff" />
        {JOINTS.map((j) => (
          <ellipse key={j} cx={pose[j][0]} cy={pose[j][1]} rx={torso * 0.1} ry={torso * 0.08} fill="#9fd585" fillOpacity="0.9" />
        ))}
        <ellipse cx={(head[0] + neck[0]) / 2} cy={(head[1] + neck[1]) / 2} rx={torso * 0.09} ry={torso * 0.09} fill="#9fd585" fillOpacity="0.9" />
      </g>

      {club && (
        <g strokeLinecap="round">
          <line x1={club[0]} y1={club[1]} x2={club[2]} y2={club[3]} stroke={clubColor} strokeWidth={torso * 0.035} />
          <circle cx={club[2]} cy={club[3]} r={torso * 0.06} fill={clubColor} />
        </g>
      )}
      {children}
    </svg>
  );
}
