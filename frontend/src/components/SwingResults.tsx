import type { PhaseName, SwingAnalysis, SwingMeasurement } from "../api";
import { PHASE_LABEL, confidenceLabel, formatMeasurement, measurementInfo } from "../swingLabels";
import { ChevronRight } from "./icons";

const GROUP_ORDER: (PhaseName | "timing")[] = ["timing", "address", "top", "impact"];

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

  return (
    <details className="card group" open={swing.feedback ? undefined : true}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5 [&::-webkit-details-marker]:hidden">
        <span>
          <h2 id="swing-h" className="text-base">
            Measurements
          </h2>
          <span className="text-sm text-mute">The numbers behind the feedback</span>
        </span>
        <ChevronRight className="h-5 w-5 text-mute transition-transform group-open:rotate-90" />
      </summary>

      <div className="space-y-5 border-t border-line p-5">
        <p className="text-sm text-mute">
          Measured in 2D from the camera's point of view, so these are not true 3D joint angles. Distances are a
          share of your torso length, so camera distance does not matter.
          {swing.mirrored_for_left_handed && " Left-handed swings are mirrored, so “lead” means your right side."}{" "}
          Select a row to see that moment.
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

        {GROUP_ORDER.filter((g) => groups.has(g)).map((g) => (
          <div key={g}>
            <h3 className="text-sm font-semibold text-mute">{g === "timing" ? "Timing" : PHASE_LABEL[g as PhaseName]}</h3>
            <ul className="mt-2 divide-y divide-line overflow-hidden rounded-xl border border-line">
              {groups.get(g)!.map((m) => {
                const info = measurementInfo(m.name);
                const conf = confidenceLabel(m.confidence);
                return (
                  <li key={m.name}>
                    <button
                      onClick={() => onSeek(m.frame_index)}
                      className="grid w-full grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 px-4 py-3 text-left transition-colors hover:bg-canvas"
                    >
                      <span className="font-medium">{info.label}</span>
                      <span className={`tnum text-right font-semibold ${m.confidence < 0.5 ? "text-mute" : ""}`}>
                        {formatMeasurement(m)}
                      </span>
                      <span className="text-sm text-mute">{info.meaning}</span>
                      <span className="text-right text-xs">
                        <span className={conf.cls}>{conf.text}</span>
                        <span className="text-mute"> · {m.type === "measured" ? "Measured" : "Estimated"}</span>
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
