import type { AnalysisStatus } from "../api";

const STYLES: Record<AnalysisStatus, { label: string; cls: string }> = {
  queued: { label: "Queued", cls: "bg-subtle text-mute" },
  processing: { label: "Analysing", cls: "bg-brand-soft text-brand" },
  completed: { label: "Ready", cls: "bg-good-soft text-good" },
  failed: { label: "Failed", cls: "bg-bad-soft text-bad" },
};

export default function StatusPill({ status }: { status: AnalysisStatus }) {
  const s = STYLES[status];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}
