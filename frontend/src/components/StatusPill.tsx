import type { AnalysisStatus } from "@/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STYLES: Record<AnalysisStatus, { label: string; cls: string }> = {
  queued: { label: "Queued", cls: "bg-muted text-muted-foreground" },
  processing: { label: "Analysing", cls: "bg-leaf-1 text-leaf-5" },
  completed: { label: "Ready", cls: "bg-good-soft text-good" },
  failed: { label: "Failed", cls: "bg-bad-soft text-bad" },
};

export default function StatusPill({ status }: { status: AnalysisStatus }) {
  const s = STYLES[status];
  return <Badge className={cn("rounded-md", s.cls)}>{s.label}</Badge>;
}
