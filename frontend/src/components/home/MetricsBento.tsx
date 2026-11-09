import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check } from "lucide-react";
import type { Analysis, Rating, SwingLimits, SwingMeasurement } from "@/api";
import { reducedMotion, useCountUp } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { RATING, signed } from "@/swingLabels";
import type { SwingPoint } from "@/swingStats";

/*
  The latest swing as a bento of soft cards beside the golfer's own pose. Every number is measured
  from the video; nothing here is a placeholder unless the swing does not have that measurement.
*/

function useGrown() {
  const [grown, setGrown] = useState(reducedMotion);
  useEffect(() => {
    const t = setTimeout(() => setGrown(true), 120);
    return () => clearTimeout(t);
  }, []);
  return grown;
}

function Card({ area, className, children }: { area: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn("relative overflow-hidden rounded-[28px] bg-[#efefed] p-7", className)} style={{ gridArea: area }}>
      {children}
    </div>
  );
}

function Title({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={cn("text-[20px] leading-tight font-medium tracking-[-0.01em]", className)}>{children}</h3>;
}

function Value({ value, format, className }: { value: number | null; format: (v: number) => string; className?: string }) {
  const shown = useCountUp(value ?? 0, 1000);
  return (
    <p className={cn("mt-3 text-[34px] leading-none font-semibold tracking-[-0.02em] tabular-nums", className)}>
      {value === null ? "–" : format(shown)}
    </p>
  );
}

/** Good / Slightly off / Clearly off, as on the analysis page (same limits as the feedback). */
function RatingPill({ rating, text, title }: { rating: Rating | null | undefined; text?: string; title?: string }) {
  if (!rating) return null;
  return (
    <span
      title={title}
      className={cn("absolute top-6 right-6 flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium", RATING[rating].pill)}
    >
      <span className={cn("size-1.5 rounded-full", RATING[rating].dot)} />
      {text ?? RATING[rating].text}
    </span>
  );
}

/** What good swings show, under the number. */
function Typical({ m }: { m: SwingMeasurement | null }) {
  return m?.typical ? <p className="mt-2 text-[14px] text-[#6b6b68]">Good swings: {m.typical}</p> : null;
}

const RATING_STROKE: Record<Rating, string> = { good: "#3f9a3c", watch: "#d9a21b", bad: "#d2483a" };

/* ---- Tempo gauge ------------------------------------------------------------------------------- */

const TEMPO_MAX = 5;

function TempoGauge({ m, good }: { m: SwingMeasurement | null; good?: SwingLimits["tempo_good"] }) {
  const grown = useGrown();
  const tempo = m?.value ?? null;
  const frac = tempo === null ? 0 : Math.min(tempo / TEMPO_MAX, 1);
  const arc = (r: number) => `M${110 - r} 115 A${r} ${r} 0 0 1 ${110 + r} 115`;
  // Point on the dial for a tempo, at radius r (0 on the left, TEMPO_MAX on the right).
  const at = (v: number, r: number) => [110 - r * Math.cos((v / TEMPO_MAX) * Math.PI), 115 - r * Math.sin((v / TEMPO_MAX) * Math.PI)];
  const band = good ? [at(good[0], 107), at(good[1], 107)] : null;
  const target = (3 / TEMPO_MAX) * Math.PI;
  return (
    <Card area="gauge" className="flex flex-col">
      <Title>Tempo</Title>
      <RatingPill rating={m?.rating} />
      <p className="mt-2 text-[14px] text-[#6b6b68]">Good swings: about 3 : 1</p>
      <div className="relative mx-auto mt-auto w-full max-w-[260px]">
        <svg viewBox="0 0 220 130" className="w-full overflow-visible">
          <path d={arc(95)} fill="none" stroke="#fafaf9" strokeWidth="16" strokeLinecap="round" />
          {/* The good range, as a green band just outside the dial. */}
          {band && (
            <path d={`M${band[0][0]} ${band[0][1]} A107 107 0 0 1 ${band[1][0]} ${band[1][1]}`} fill="none" stroke="#3f9a3c" strokeOpacity="0.55" strokeWidth="4" strokeLinecap="round" />
          )}
          <path d={arc(76)} fill="none" stroke="#b9b9b5" strokeWidth="1.2" strokeDasharray="1 4" />
          <path
            d={arc(95)}
            fill="none"
            stroke={m?.rating ? RATING_STROKE[m.rating] : "#9a9a96"}
            strokeWidth="16"
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray={`${grown ? frac : 0} 1`}
            style={{ transition: "stroke-dasharray 1.1s cubic-bezier(0.22, 0.8, 0.24, 1)" }}
          />
          {/* 3 : 1, what most good swings show */}
          <line
            x1={110 - 104 * Math.cos(target)}
            y1={115 - 104 * Math.sin(target)}
            x2={110 - 86 * Math.cos(target)}
            y2={115 - 86 * Math.sin(target)}
            stroke="#111"
            strokeOpacity="0.35"
            strokeWidth="1.5"
          />
        </svg>
        <div className="absolute inset-x-0 bottom-3 text-center">
          <Value value={tempo} format={(v) => v.toFixed(1)} className="mt-0" />
          <p className="mt-1 text-[15px] font-medium">( : 1 )</p>
        </div>
        <div className="mt-1 flex justify-between px-1 text-[17px] text-[#6b6b68]">
          <span>0</span>
          <span>{TEMPO_MAX}</span>
        </div>
      </div>
    </Card>
  );
}

/* ---- Progress curve ------------------------------------------------------------------------------ */

const CW = 300;
const CH = 190;
/** Green to yellow to orange, left to right. */
const ramp = (f: number) => {
  const stops = [
    [108, 192, 74],
    [232, 184, 48],
    [240, 122, 58],
  ];
  const x = Math.min(Math.max(f, 0), 1) * 2;
  const [a, b] = x < 1 ? [stops[0], stops[1]] : [stops[1], stops[2]];
  const t = x < 1 ? x : x - 1;
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(" ")})`;
};

function ProgressCurve({ points }: { points: SwingPoint[] }) {
  const rated = points.filter((p) => p.goodShare !== null).slice(-6);
  const values = rated.map((p) => p.goodShare!);
  const latest = values.at(-1) ?? null;
  const previous = values.at(-2) ?? null;
  const lo = Math.min(...values, 50);
  const hi = Math.max(...values, 100);
  const xs = values.map((_, i) => 12 + (values.length > 1 ? (i / (values.length - 1)) * (CW - 24) : (CW - 24) / 2));
  const ys = values.map((v) => 12 + (1 - (v - lo) / (hi - lo || 1)) * (CH - 50));
  const step = values.length > 1 ? (CW - 24) / (values.length - 1) : 0;
  const path = xs.reduce((d, x, i) => {
    if (i === 0) return `M${x} ${ys[0]}`;
    const mid = x - step / 2;
    return `${d} C${mid} ${ys[i - 1]} ${mid} ${ys[i]} ${x} ${ys[i]}`;
  }, "");

  return (
    <Card area="curve" className="flex flex-col">
      <Title>Progress</Title>
      {latest !== null && previous !== null && (
        <RatingPill
          rating={Math.abs(latest - previous) < 1 ? "watch" : latest > previous ? "good" : "bad"}
          text={Math.abs(latest - previous) < 1 ? "Steady" : latest > previous ? "Improving" : "Dropping"}
        />
      )}
      <Value
        value={latest}
        format={(v) => `${Math.round(v)}%`}
      />
      <p className="mt-2 text-[14px] text-[#6b6b68]">
        {previous !== null && latest !== null ? `${signed(latest - previous)} pts on the swing before` : "Rated good, swing by swing"}
      </p>
      <svg viewBox={`0 0 ${CW} ${CH}`} className="mt-auto w-full overflow-visible">
        <defs>
          <linearGradient id="curve-ramp" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor={ramp(0)} />
            <stop offset="0.5" stopColor={ramp(0.5)} />
            <stop offset="1" stopColor={ramp(1)} />
          </linearGradient>
          <filter id="curve-glow" x="-10%" y="-30%" width="120%" height="160%">
            <feGaussianBlur stdDeviation="7" />
          </filter>
        </defs>
        {xs.map((x, i) => (
          <line key={i} x1={x} x2={x} y1={ys[i] + 10} y2={CH} stroke="#c8c8c4" strokeDasharray="3 4" className="chart-after" />
        ))}
        {values.length > 1 && (
          <>
            <path d={path} fill="none" stroke="url(#curve-ramp)" strokeOpacity="0.35" strokeWidth="14" filter="url(#curve-glow)" className="chart-after" />
            <path d={path} fill="none" stroke="url(#curve-ramp)" strokeWidth="4" strokeLinecap="round" pathLength={1} className="chart-draw" />
          </>
        )}
        {xs.map((x, i) => (
          <circle
            key={i}
            cx={x}
            cy={ys[i]}
            r="7"
            fill="white"
            stroke={ramp(values.length > 1 ? i / (values.length - 1) : 0)}
            strokeWidth="3"
            className="chart-after"
          />
        ))}
        {values.length === 0 && (
          <text x={CW / 2} y={CH / 2} textAnchor="middle" className="fill-[#6b6b68] text-[14px]">
            No rated swings yet
          </text>
        )}
      </svg>
    </Card>
  );
}

/* ---- Strengths (green) ----------------------------------------------------------------------------- */

/** What the latest swing does well. */
function StrengthsCard({ latest }: { latest: Analysis | null }) {
  const findings = latest?.swing?.feedback?.findings ?? [];
  const strengths = findings.filter((f) => f.kind === "strength");
  return (
    <Card area="green" className="flex flex-col bg-[linear-gradient(160deg,#3f7a45_0%,#5d8c4c_45%,#8fbb7c_100%)] text-white">
      <Title>Strengths</Title>
      <Value value={latest?.swing?.feedback ? strengths.length : null} format={(v) => String(Math.round(v))} />
      <ul className="mt-auto space-y-2.5">
        {strengths.slice(0, 3).map((f) => (
          <li key={f.code} className="flex items-start gap-2.5 text-[14px] leading-snug">
            <span className="mt-px grid size-[18px] shrink-0 place-items-center rounded-full bg-white/20">
              <Check className="size-3" strokeWidth={3} />
            </span>
            {f.title}
          </li>
        ))}
        {strengths.length === 0 && (
          <li className="text-[14px] leading-snug text-white/80">
            {latest ? "Strengths show up here as your swing comes together." : "Analyse a swing to see yours."}
          </li>
        )}
      </ul>
    </Card>
  );
}

/* ---- Swing plane (club) ------------------------------------------------------------------------------ */

const RATING_TEXT = { good: "text-[#3f9a3c]", watch: "text-[#c98a12]", bad: "text-[#d2483a]" } as const;

function PlaneCard({
  shaft,
  path,
  verdict,
  rating,
}: {
  shaft: SwingMeasurement | null;
  path: SwingMeasurement | null;
  verdict: string;
  rating: Rating | null;
}) {
  const grown = useGrown();
  // The shaft's direction halfway down, against the plane line at address (vertical here).
  const tilt = shaft ? Math.max(-28, Math.min(28, (shaft.value / 100) * 30)) : 0;
  const rows: [string, string, string][] = [
    ["Swing plane", verdict, rating ? RATING_TEXT[rating] : "text-[#6b6b68]"],
    ["Shaft halfway down", shaft ? `${signed(shaft.value)}%` : "–", shaft?.rating ? RATING_TEXT[shaft.rating] : ""],
    ["Hand path", path ? `${signed(path.value)}%` : "–", path?.rating ? RATING_TEXT[path.rating] : ""],
  ];
  return (
    <Card area="club" className="grid grid-cols-[40%_1fr] items-center gap-2 py-6 pl-0">
      <svg viewBox="0 0 140 300" className="h-full max-h-[300px] w-full overflow-visible" aria-hidden>
        <line x1="96" x2="96" y1="10" y2="290" stroke="#9a9a96" strokeDasharray="5 5" />
        <path
          d={`M96 200 L${96 + 90 * Math.sin((tilt * Math.PI) / 180)} ${200 - 90 * Math.cos((tilt * Math.PI) / 180)} L96 110 Z`}
          fill="#3d6ef5"
          fillOpacity="0.14"
          className="chart-after"
        />
        <line x1="96" y1="200" x2="96" y2="96" stroke="#4caf50" strokeWidth="5" strokeLinecap="round" />
        <path d="M86 104 L96 84 L106 104 Z" fill="#4caf50" />
        <g
          style={{ transform: `rotate(${grown ? tilt : 0}deg)`, transformOrigin: "96px 200px", transition: "transform 1s cubic-bezier(0.22, 0.8, 0.24, 1)" }}
        >
          <line x1="96" y1="200" x2="96" y2="100" stroke="#111" strokeWidth="5" strokeLinecap="round" />
          <path d="M86 108 L96 88 L106 108 Z" fill="#111" />
        </g>
        <path d="M0 196 L70 206" stroke="#111" strokeWidth="5" strokeLinecap="round" />
        <path d="M70 196 Q96 190 104 214 Q92 236 70 226 Z" fill="#2b2b2b" />
        <circle cx="96" cy="200" r="15" fill="white" stroke="#d8d8d4" />
        <circle cx="91" cy="195" r="5" fill="#f2f2f0" />
      </svg>
      <dl className="space-y-5 pr-4">
        {rows.map(([k, v, cls]) => (
          <div key={k}>
            <dt className="text-[17px] leading-tight font-medium">{k}</dt>
            <dd className={cn("mt-1 text-[26px] leading-none font-semibold tracking-[-0.02em]", cls)}>{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

/* ---- Rated good (dotted bar) ---------------------------------------------------------------------------- */

const DOTS = { maskImage: "radial-gradient(circle, #000 1.7px, transparent 2px)", maskSize: "7px 7px" };

/** 80%+ of measurements in the good range is good; under 60% is clearly off. */
const shareRating = (share: number): Rating => (share >= 80 ? "good" : share >= 60 ? "watch" : "bad");

function RatedGoodBar({ share }: { share: number | null }) {
  const grown = useGrown();
  return (
    <Card area="weight" className="flex flex-col justify-center gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <Title className="flex items-center gap-2">
          Rated good
          {share !== null && (
            <span className={cn("rounded-full px-2.5 py-1 text-[12px] font-medium", RATING[shareRating(share)].pill)}>
              {RATING[shareRating(share)].text}
            </span>
          )}
        </Title>
        <p className="text-[34px] leading-none font-semibold tracking-[-0.02em] tabular-nums">
          <Counted value={share} />
          <span className="ml-1 text-[18px] font-medium">%</span>
        </p>
      </div>
      <div className="relative h-11">
        <div className="absolute inset-0 bg-[#c9c9c6]" style={DOTS} />
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-[#bfe5aa] to-[#2f8f3a]"
          style={{ ...DOTS, width: grown ? `${share ?? 0}%` : 0, transition: "width 1.1s cubic-bezier(0.22, 0.8, 0.24, 1)" }}
        />
      </div>
    </Card>
  );
}

function Counted({ value }: { value: number | null }) {
  const shown = useCountUp(value ?? 0, 1000);
  return <>{value === null ? "–" : Math.round(shown)}</>;
}

/* ---- Section --------------------------------------------------------------------------------------------- */

export function MetricsBento({ latest, points }: { latest: Analysis | null; points: SwingPoint[] }) {
  const m = (name: string) => latest?.swing?.measurements.find((x) => x.name === name) ?? null;
  const limits = latest?.swing?.limits;
  const toCm = (pctOfTorso: number) => pctOfTorso * ((limits?.average_torso_cm ?? 0) / 100);
  const spine = m("spine_angle_address");
  const knee = m("trail_knee_flex_address");
  const tempo = m("tempo_ratio");
  const headTop = m("head_rise_top");
  const headImpact = m("head_rise_impact");
  const head = [headTop, headImpact].filter((x) => x !== null).sort((a, b) => Math.abs(b.value) - Math.abs(a.value))[0] ?? null;
  const findings = latest?.swing?.feedback?.findings ?? [];
  const plane = findings.find((f) => ["over_the_top", "inside_out", "on_plane"].includes(f.code));
  const verdict = plane ? { over_the_top: "Over the top", inside_out: "Inside-out", on_plane: "On plane" }[plane.code]! : latest?.swing?.club?.tracked ? "No verdict" : "Not tracked";
  const planeRating: Rating | null = plane ? ({ strength: "good", watch: "watch", improve: "bad" } as const)[plane.kind] : null;
  const latestPoint = points.at(-1) ?? null;
  const date = latest ? new Date(latest.createdAt).toLocaleDateString(undefined, { day: "numeric", month: "long" }) : null;

  return (
    <section id="metrics" className="scroll-mt-20 bg-[#f7f7f5] py-24 text-[#111]">
      <div className="mx-auto max-w-[90rem] px-6 sm:px-10">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="font-aspekta text-lg font-medium text-[#6b6b68]">{date ? `Your latest swing · ${date}` : "Your latest swing"}</p>
            <h2 className="mt-2 font-aspekta text-[clamp(2rem,4.2vw,3.5rem)] leading-[1.05] font-medium tracking-tight">
              Every swing, measured.
            </h2>
          </div>
          {latest && (
            <Button asChild size="lg">
              <Link to={`/analyses/${latest.id}`}>
                Open the full analysis <ArrowUpRight />
              </Link>
            </Button>
          )}
        </div>

        <div className="bento mt-14 grid gap-5 font-aspekta">
            <TempoGauge m={tempo} good={limits?.tempo_good} />
            <Card area="spine">
              <Title>Spine angle</Title>
              <RatingPill rating={spine?.rating} />
              <Value value={spine?.value ?? null} format={(v) => `${signed(v)}°`} />
              <Typical m={spine} />
            </Card>
            <Card area="head">
              <Title>Head movement</Title>
              <RatingPill rating={head?.rating} />
              <Value
                value={head && limits ? toCm(Math.abs(head.value)) : null}
                format={(v) => `${v.toFixed(1)} cm`}
              />
              {head && limits && (
                <p className="mt-2 text-[14px] text-[#6b6b68]">
                  {head.value >= 0 ? "Up" : "Down"} at {head.name.endsWith("top") ? "the top" : "impact"} · good swings: under
                  about {head.value >= 0 ? `${toCm(limits.head_lift).toFixed(0)} cm up` : `${toCm(limits.head_drop).toFixed(0)} cm down`}
                </p>
              )}
            </Card>
            <Card area="knee">
              <Title>Knee flex</Title>
              <RatingPill rating={knee?.rating} />
              <Value value={knee?.value ?? null} format={(v) => `${signed(v)}°`} />
              <Typical m={knee} />
            </Card>
            <ProgressCurve points={points} />
            <StrengthsCard latest={latest} />
            <PlaneCard shaft={m("shaft_points_downswing")} path={m("hand_path_downswing")} verdict={verdict} rating={planeRating} />
            <RatedGoodBar share={latestPoint?.goodShare ?? null} />
        </div>
      </div>
    </section>
  );
}
