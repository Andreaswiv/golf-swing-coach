import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import type { SwingPhase } from "../api";
import {
  CONFIDENT_VISIBILITY,
  JOINTS,
  SEGMENTS,
  frameIndexAt,
  loadKeypoints,
  type KeypointFrame,
  type KeypointsFile,
  type Side,
} from "../keypoints";
import { PHASE_HINT, PHASE_LABEL } from "../swingLabels";
import { ChevronLeft, ChevronRight } from "./icons";

const SPEEDS = [0.1, 0.25, 0.5, 1];

const COLORS: Record<Side, string> = {
  left: "#4aa3df",
  right: "#f0b93a",
  center: "#ffffff",
};

export interface SwingPlayerHandle {
  /** Pause and show the given frame. */
  seekToFrame(index: number): void;
}

interface Props {
  videoUrl: string;
  keypointsUrl: string | null;
  phases?: SwingPhase[];
  ref?: Ref<SwingPlayerHandle>;
}

/** Video player with the detected skeleton drawn on top, in sync with playback, and the swing phases below. */
export default function SwingPlayer({ videoUrl, keypointsUrl, phases = [], ref }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [speed, setSpeed] = useState(1);
  const [keypoints, setKeypoints] = useState<KeypointsFile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const [hideUncertain, setHideUncertain] = useState(false);
  const [frameIndex, setFrameIndex] = useState(0);
  const [aspectMismatch, setAspectMismatch] = useState(false);

  useEffect(() => {
    if (!keypointsUrl) return;
    loadKeypoints(keypointsUrl)
      .then(setKeypoints)
      .catch((e: Error) => setLoadError(e.message));
  }, [keypointsUrl]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = speed;
  }, [speed]);

  // Latest settings for the draw loop, which outlives individual renders.
  const settings = useRef({ showSkeleton, hideUncertain, keypoints });
  settings.current = { showSkeleton, hideUncertain, keypoints };

  const draw = useCallback((time: number) => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const { showSkeleton, hideUncertain, keypoints } = settings.current;

    const dpr = window.devicePixelRatio || 1;
    const cw = video.clientWidth;
    const ch = video.clientHeight;
    if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
      canvas.width = Math.round(cw * dpr);
      canvas.height = Math.round(ch * dpr);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);

    if (!keypoints || keypoints.frames.length === 0) return;
    const index = frameIndexAt(keypoints.frames, time);
    setFrameIndex(index);
    if (!showSkeleton || !video.videoWidth) return;

    // The video is letterboxed inside its element (object-fit: contain).
    const scale = Math.min(cw / video.videoWidth, ch / video.videoHeight);
    const w = video.videoWidth * scale;
    const h = video.videoHeight * scale;
    drawSkeleton(ctx, keypoints.frames[index], (cw - w) / 2, (ch - h) / 2, w, h, hideUncertain);
  }, []);

  // Redraw on every presented video frame; fall back to animation frames.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let stopped = false;
    let handle = 0;

    if ("requestVideoFrameCallback" in video) {
      const onFrame = (_now: number, meta: VideoFrameCallbackMetadata) => {
        if (stopped) return;
        draw(meta.mediaTime);
        handle = video.requestVideoFrameCallback(onFrame);
      };
      handle = video.requestVideoFrameCallback(onFrame);
    } else {
      const onTick = () => {
        if (stopped) return;
        draw((video as HTMLVideoElement).currentTime);
        handle = requestAnimationFrame(onTick);
      };
      handle = requestAnimationFrame(onTick);
    }

    // Frame callbacks do not fire for every seek or resize, so redraw then too.
    const redraw = () => draw(video.currentTime);
    video.addEventListener("seeked", redraw);
    video.addEventListener("loadeddata", redraw);
    const resize = new ResizeObserver(redraw);
    resize.observe(video);

    return () => {
      stopped = true;
      if ("cancelVideoFrameCallback" in video) video.cancelVideoFrameCallback(handle);
      else cancelAnimationFrame(handle);
      video.removeEventListener("seeked", redraw);
      video.removeEventListener("loadeddata", redraw);
      resize.disconnect();
    };
  }, [draw]);

  // Toggling a setting while paused needs an explicit redraw.
  useEffect(() => {
    if (videoRef.current) draw(videoRef.current.currentTime);
  }, [showSkeleton, hideUncertain, keypoints, draw]);

  // Keypoints are in the orientation the analysis saw; warn if the browser shows another.
  const checkAspect = useCallback(() => {
    const video = videoRef.current;
    const kp = settings.current.keypoints;
    if (!video?.videoWidth || !kp) return;
    const ratio = video.videoWidth / video.videoHeight / (kp.video.width / kp.video.height);
    setAspectMismatch(Math.abs(ratio - 1) > 0.02);
  }, []);
  useEffect(checkAspect, [keypoints, checkAspect]);

  function onLoadedMetadata() {
    if (videoRef.current) videoRef.current.playbackRate = speed;
    checkAspect();
  }

  const seekToFrame = useCallback(
    (index: number) => {
      const video = videoRef.current;
      const frames = keypoints?.frames;
      if (!video || !frames?.length) return;
      video.pause();
      video.currentTime = frameMidpoint(frames, Math.min(Math.max(index, 0), frames.length - 1));
    },
    [keypoints],
  );
  useImperativeHandle(ref, () => ({ seekToFrame }), [seekToFrame]);

  const frames = keypoints?.frames ?? [];
  const current: KeypointFrame | undefined = frames[frameIndex];
  const clipEnd = frames.length ? frames[frames.length - 1].t : 0;
  const currentPhase = [...phases].reverse().find((p) => p.frame_index <= frameIndex);

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-2xl bg-black shadow-[var(--shadow-card)]">
        <video
          ref={videoRef}
          src={videoUrl}
          controls
          playsInline
          className="mx-auto block max-h-[70vh] w-full"
          onLoadedMetadata={onLoadedMetadata}
        />
        <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full" />
      </div>

      <div className="card space-y-4 p-4">
        {phases.length > 0 && clipEnd > 0 && (
          <div aria-label="Swing phases">
            <div className="relative mx-2 h-1.5 rounded-full bg-subtle">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-brand/30"
                style={{ width: `${Math.min(100, ((current?.t ?? 0) / clipEnd) * 100)}%` }}
              />
              {phases.map((p) => (
                <span
                  key={p.name}
                  className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface ${
                    currentPhase?.name === p.name ? "bg-brand" : "bg-mute/50"
                  }`}
                  style={{ left: `${(p.timestamp_s / clipEnd) * 100}%` }}
                />
              ))}
            </div>
            <div className="mt-3 grid grid-cols-5 gap-1.5">
              {phases.map((p) => {
                const active = currentPhase?.name === p.name;
                return (
                  <button
                    key={p.name}
                    onClick={() => seekToFrame(p.frame_index)}
                    title={PHASE_HINT[p.name]}
                    aria-pressed={active}
                    className={`rounded-lg px-1 py-1.5 text-center text-xs transition-colors sm:text-sm ${
                      active ? "bg-brand text-white" : "bg-subtle text-mute hover:text-ink"
                    }`}
                  >
                    <span className="block font-semibold">{PHASE_LABEL[p.name]}</span>
                    <span className={`tnum block text-[0.7rem] ${active ? "text-white/75" : "text-mute"}`}>
                      {p.timestamp_s.toFixed(2)} s{p.confidence < 0.5 ? " ?" : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          {keypoints ? (
            <div className="flex items-center gap-1">
              <button onClick={() => seekToFrame(frameIndex - 1)} className="btn-quiet rounded-lg" aria-label="Previous frame">
                <ChevronLeft className="h-5 w-5" />
              </button>
              <span className="tnum min-w-[6.5rem] text-center text-xs text-mute">
                Frame {current ? current.i + 1 : "–"} / {frames.length}
              </span>
              <button onClick={() => seekToFrame(frameIndex + 1)} className="btn-quiet rounded-lg" aria-label="Next frame">
                <ChevronRight className="h-5 w-5" />
              </button>
            </div>
          ) : (
            <span />
          )}
          <div className="seg" role="group" aria-label="Playback speed">
            {SPEEDS.map((s) => (
              <button key={s} onClick={() => setSpeed(s)} aria-pressed={speed === s} className="tnum">
                {s}×
              </button>
            ))}
          </div>
        </div>

        {keypoints && (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-3 text-sm">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={showSkeleton}
                onChange={(e) => setShowSkeleton(e.target.checked)}
                className="h-4 w-4 accent-[var(--color-brand)]"
              />
              Skeleton
            </label>
            <label className={`flex cursor-pointer items-center gap-2 ${showSkeleton ? "" : "opacity-50"}`}>
              <input
                type="checkbox"
                checked={hideUncertain}
                disabled={!showSkeleton}
                onChange={(e) => setHideUncertain(e.target.checked)}
                className="h-4 w-4 accent-[var(--color-brand)]"
              />
              Hide hidden joints
            </label>
            <span className="flex items-center gap-3 text-xs text-mute">
              <Legend color={COLORS.left} label="Left side" />
              <Legend color={COLORS.right} label="Right side" />
            </span>
          </div>
        )}

        {current && !current.lm && <p className="text-sm text-bad">No person was detected in this frame.</p>}
        {current && current.lm && current.n > 1 && (
          <p className="text-sm text-warn">{current.n} people detected here; showing the one chosen as the golfer.</p>
        )}
        {aspectMismatch && (
          <p role="alert" className="text-sm text-bad">
            The browser shows this video in a different orientation than the one analysed, so the skeleton may not
            line up.
          </p>
        )}
        {loadError && (
          <p role="alert" className="text-sm text-bad">
            Skeleton unavailable: {loadError}
          </p>
        )}
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-1 w-4 rounded" style={{ background: color }} />
      {label}
    </span>
  );
}

/** A time inside frame `index`, away from its edges, so seeking lands on that frame. */
function frameMidpoint(frames: KeypointFrame[], index: number): number {
  const t = frames[index].t;
  const next = frames[index + 1]?.t;
  const prev = frames[index - 1]?.t;
  const span = next !== undefined ? next - t : prev !== undefined ? t - prev : 0.033;
  return t + span / 2;
}

function drawSkeleton(
  ctx: CanvasRenderingContext2D,
  frame: KeypointFrame,
  ox: number,
  oy: number,
  w: number,
  h: number,
  hideUncertain: boolean,
) {
  const lm = frame.lm;
  if (!lm) return;
  const px = (i: number) => ox + lm[i][0] * w;
  const py = (i: number) => oy + lm[i][1] * h;
  const confident = (i: number) => lm[i][3] >= CONFIDENT_VISIBILITY;
  const lineWidth = Math.max(2, Math.min(w, h) / 160);

  ctx.lineCap = "round";
  for (const [a, b, side] of SEGMENTS) {
    const sure = confident(a) && confident(b);
    if (!sure && hideUncertain) continue;
    ctx.globalAlpha = sure ? 1 : 0.4;
    ctx.setLineDash(sure ? [] : [lineWidth * 1.5, lineWidth * 2]);
    // Dark underlay keeps the lines readable on bright backgrounds.
    ctx.strokeStyle = "rgba(0,0,0,0.55)";
    ctx.lineWidth = lineWidth + 2;
    ctx.beginPath();
    ctx.moveTo(px(a), py(a));
    ctx.lineTo(px(b), py(b));
    ctx.stroke();
    ctx.strokeStyle = COLORS[side];
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }
  ctx.setLineDash([]);

  const radius = lineWidth * 1.4;
  for (const [i, side] of JOINTS) {
    const sure = confident(i);
    if (!sure && hideUncertain) continue;
    ctx.globalAlpha = sure ? 1 : 0.4;
    ctx.beginPath();
    ctx.arc(px(i), py(i), radius, 0, Math.PI * 2);
    ctx.fillStyle = sure ? COLORS[side] : "rgba(0,0,0,0.4)";
    ctx.fill();
    ctx.strokeStyle = sure ? "rgba(0,0,0,0.6)" : COLORS[side];
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}
