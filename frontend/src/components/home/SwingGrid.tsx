import { Link } from "react-router-dom";
import { ArrowUpRight, Trash2, Upload } from "lucide-react";
import { angleLabel, api, type Analysis } from "@/api";
import ConfirmDelete from "@/components/ConfirmDelete";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useVideoFrames } from "@/lib/videoFrames";
import { TONE_CLASS, verdict } from "@/swingLabels";

const STATUS: Record<Analysis["status"], string> = {
  queued: "Waiting to start",
  processing: "Analysing…",
  completed: "Ready",
  failed: "Could not be analysed",
};

/** Impact is the most telling frame; fall back to the top, then the start of the clip. */
function stillTime(a: Analysis) {
  const phases = a.swing?.phases ?? [];
  return (phases.find((p) => p.name === "impact") ?? phases.find((p) => p.name === "top"))?.timestamp_s ?? 0.5;
}

function SwingCard({ a, onDelete }: { a: Analysis; onDelete: (a: Analysis) => void }) {
  const done = a.status === "completed";
  const frames = useVideoFrames(done ? api.videoUrl(a.id) : null, done ? [stillTime(a) + 0.01] : [], 640);
  const still = frames?.[0] ?? null;
  const v = verdict(a.swing?.feedback);
  const href = done ? `/analyses/${a.id}` : `/analyses/${a.id}/processing`;
  const date = new Date(a.createdAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  const title = `${angleLabel(a.video.cameraAngle)} swing`;

  return (
    <article className="group relative overflow-hidden rounded-[28px] bg-[#efefed] transition-[translate] duration-300 ease-out will-change-transform hover:-translate-y-1">
      <div className="relative aspect-[4/5] overflow-hidden bg-[#e3e3e0]">
        {still ? (
          <img src={still} alt="" className="absolute inset-0 size-full object-cover transition-[scale] duration-500 ease-out will-change-transform group-hover:scale-[1.04]" />
        ) : (
          <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_0%,#cfe3c4_0%,#e3e3e0_70%)]" />
        )}
        <span className="absolute bottom-4 left-4 grid size-11 place-items-center rounded-full bg-white/90 text-[#111] backdrop-blur transition-colors duration-200 group-hover:bg-[#111] group-hover:text-white">
          <ArrowUpRight className="size-5" />
        </span>
        <div className="absolute top-4 right-4 z-10 opacity-0 transition-opacity duration-200 group-hover:opacity-100 focus-within:opacity-100">
          <ConfirmDelete
            description={`"${title}" from ${date} and its analysis will be deleted from this computer. This cannot be undone.`}
            onConfirm={() => onDelete(a)}
            trigger={
              <button
                type="button"
                aria-label={`Delete ${title} from ${date}`}
                className="grid size-9 place-items-center rounded-full bg-white/90 text-[#111] backdrop-blur transition-colors duration-200 hover:bg-[#d2483a] hover:text-white"
              >
                <Trash2 className="size-4" />
              </button>
            }
          />
        </div>
      </div>
      <div className="p-6">
        <h3 className="text-[20px] leading-tight font-medium tracking-[-0.01em]">
          <Link to={href} className="after:absolute after:inset-0">
            {title}
          </Link>
        </h3>
        <p className="mt-1 text-[14px] text-[#6b6b68]">
          {date} · {a.video.handedness === "right" ? "Right" : "Left"}-handed{a.video.club ? ` · ${a.video.club}` : ""}
        </p>
        <p className="mt-4">
          {done && v ? (
            <span className={cn("inline-block rounded-full px-3 py-1 text-[13px] font-medium", TONE_CLASS[v.tone])}>{v.title}</span>
          ) : (
            <span className="inline-block rounded-full bg-white px-3 py-1 text-[13px] font-medium text-[#6b6b68]">{STATUS[a.status]}</span>
          )}
        </p>
      </div>
    </article>
  );
}

export function SwingGrid({ analyses, onDelete }: { analyses: Analysis[] | null; onDelete: (a: Analysis) => void }) {
  return (
    <section id="swings" className="scroll-mt-20 bg-white py-24 text-[#111]">
      <div className="mx-auto max-w-[90rem] px-6 font-aspekta sm:px-10">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="text-lg font-medium text-[#6b6b68]">{analyses ? `${analyses.length} ${analyses.length === 1 ? "swing" : "swings"}` : "Your swings"}</p>
            <h2 className="mt-2 text-[clamp(2rem,4.2vw,3.5rem)] leading-[1.05] font-medium tracking-tight">Your swings.</h2>
          </div>
          <Button asChild size="lg">
            <Link to="/analyse">
              <Upload />
              Analyse a swing
            </Link>
          </Button>
        </div>

        {analyses === null && (
          <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="aspect-[4/6] animate-pulse rounded-[28px] bg-[#efefed]" />
            ))}
          </div>
        )}

        {analyses && analyses.length === 0 && (
          <div className="mt-14 rounded-[28px] bg-[#efefed] p-10 text-[20px] leading-snug text-[#6b6b68] sm:p-14">
            No swings yet. Film one from behind or from the front and upload it: it appears here with its feedback.
          </div>
        )}

        {analyses && analyses.length > 0 && (
          <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {analyses.slice(0, 16).map((a) => (
              <SwingCard key={a.id} a={a} onDelete={onDelete} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
