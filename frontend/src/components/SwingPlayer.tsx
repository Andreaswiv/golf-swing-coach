import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from "react";
import { ChevronLeft, ChevronRight, Maximize, Minimize, Pause, Play } from "lucide-react";
import type { ClubSummary, ClubTrackPoint, SwingPhase } from "@/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import {
  CONFIDENT_VISIBILITY,
  JOINTS,
  SEGMENTS,
  frameIndexAt,
  hasClubData,
  loadKeypoints,
  clubLineAt,
  rejectedByFrame,
  type KeypointFrame,
  type KeypointsFile,
  type ShaftLine,
  type Side,
} from "../keypoints";
import { PHASE_HINT, PHASE_LABEL } from "@/swingLabels";

const SPEEDS = [0.1, 0.25, 0.5, 1];

const COLORS: Record<Side, string> = {
  left: "#4aa3df",
  right: "#f0b93a",
  center: "#ffffff",
};
const HIDE_UNCERTAIN_KEY = "golfcoach.hideUncertainJoints";
const CLUB_COLOR = "#5ee38a";
const PLANE_COLOR = "#ff5a7a";

type Plane = NonNullable<ClubSummary["plane"]>;

export interface SwingPlayerHandle {
  /** Pause and show the given frame. */
  seekToFrame(index: number): void;
}

interface Props {
  videoUrl: string;
  keypointsUrl: string | null;
  phases?: SwingPhase[];
  /** Swing plane from the club analysis (down-the-line only). */
  plane?: Plane | null;
  /** The club per frame as the analysis used it (impossible detections removed). */
  clubTrack?: (ClubTrackPoint | null)[];
  /** Joints the analysis dropped as impossible, by landmark name -> frames. Not drawn. */
  rejectedLandmarks?: Record<string, number[]>;
  ref?: Ref<SwingPlayerHandle>;
}

/**
 * Video player with the detected skeleton, club and swing plane drawn on top, in sync with
 * playback, and the swing phases below.
 */
export default function SwingPlayer({
  videoUrl,
  keypointsUrl,
  phases = [],
  plane = null,
  clubTrack,
  rejectedLandmarks,
  ref,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [speed, setSpeed] = useState(1);
  const [keypoints, setKeypoints] = useState<KeypointsFile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showSkeleton, setShowSkeleton] = useState(true);
  // On by default: joints hidden behind the body (the lead arm from down-the-line) are guesses and
  // often drawn in the wrong place. Remembered between visits.
  const [hideUncertain, setHideUncertain] = useState(() => localStorage.getItem(HIDE_UNCERTAIN_KEY) !== "false");
  useEffect(() => localStorage.setItem(HIDE_UNCERTAIN_KEY, String(hideUncertain)), [hideUncertain]);
  const [showClub, setShowClub] = useState(true);
  const [showPlane, setShowPlane] = useState(true);
  const [frameIndex, setFrameIndex] = useState(0);
  // Our own controls (the browser's add a fullscreen button that drops the overlay, and Safari's
  // cannot be hidden). shownSeconds follows the frame on screen; scrubTo is set while dragging.
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [shownSeconds, setShownSeconds] = useState(0);
  const [scrubTo, setScrubTo] = useState<number | null>(null);
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
  const rejected = useMemo(
    () => (keypoints ? rejectedByFrame(keypoints, rejectedLandmarks) : new Map<number, Set<number>>()),
    [keypoints, rejectedLandmarks],
  );
  const settings = useRef({ showSkeleton, hideUncertain, showClub, showPlane, plane, keypoints, clubTrack, rejected });
  settings.current = { showSkeleton, hideUncertain, showClub, showPlane, plane, keypoints, clubTrack, rejected };

  const draw = useCallback((time: number) => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const { showSkeleton, hideUncertain, showClub, showPlane, plane, keypoints, clubTrack, rejected } = settings.current;

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

    if (!keypoints || keypoints.frames.length === 0) return setShownSeconds(time);
    const index = frameIndexAt(keypoints.frames, time);
    setFrameIndex(index);
    setShownSeconds(time);
    if (!video.videoWidth) return;

    // The video is letterboxed inside its element (object-fit: contain).
    const scale = Math.min(cw / video.videoWidth, ch / video.videoHeight);
    const w = video.videoWidth * scale;
    const h = video.videoHeight * scale;
    const ox = (cw - w) / 2;
    const oy = (ch - h) / 2;
    const frame = keypoints.frames[index];

    ctx.save();
    ctx.beginPath();
    ctx.rect(ox, oy, w, h);
    ctx.clip(); // the plane line runs past the frame edge
    if (showPlane && plane) drawPlane(ctx, plane, ox, oy, w, h);
    if (showSkeleton) drawSkeleton(ctx, frame, ox, oy, w, h, hideUncertain, rejected.get(index));
    if (showClub) drawClub(ctx, clubLineAt(frame, index, clubTrack, w / h), ox, oy, w, h);
    ctx.restore();
  }, []);

  // Media time of the frame actually on screen. While scrubbing, currentTime jumps ahead of the
  // picture (the browser may not have decoded the new frame yet, or skips it), so the overlay is
  // only ever drawn for the presented frame.
  const presentedTime = useRef<number | null>(null);
  const shownTime = useCallback(() => presentedTime.current ?? videoRef.current?.currentTime ?? 0, []);

  // Redraw on every presented video frame; fall back to animation frames.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let stopped = false;
    let handle = 0;
    const frameCallbacks = "requestVideoFrameCallback" in video;

    let presentedSinceSeek = true;
    let fallback = 0;
    let lastFrameAt = 0;
    let watchdog = 0;
    // (Re)arm the frame callback. Browsers occasionally drop a pending one (Safari around pause/play,
    // any browser while re-buffering); the chain would then stop and leave the overlay frozen.
    const arm = () => {
      if (stopped || !frameCallbacks) return;
      video.cancelVideoFrameCallback(handle);
      handle = video.requestVideoFrameCallback(onFrame);
    };
    const onFrame = (_now: number, meta: VideoFrameCallbackMetadata) => {
      if (stopped) return;
      // Re-register first: if drawing ever throws, the chain must not break with it.
      handle = video.requestVideoFrameCallback(onFrame);
      lastFrameAt = performance.now();
      presentedSinceSeek = true;
      presentedTime.current = meta.mediaTime;
      draw(meta.mediaTime);
    };
    // While playing: if no frame has been reported for a while, draw from the clock and re-arm.
    const watch = () => {
      if (stopped || video.paused || video.ended) return;
      if (performance.now() - lastFrameAt > 250) {
        presentedTime.current = video.currentTime;
        draw(video.currentTime);
        lastFrameAt = performance.now();
        arm();
      }
      watchdog = requestAnimationFrame(watch);
    };
    const onPlay = () => {
      lastFrameAt = performance.now();
      arm();
      cancelAnimationFrame(watchdog);
      watchdog = requestAnimationFrame(watch);
    };
    if (frameCallbacks) {
      arm();
      video.addEventListener("play", onPlay);
      video.addEventListener("playing", onPlay);
    } else {
      const onTick = () => {
        if (stopped) return;
        draw((video as HTMLVideoElement).currentTime);
        handle = requestAnimationFrame(onTick);
      };
      handle = requestAnimationFrame(onTick);
    }

    // Without frame callbacks, seeks while paused need a redraw. With them, the callback fires
    // when the sought frame is actually shown, so a seek alone must not move the overlay.
    // Some browsers (Safari) do not always report the frame shown after a seek while paused; if
    // nothing is reported shortly after the seek, the sought frame is what is on screen.
    const onSeeking = () => {
      presentedSinceSeek = false;
    };
    const onSeeked = () => {
      const v = video as HTMLVideoElement;
      if (!frameCallbacks) return draw(v.currentTime);
      window.clearTimeout(fallback);
      fallback = window.setTimeout(() => {
        if (stopped || presentedSinceSeek || v.seeking) return;
        presentedTime.current = v.currentTime;
        draw(v.currentTime);
      }, 150);
    };
    const redraw = () => draw(shownTime());
    video.addEventListener("seeking", onSeeking);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("loadeddata", redraw);
    const resize = new ResizeObserver(redraw);
    resize.observe(video);

    return () => {
      stopped = true;
      if (frameCallbacks) video.cancelVideoFrameCallback(handle);
      else cancelAnimationFrame(handle);
      cancelAnimationFrame(watchdog);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("playing", onPlay);
      window.clearTimeout(fallback);
      video.removeEventListener("seeking", onSeeking);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("loadeddata", redraw);
      resize.disconnect();
    };
  }, [draw, shownTime]);

  // Toggling a setting while paused needs an explicit redraw (of the frame on screen).
  useEffect(() => {
    draw(shownTime());
  }, [showSkeleton, hideUncertain, showClub, showPlane, plane, keypoints, clubTrack, rejected, draw, shownTime]);

  // Fullscreen for the video AND its overlay. The browser's own fullscreen button only enlarges
  // the <video>, which leaves the skeleton and club behind, so it is replaced where possible.
  const stageRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const canFullscreen = typeof document !== "undefined" && !!document.fullscreenEnabled;
  // iPhone Safari only lets a bare <video> go fullscreen (without the overlay): better than nothing.
  const videoOnlyFullscreen = (v: HTMLVideoElement | null) =>
    v as (HTMLVideoElement & { webkitEnterFullscreen?: () => void }) | null;
  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = useCallback(() => {
    if (!canFullscreen) return videoOnlyFullscreen(videoRef.current)?.webkitEnterFullscreen?.();
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stageRef.current?.requestFullscreen();
  }, [canFullscreen]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused || video.ended) void video.play();
    else video.pause();
  }, []);

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
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
      setDuration(videoRef.current.duration || 0);
    }
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

  // Step from where the video IS (or is seeking to), not from the last frame the overlay drew: that
  // can lag behind after scrubbing, and stepping from it jumped back to an old frame or the start.
  const stepFrames = useCallback(
    (delta: number) => {
      const video = videoRef.current;
      const frames = keypoints?.frames;
      if (!video || !frames?.length) return;
      seekToFrame(frameIndexAt(frames, video.currentTime) + delta);
    },
    [keypoints, seekToFrame],
  );

  const frames = keypoints?.frames ?? [];
  const current: KeypointFrame | undefined = frames[frameIndex];
  const clipEnd = frames.length ? frames[frames.length - 1].t : 0;
  const currentPhase = [...phases].reverse().find((p) => p.frame_index <= frameIndex);
  const aspect = keypoints ? keypoints.video.width / keypoints.video.height : 1;
  const clubTracked = useMemo(() => (keypoints ? hasClubData(keypoints) : false), [keypoints]);

  return (
    <div className="space-y-3">
      <div
        ref={stageRef}
        tabIndex={0}
        aria-label="Swing video. Space plays or pauses, the arrow keys step one frame."
        onKeyDown={(e) => {
          if (e.key === " " || e.key === "k") {
            e.preventDefault();
            togglePlay();
          } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            stepFrames(e.key === "ArrowLeft" ? -1 : 1);
          }
        }}
        className={cn(
          "flex flex-col overflow-hidden bg-black outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
          fullscreen ? "h-full w-full" : "rounded-[24px]",
        )}
      >
        <div className="relative min-h-0 flex-1">
          <video
            ref={videoRef}
            src={videoUrl}
            playsInline
            disablePictureInPicture
            className={fullscreen ? "h-full w-full" : "mx-auto block max-h-[70vh] w-full"}
            onLoadedMetadata={onLoadedMetadata}
            onDurationChange={(e) => setDuration(e.currentTarget.duration || 0)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onClick={togglePlay}
            onDoubleClick={toggleFullscreen}
          />
          <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full" />
        </div>

        {/* Below the video, not on top of it: it would cover the feet and the ball. */}
        <div className="flex items-center gap-3 px-3 py-2 text-white">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={togglePlay}
            className="text-white hover:bg-white/15 hover:text-white"
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause className="size-5" /> : <Play className="size-5 fill-current" />}
          </Button>
          <span className="tnum shrink-0 font-mono text-[11px] text-white/80">
            {(scrubTo ?? shownSeconds).toFixed(2)} / {duration.toFixed(2)} s
          </span>
          <Slider
            min={0}
            max={duration || 1}
            step={0.001}
            value={[Math.min(scrubTo ?? shownSeconds, duration || 0)]}
            aria-label="Position in the video"
            onValueChange={([t]) => {
              setScrubTo(t);
              if (videoRef.current) videoRef.current.currentTime = t;
            }}
            onValueCommit={() => setScrubTo(null)}
            onBlur={() => setScrubTo(null)}
            className="min-w-0 flex-1 cursor-pointer [&_[data-slot=slider-range]]:bg-white [&_[data-slot=slider-thumb]]:size-3.5 [&_[data-slot=slider-thumb]]:border-white [&_[data-slot=slider-track]]:bg-white/25"
          />
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleFullscreen}
            className="text-white hover:bg-white/15 hover:text-white"
            aria-label={fullscreen ? "Exit full screen" : "Full screen"}
            title={fullscreen ? "Exit full screen" : "Full screen (with the overlay)"}
          >
            {fullscreen ? <Minimize className="size-5" /> : <Maximize className="size-5" />}
          </Button>
        </div>
      </div>

      <Card className="gap-4 p-5">
        {phases.length > 0 && clipEnd > 0 && (
          <div aria-label="Swing phases">
            <div className="relative mx-2 h-1.5 rounded-full bg-muted">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-leaf-2"
                style={{ width: `${Math.min(100, ((current?.t ?? 0) / clipEnd) * 100)}%` }}
              />
              {phases.map((p) => (
                <span
                  key={p.name}
                  className={cn(
                    "absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card",
                    currentPhase?.name === p.name ? "bg-leaf-4" : "bg-muted-foreground/40",
                  )}
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
                    className={cn(
                      "rounded-lg px-1 py-1.5 text-center text-xs transition-colors sm:text-sm",
                      active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <span className="block font-semibold">{PHASE_LABEL[p.name]}</span>
                    <span className={cn("tnum block text-[0.7rem]", active ? "text-primary-foreground/70" : "text-muted-foreground")}>
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
              <Button variant="ghost" size="icon-sm" onClick={() => stepFrames(-1)} aria-label="Previous frame">
                <ChevronLeft className="size-5" />
              </Button>
              <span className="tnum min-w-[6.5rem] text-center text-xs text-muted-foreground">
                Frame {current ? current.i + 1 : "–"} / {frames.length}
              </span>
              <Button variant="ghost" size="icon-sm" onClick={() => stepFrames(1)} aria-label="Next frame">
                <ChevronRight className="size-5" />
              </Button>
            </div>
          ) : (
            <span />
          )}
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            aria-label="Playback speed"
            value={String(speed)}
            onValueChange={(v) => v && setSpeed(Number(v))}
          >
            {SPEEDS.map((s) => (
              <ToggleGroupItem key={s} value={String(s)} className="tnum px-2.5">
                {s}×
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>

        {keypoints && (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t pt-4 text-sm">
            <OverlaySwitch id="ov-skeleton" label="Skeleton" checked={showSkeleton} onChange={setShowSkeleton} />
            <OverlaySwitch
              id="ov-hidden"
              label="Hide hidden joints"
              checked={hideUncertain}
              onChange={setHideUncertain}
              disabled={!showSkeleton}
            />
            {clubTracked && <OverlaySwitch id="ov-club" label="Club" checked={showClub} onChange={setShowClub} />}
            {plane && <OverlaySwitch id="ov-plane" label="Swing plane" checked={showPlane} onChange={setShowPlane} />}
            <span className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <Legend color={COLORS.left} label="Left side" />
              <Legend color={COLORS.right} label="Right side" />
              {clubTracked && <Legend color={CLUB_COLOR} label="Club" />}
              {plane && <Legend color={PLANE_COLOR} label="Plane at address" dashed />}
            </span>
          </div>
        )}
        {current && clubTracked && showClub && !clubLineAt(current, frameIndex, clubTrack, aspect) && (
          <p className="text-sm text-muted-foreground">
            {current.club ? "The club was not found in this frame." : "The club is only tracked around the swing."}
          </p>
        )}

        {current && !current.lm && <p className="text-sm text-destructive">No person was detected in this frame.</p>}
        {current && current.lm && current.n > 1 && (
          <p className="text-sm text-warn">{current.n} people detected here; showing the one chosen as the golfer.</p>
        )}
        {aspectMismatch && (
          <p role="alert" className="text-sm text-destructive">
            The browser shows this video in a different orientation than the one analysed, so the skeleton may not
            line up.
          </p>
        )}
        {loadError && (
          <p role="alert" className="text-sm text-destructive">
            Skeleton unavailable: {loadError}
          </p>
        )}
      </Card>
    </div>
  );
}

function OverlaySwitch({
  id,
  label,
  checked,
  onChange,
  disabled = false,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <span className={cn("flex items-center gap-2", disabled && "opacity-50")}>
      <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} />
      <Label htmlFor={id} className="cursor-pointer font-normal">
        {label}
      </Label>
    </span>
  );
}

function Legend({ color, label, dashed = false }: { color: string; label: string; dashed?: boolean }) {
  const background = dashed ? `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 7px)` : color;
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-1 w-4 rounded" style={{ background }} />
      {label}
    </span>
  );
}

/** Stroke a line with a dark underlay so it stays readable on bright backgrounds. */
function strokeLine(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, color: string, width: number) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = "rgba(0,0,0,0.55)";
  ctx.lineWidth = width + 2;
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}

function drawPlane(ctx: CanvasRenderingContext2D, plane: Plane, ox: number, oy: number, w: number, h: number) {
  const lineWidth = Math.max(2, Math.min(w, h) / 200);
  ctx.setLineDash([lineWidth * 4, lineWidth * 3]);
  ctx.lineCap = "butt";
  strokeLine(
    ctx,
    ox + plane.from[0] * w,
    oy + plane.from[1] * h,
    ox + plane.to[0] * w,
    oy + plane.to[1] * h,
    PLANE_COLOR,
    lineWidth,
  );
  ctx.setLineDash([]);
}

function drawClub(ctx: CanvasRenderingContext2D, line: ShaftLine | null, ox: number, oy: number, w: number, h: number) {
  if (!line) return;
  const lineWidth = Math.max(2, Math.min(w, h) / 160);
  const gx = ox + line.grip[0] * w;
  const gy = oy + line.grip[1] * h;
  const hx = ox + line.head[0] * w;
  const hy = oy + line.head[1] * h;

  ctx.lineCap = "round";
  // A head end inferred from the shaft box is less certain: draw it dashed.
  ctx.setLineDash(line.headFound ? [] : [lineWidth * 2, lineWidth * 2]);
  strokeLine(ctx, gx, gy, hx, hy, CLUB_COLOR, lineWidth);
  ctx.setLineDash([]);

  for (const [x, y, r] of [
    [gx, gy, lineWidth * 1.6],
    [hx, hy, lineWidth * 2.4],
  ]) {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = line.headFound || r < lineWidth * 2 ? CLUB_COLOR : "rgba(0,0,0,0.4)";
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.6)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
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
  dropped?: Set<number>,
) {
  const lm = frame.lm;
  if (!lm) return;
  const px = (i: number) => ox + lm[i][0] * w;
  const py = (i: number) => oy + lm[i][1] * h;
  const confident = (i: number) => lm[i][3] >= CONFIDENT_VISIBILITY;
  // Dropped by the analysis as impossible (a glitch or an over-long limb): never drawn.
  const ok = (i: number) => !dropped?.has(i);
  const lineWidth = Math.max(2, Math.min(w, h) / 160);

  ctx.lineCap = "round";
  for (const [a, b, side] of SEGMENTS) {
    if (!ok(a) || !ok(b)) continue;
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
    if (!ok(i)) continue;
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
