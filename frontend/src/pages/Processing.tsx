import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertCircle, Check, Clock } from "lucide-react";
import { api, type Analysis } from "@/api";
import QualityReportView from "@/components/QualityReportView";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// The stages the computer-vision service reports, in order.
const STAGES = [
  "Queued",
  "Reading video",
  "Detecting pose",
  "Tracking the club",
  "Assessing video quality",
  "Saving keypoints",
  "Analysing swing",
  "Completed",
];

const STAGE_LABEL: Record<string, string> = {
  Queued: "Waiting to start",
  "Reading video": "Reading the video",
  "Detecting pose": "Finding your joints in every frame",
  "Tracking the club": "Finding the club around your swing",
  "Assessing video quality": "Checking video quality",
  "Saving keypoints": "Saving results",
  "Analysing swing": "Analysing your swing",
  Completed: "Done",
};

// Stage names that mean the same step as one in STAGES.
const STAGE_ALIAS: Record<string, string> = {
  "Detecting pose and club": "Detecting pose",
};

function stageIndex(a: Analysis): number {
  if (a.status === "completed") return STAGES.length - 1;
  const i = STAGES.indexOf(STAGE_ALIAS[a.stage] ?? a.stage);
  return i >= 0 ? i : a.status === "queued" ? 0 : 1; // "Starting" etc. count as reading the video
}

const POLL_MS = 1000;

function elapsedSince(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Re-render every second while `active`, for the elapsed-time clock. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export default function Processing() {
  const { id = "" } = useParams();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = analysis?.status === "queued" || analysis?.status === "processing";
  const now = useNow(running);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const a = await api.get(id);
        if (cancelled) return;
        setAnalysis(a);
        setError(null);
        if (a.status === "queued" || a.status === "processing") timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
        timer = setTimeout(tick, POLL_MS * 3); // keep trying; the API may be restarting
      }
    }
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (!analysis) {
    return error ? (
      <Alert variant="destructive" className="mx-auto max-w-xl">
        <AlertCircle />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    ) : (
      <Skeleton className="mx-auto h-[420px] max-w-xl rounded-xl" />
    );
  }

  const current = stageIndex(analysis);
  const failed = analysis.status === "failed";
  const done = analysis.status === "completed";

  return (
    <div className="mx-auto max-w-xl space-y-6">
        <Card className="gap-0 p-6 sm:p-8">
          <h1 className="text-2xl">
            {failed ? "The analysis failed" : done ? "Your analysis is ready" : "Analysing your swing"}
          </h1>
          <p className="mt-1 truncate text-sm text-muted-foreground">{analysis.video.originalFileName}</p>

          {!failed && (
            <div aria-live="polite" className="mt-6">
              <Progress value={analysis.progress} aria-label="Processing progress" className="h-2" />
              <p className="tnum mt-2 flex items-center justify-between text-sm text-muted-foreground">
                <span>{analysis.progress}%</span>
                {running && (
                  <span className="flex items-center gap-1.5" aria-label={`Running for ${elapsedSince(analysis.createdAt, now)}`}>
                    <Clock className="size-4" />
                    {elapsedSince(analysis.createdAt, now)}
                  </span>
                )}
              </p>

              <ol className="mt-6 space-y-3">
                {STAGES.slice(1).map((s, j) => {
                  const i = j + 1;
                  const complete = i < current || done;
                  const active = i === current && !done;
                  return (
                    <li
                      key={s}
                      className={cn("flex items-center gap-3 text-sm", complete || active ? "text-foreground" : "text-muted-foreground")}
                    >
                      <span
                        aria-hidden
                        className={cn(
                          "flex size-6 items-center justify-center rounded-full",
                          complete ? "bg-primary text-primary-foreground" : active ? "bg-brand-soft ring-2 ring-leaf-4" : "bg-muted",
                        )}
                      >
                        {complete && <Check className="size-3.5" />}
                      </span>
                      {STAGE_LABEL[s]}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {failed && (
            <Alert variant="destructive" className="mt-5">
              <AlertCircle />
              <AlertTitle>{analysis.error ?? "The video could not be processed."}</AlertTitle>
              <AlertDescription>
                <p>
                  Check that the file plays on your computer, then{" "}
                  <Link to="/analyse" className="link">
                    try again
                  </Link>
                  . Re-exporting as H.264 MP4 fixes most video format problems.
                </p>
              </AlertDescription>
            </Alert>
          )}

          {error && !failed && (
            <p className="mt-4 text-sm text-destructive" role="status">
              Connection problem: {error}. Retrying…
            </p>
          )}

          {done && (
            <Button asChild size="lg" className="mt-6 w-full">
              <Link to={`/analyses/${analysis.id}`}>See your feedback</Link>
            </Button>
          )}
        </Card>

        {done && analysis.quality && (
          <Card className="animate-in fade-in-0 p-6 duration-500">
            <QualityReportView quality={analysis.quality} />
          </Card>
        )}
    </div>
  );
}
