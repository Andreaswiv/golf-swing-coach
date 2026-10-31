import { useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Info } from "lucide-react";
import example from "@/assets/example-swing.json";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import type { PhaseName } from "@/api";
import { cn } from "@/lib/utils";
import { PHASE_LABEL } from "@/swingLabels";
import { PoseFigure, boundsOf, useSwingPlayback, type Pose } from "./PoseFigure";

/*
  The homepage hero: an example analysis acted out by the soft white figure (no real person on
  screen). The motion is one analysed swing's smoothed joint positions (assets/example-swing.json),
  the same for every visitor, so it shows what an analysis looks like before you have one.
*/

type ExampleFrame = Pose & { club: [number, number, number, number] };
const frames = example.frames as unknown as ExampleFrame[];
const phases = example.phases as Record<PhaseName, number>;
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

const currentPhase = (index: number) => [...ORDER].reverse().find((name) => phases[name] <= index) ?? "address";

/**
 * The figure, its notes and the phase timeline: the only part that changes every frame, kept apart
 * so the headline and buttons beside it do not re-render with it.
 */
function ExampleStage() {
  const ref = useRef<HTMLDivElement>(null);
  // Plays the swing once when the page opens, then holds the finish.
  const index = useSwingPlayback(frames.length, 5200, ref, { once: true });
  const box = BOX;
  const frame = frames[index];
  const phase = currentPhase(index);
  const note = NOTES.find((n) => n.at.includes(phase));
  const trail = frames.slice(Math.max(0, index - TRAIL), index + 1).map((f) => [f.club[2], f.club[3]] as [number, number]);
  const pct = (x: number, y: number) => [((x - box!.x) / box!.w) * 100, ((y - box!.y) / box!.h) * 100];
  const [nx, ny] = note ? pct(...note.anchor(frame)) : [0, 0];
  const progress = index / (frames.length - 1);

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
                      phases[name] <= index ? "bg-white" : "bg-white/35",
                    )}
                    style={{ left: `${(phases[name] / (frames.length - 1)) * 100}%` }}
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
