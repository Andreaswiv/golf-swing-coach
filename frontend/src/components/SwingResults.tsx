import type { MomentName, Rating, SwingAnalysis, SwingMeasurement } from "../api";
import { MOMENT_LABEL, RATING, confidenceLabel, formatMeasurement, measurementInfo } from "../swingLabels";
import { ChevronRight } from "./icons";

const GROUP_ORDER: (MomentName | "timing")[] = ["timing", "address", "takeaway", "top", "downswing", "impact", "finish"];

/** Known groups in swing order, then any the frontend does not know yet (never hide a measurement). */
function orderedGroups(groups: Map<string, SwingMeasurement[]>): string[] {
  const known: string[] = GROUP_ORDER;
  return [...known.filter((g) => groups.has(g)), ...[...groups.keys()].filter((g) => !known.includes(g))];
}

interface Props {
  swing: SwingAnalysis;
  onSeek: (frameIndex: number) => void;
}

/** The measurements behind the feedback, folded away by default when feedback exists. */
export default function SwingResults({ swing, onSeek }: Props) {
  const groups = new Map<string, SwingMeasurement[]>();
  for (const m of swing.measurements) {
    const key = m.unit === "s" || m.name === "tempo_ratio" ? "timing" : (m.phase ?? "timing");
    groups.set(key, [...(groups.get(key) ?? []), m]);
  }
  const counts = (["good", "watch", "bad"] as Rating[])
    .map((r) => ({ r, n: swing.measurements.filter((m) => m.rating === r).length }))
    .filter((c) => c.n > 0);

  return (
    <details className="card group" open={swing.feedback ? undefined : true}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5 [&::-webkit-details-marker]:hidden">
        <span>
          <h2 id="swing-h" className="text-base">
            Measurements
          </h2>
          <span className="text-sm text-mute">The numbers behind the feedback</span>
          {counts.length > 0 && (
            <span className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-mute">
              {counts.map(({ r, n }) => (
                <span key={r} className="flex items-center gap-1.5">
                  <span className={`h-2 w-2 rounded-full ${RATING[r].dot}`} />
                  {n} {RATING[r].text.toLowerCase()}
                </span>
              ))}
            </span>
          )}
        </span>
        <ChevronRight className="h-5 w-5 text-mute transition-transform group-open:rotate-90" />
      </summary>

      <div className="space-y-5 border-t border-line p-5">
        <p className="text-sm text-mute">
          Measured in 2D from the camera's point of view, so these are not true 3D joint angles. Distances are a
          share of your torso length, so camera distance does not matter.
          {swing.mirrored_for_left_handed && " Left-handed swings are mirrored, so “lead” means your right side."}{" "}
          Select a row to see that moment.
          {counts.length > 0 &&
            " Green is within what good swings show, yellow is slightly off, red is clearly off. Grey values are context only, or too uncertain to judge."}
        </p>

        {swing.notes.length > 0 && (
          <ul className="space-y-2 rounded-xl bg-subtle p-4 text-sm">
            {swing.notes.map((n) => (
              <li key={n.code}>{n.message}</li>
            ))}
          </ul>
        )}

        {swing.status !== "ok" && (
          <p className="text-sm text-bad">
            {swing.status === "no_swing_found"
              ? "No measurements: a full swing was not found in this clip."
              : "No measurements: the analysis failed (see the note above)."}
          </p>
        )}

        {orderedGroups(groups).map((g) => (
          <div key={g}>
            <h3 className="text-sm font-semibold text-mute">{g === "timing" ? "Timing" : (MOMENT_LABEL[g as MomentName] ?? g)}</h3>
            <ul className="mt-2 divide-y divide-line overflow-hidden rounded-xl border border-line">
              {groups.get(g)!.map((m) => {
                const info = measurementInfo(m.name);
                const conf = confidenceLabel(m.confidence);
                const rating = m.rating ? RATING[m.rating] : null;
                // Older results have no rating: keep the old look (grey only when uncertain).
                const valueCls = rating ? rating.value : m.rating === undefined && m.confidence >= 0.5 ? "" : "text-mute";
                return (
                  <li key={m.name}>
                    <button
                      onClick={() => onSeek(m.frame_index)}
                      className="grid w-full grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-canvas"
                    >
                      <span className="font-medium">{info.label}</span>
                      <span className={`tnum text-right text-lg font-semibold leading-tight ${valueCls}`}>
                        {formatMeasurement(m)}
                      </span>
                      <span className="text-sm text-mute">
                        {info.meaning}
                        {m.typical && (
                          <span className="mt-0.5 block text-ink/80">Good swings: {m.typical}</span>
                        )}
                      </span>
                      <span className="flex flex-col items-end gap-1 text-right text-xs">
                        {rating && (
                          <span className={`rounded-full px-2 py-0.5 font-semibold ${rating.pill}`}>{rating.text}</span>
                        )}
                        <span className="text-mute">
                          <span className={m.confidence < 0.5 ? conf.cls : ""}>{conf.text}</span> ·{" "}
                          {m.type === "measured" ? "Measured" : "Estimated"}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}
