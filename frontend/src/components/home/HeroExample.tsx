import { useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Info } from "lucide-react";
import example from "@/assets/example-swing.json";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import type { PhaseName } from "@/api";
import { cn } from "@/lib/utils";
import { PHASE_LABEL } from "@/swingLabels";
import { PoseFigure, boundsOf, useSwingClock, type Pose } from "./PoseFigure";

/*
  The homepage hero: an example analysis acted out by the soft white figure (no real person on
  screen). The motion is one analysed swing's smoothed joint positions (assets/example-swing.json),
  the same for every visitor, so it shows what an analysis looks like before you have one.
*/

type ExampleFrame = Pose & { club: [number, number, number, number] };
type Club = ExampleFrame["club"];

const rawFrames = example.frames as unknown as ExampleFrame[];
const phases = example.phases as Record<PhaseName, number>;

/** Gaussian average of `xs` where frame i uses its own width `sigma[i]` (in frames). */
function gaussVarying(xs: number[], sigma: number[]): number[] {
  return xs.map((_, i) => {
    const r = Math.ceil(sigma[i] * 2.5);
    let sum = 0;
    let weight = 0;
    for (let j = Math.max(0, i - r); j <= Math.min(xs.length - 1, i + r); j++) {
      const w = Math.exp(-((j - i) ** 2) / (2 * sigma[i] ** 2));
      sum += xs[j] * w;
      weight += w;
    }
    return sum / weight;
  });
}

/**
 * The club as detected jitters a few pixels from frame to frame. In the slow backswing that jitter is
 * large next to the motion, so the path wiggles; in the fast downswing it hardly shows, and heavy
 * smoothing there would cut the corner at the bottom of the arc. So: a 3-frame median against
 * single-frame outliers, then a Gaussian that is wide in the backswing (sigma 3 frames) and narrow from
 * the top on (sigma 1), blended over a few frames around the top.
 */
function smoothClub(raw: Club[]): Club[] {
  const median3 = (xs: number[]) => xs.map((x, i) => (i === 0 || i === xs.length - 1 ? x : [xs[i - 1], x, xs[i + 1]].sort((a, b) => a - b)[1]));
  const top = phases.top;
  const sigma = raw.map((_, i) => 1 + 2 * Math.min(1, Math.max(0, (top - i) / 6)));
  const columns = [0, 1, 2, 3].map((c) => gaussVarying(median3(raw.map((club) => club[c])), sigma));
  return raw.map((_, i) => columns.map((col) => col[i]) as Club);
}

const smoothed = smoothClub(rawFrames.map((f) => f.club));
const frames: ExampleFrame[] = rawFrames.map((f, i) => ({ ...f, club: smoothed[i] }));

/*
  Tempo. The source clip is phone slow motion that changes speed partway (it plays the follow-through
  at normal speed), so its own timing is not used. Instead each phase gets a tour player's timing:
  the familiar 3 : 1 (about 0.8 s back, 0.27 s down, typical of tour players) and a 0.4 s
  follow-through, all played SLOW_MOTION times slower so it is easy to follow. Frames are spread
  evenly within each phase, which keeps that phase's own acceleration.
*/
const SLOW_MOTION = 3;
const DOWNSWING_S = 0.27;
const FOLLOW_THROUGH_S = 0.4;
/**
 * Where the source clip goes back to normal speed: 3 frames after impact (the hands' movement per frame
 * triples there). Those 3 frames are still slow motion, so they keep the downswing's pace; splitting
 * the follow-through evenly instead made the swing stall just after impact.
 */
const SPEED_SWITCH = phases.impact + 3;
const downswingFrame = DOWNSWING_S / (phases.impact - phases.top);
/** Real seconds per stretch of frames: [from, to, seconds]. The set-up parts are timed for viewing. */
const PHASE_SECONDS: [number, number, number][] = [
  [0, phases.address, 0.1],
  [phases.address, phases.takeaway, 0.23],
  [phases.takeaway, phases.top, 0.8],
  [phases.top, phases.impact, DOWNSWING_S],
  [phases.impact, SPEED_SWITCH, (SPEED_SWITCH - phases.impact) * downswingFrame],
  [SPEED_SWITCH, phases.finish, FOLLOW_THROUGH_S - (SPEED_SWITCH - phases.impact) * downswingFrame],
  [phases.finish, frames.length - 1, 0.2],
];
/** When each frame is shown, in ms from the start. */
const SHOW_AT: number[] = (() => {
  const at = new Array<number>(frames.length).fill(0);
  let t = 0;
  for (const [from, to, seconds] of PHASE_SECONDS) {
    const ms = seconds * SLOW_MOTION * 1000;
    for (let i = from; i <= to; i++) at[i] = t + (to > from ? ((i - from) / (to - from)) * ms : 0);
    t += ms;
  }
  return at;
})();
const TOTAL = SHOW_AT[SHOW_AT.length - 1];

/** Fractional source frame at playback progress p (0..1). */
function framePosition(p: number): number {
  const t = p * TOTAL;
  let i = 0;
  while (i < SHOW_AT.length - 2 && SHOW_AT[i + 1] <= t) i++;
  return Math.min(frames.length - 1, i + (t - SHOW_AT[i]) / (SHOW_AT[i + 1] - SHOW_AT[i]));
}

const lerp = (a: number, b: number, f: number) => a + (b - a) * f;

/** The figure between two frames: every joint and the club, linearly. */
function frameAt(u: number): ExampleFrame {
  const i = Math.floor(u);
  const f = u - i;
  const a = frames[i];
  const b = frames[Math.min(frames.length - 1, i + 1)];
  if (f === 0 || a === b) return a;
  const out = {} as Record<string, number[]>;
  for (const key of Object.keys(a) as (keyof ExampleFrame)[]) {
    out[key] = (a[key] as number[]).map((v, c) => lerp(v, (b[key] as number[])[c], f));
  }
  return out as unknown as ExampleFrame;
}

const ORDER: PhaseName[] = ["address", "takeaway", "top", "impact", "finish"];
/** Club-head positions kept lit behind the club, in frames. */
const TRAIL = 16;

const STEPS = [
  ["Film", "Record a swing from behind (down-the-line) or from the front (face-on), at 60 fps or more."],
  ["Upload", "The video stays on this computer. Your body and the club are tracked in every frame."],
  ["Improve", "Get plain-language feedback with drills, and watch your numbers change swing by swing."],
];

type Note = { at: PhaseName[]; title: string; value: string; anchor: (p: ExampleFrame) => [number, number] };

/** What the coach points out, phase by phase, next to the part of the body it is about. */
const NOTES: Note[] = [
  {
    at: ["address", "takeaway"],
    title: "Spine angle",
    value: `${example.values.spine}° · Good`,
    anchor: (p) => [(p.ls[0] + p.lh[0]) / 2, (p.ls[1] + p.lh[1]) / 2],
  },
  { at: ["top"], title: "Knee flex", value: `${example.values.knee}° · Good`, anchor: (p) => [p.rk[0], p.rk[1]] },
  { at: ["impact"], title: "Swing plane", value: "On plane", anchor: (p) => [p.club[0], p.club[1]] },
  { at: ["finish"], title: "Rated good", value: `${example.values.ratedGood}%`, anchor: (p) => [p.nose[0], p.nose[1]] },
];

/** One frame around the whole swing (club included), so the figure stays put while it moves. */
const BOX = boundsOf(frames, frames.flatMap((f) => [[f.club[2], f.club[3]] as [number, number]]), 0.06);

const currentPhase = (u: number) => [...ORDER].reverse().find((name) => phases[name] <= u) ?? "address";

/**
 * The figure, its notes and the phase timeline: the only part that changes every frame, kept apart
 * so the headline and buttons beside it do not re-render with it.
 */
function ExampleStage() {
  const ref = useRef<HTMLDivElement>(null);
  // Plays the swing once when the page opens, then holds the finish.
  const progress = useSwingClock(TOTAL, ref, { once: true });
  const u = framePosition(progress);
  const index = Math.floor(u);
  const box = BOX;
  const frame = frameAt(u);
  const phase = currentPhase(u);
  const note = NOTES.find((n) => n.at.includes(phase));
  // The lit trail: club-head positions of the last TRAIL frames, ending exactly at the club head now.
  const trail = [
    ...frames.slice(Math.max(0, index - TRAIL), index + 1).map((f) => [f.club[2], f.club[3]] as [number, number]),
    [frame.club[2], frame.club[3]] as [number, number],
  ];
  const pct = (x: number, y: number) => [((x - box!.x) / box!.w) * 100, ((y - box!.y) / box!.h) * 100];
  const [nx, ny] = note ? pct(...note.anchor(frame)) : [0, 0];

  return (
          <div ref={ref} className="relative flex h-[min(78svh,760px)] min-h-[440px] flex-col">
            <div className="relative min-h-0 flex-1">
              {box && <PoseFigure pose={frame} box={box} club={frame.club} trail={trail} tone="dark" label="Example: a figure swinging a golf club, with the coach's notes" />}
              {note && (
                <div key={note.title} className="pointer-events-none absolute inset-0 animate-in fade-in-0 duration-300">
                  <span
                    className="absolute size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-[#7cc35f] shadow-[0_0_0_6px_rgb(124_195_95/0.25)]"
                    style={{ left: `${nx}%`, top: `${ny}%` }}
                  />
                  <div
                    className="absolute rounded-2xl bg-white/95 px-4 py-2.5 text-[#111] shadow-[0_8px_30px_rgb(0_0_0/0.25)] backdrop-blur"
                    style={{ left: `${Math.min(nx, 68)}%`, top: `${ny}%`, transform: "translate(22px, -50%)" }}
                  >
                    <p className="text-[13px] font-medium text-[#6b6b68]">{note.title}</p>
                    <p className="text-[20px] leading-tight font-semibold tracking-[-0.02em] whitespace-nowrap">{note.value}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Phase timeline: where in the swing the figure is. */}
            <div className="mt-4">
              <div className="relative h-1 rounded-full bg-white/15">
                <div className="absolute inset-y-0 left-0 rounded-full bg-white" style={{ width: `${progress * 100}%` }} />
                {ORDER.map((name) => (
                  <span
                    key={name}
                    className={cn(
                      "absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#1a3d29] transition-colors",
                      phases[name] <= u ? "bg-white" : "bg-white/35",
                    )}
                    style={{ left: `${(SHOW_AT[phases[name]] / TOTAL) * 100}%` }}
                  />
                ))}
              </div>
              {/* Evenly spaced: impact and finish are only a few frames apart on the bar. */}
              <div className="mt-3 grid grid-cols-5 text-[13px] font-medium">
                {ORDER.map((name, i) => (
                  <span
                    key={name}
                    className={cn(
                      "transition-colors",
                      i === 0 ? "text-left" : i === ORDER.length - 1 ? "text-right" : "text-center",
                      name === phase ? "text-white" : "text-white/45",
                    )}
                  >
                    {PHASE_LABEL[name]}
                  </span>
                ))}
              </div>
            </div>
          </div>
  );
}

export function HeroExample() {
  return (
    <section className="relative min-h-svh overflow-hidden bg-[radial-gradient(90%_75%_at_72%_42%,#2a5a3c_0%,#1a3d29_50%,#0f2618_100%)] text-white">
      <div className="mx-auto grid min-h-svh max-w-[90rem] items-center gap-6 px-6 pt-24 pb-10 font-aspekta sm:px-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="max-w-xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-1.5 text-[14px] font-medium text-[#cfeac2] backdrop-blur">
            <span className="size-2 rounded-full bg-[#7cc35f]" />
            Example analysis
          </p>
          <h1 className="mt-6 text-[clamp(2.6rem,5.2vw,4.75rem)] leading-[1.02] font-medium tracking-[-0.03em]">
            See your swing the way a coach does.
          </h1>
          <p className="mt-6 max-w-md text-[18px] leading-relaxed text-white/70">
            Upload a phone video: your body and club are tracked in every frame, measured, and explained in plain
            language, with drills.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button asChild variant="white" size="lg" className="group h-13 px-8 text-[16px]">
              <Link to="/analyse">
                Analyse a swing
                <ArrowRight className="group-hover:translate-x-0.5" />
              </Link>
            </Button>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="glass" size="lg" className="h-13 gap-3 pr-2.5 pl-6 text-[16px]">
                  How Swing Coach works
                  <span className="grid size-8 place-items-center rounded-full border-2 border-white">
                    <Info className="size-4" strokeWidth={2.5} />
                  </span>
                </Button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="start" sideOffset={12} className="w-[min(92vw,26rem)] rounded-3xl p-6">
                <ol className="space-y-4">
                  {STEPS.map(([title, text], i) => (
                    <li key={title} className="flex gap-4">
                      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#eef6ea] text-sm font-semibold text-[#3f7a3a]">
                        {i + 1}
                      </span>
                      <span>
                        <span className="block font-semibold">{title}</span>
                        <span className="text-sm text-muted-foreground">{text}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </PopoverContent>
            </Popover>
          </div>
        </div>

        <ExampleStage />
      </div>
    </section>
  );
}
