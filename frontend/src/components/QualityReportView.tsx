import type { QualityReport } from "../api";

const OVERALL: Record<QualityReport["overall"], { text: string; cls: string }> = {
  good: { text: "No problems found in the checks that ran", cls: "text-good" },
  warning: { text: "Usable, with caveats", cls: "text-warn" },
  poor: { text: "Results will be unreliable", cls: "text-bad" },
};

const SEVERITY_DOT: Record<string, string> = {
  info: "bg-left",
  warning: "bg-warn",
  high: "bg-bad",
};

const NOT_RUN_LABEL: Record<string, string> = {
  camera_motion: "Camera movement",
  camera_angle_match: "Selected camera angle matches the footage",
};

function pct(v: unknown): string {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "–";
}

export default function QualityReportView({ quality }: { quality: QualityReport }) {
  const overall = OVERALL[quality.overall];
  const s = quality.stats;
  return (
    <section aria-labelledby="quality-heading">
      <h2 id="quality-heading" className="text-lg">
        Video quality
      </h2>
      <p className={`mt-1 text-sm ${overall.cls}`}>{overall.text}</p>

      {quality.warnings.length > 0 ? (
        <ul className="mt-4 divide-y divide-line border-y border-line">
          {quality.warnings.map((w, i) => (
            <li key={`${w.code}-${i}`} className="flex gap-3 py-3 text-sm">
              <span
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[w.severity] ?? "bg-mute"}`}
                aria-hidden
              />
              <span>
                <span className="sr-only">{w.severity}: </span>
                {w.message}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 border-y border-line py-3 text-sm text-mute">No warnings.</p>
      )}

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-mute">Person detected in</dt>
          <dd className="tnum">{pct(s.pose_detection_rate)} of frames</dd>
        </div>
        <div>
          <dt className="text-mute">Frame rate</dt>
          <dd className="tnum">{typeof s.fps === "number" ? `${s.fps} fps` : "–"}</dd>
        </div>
        <div>
          <dt className="text-mute">Timing confidence</dt>
          <dd className="tnum">{pct(s.temporal_resolution_factor)}</dd>
        </div>
      </dl>

      {quality.checks_not_run.length > 0 && (
        <p className="mt-4 text-sm text-mute">
          Not checked yet:{" "}
          {quality.checks_not_run.map((c) => NOT_RUN_LABEL[c] ?? c).join("; ")}. A clean report
          does not cover these.
        </p>
      )}
    </section>
  );
}
