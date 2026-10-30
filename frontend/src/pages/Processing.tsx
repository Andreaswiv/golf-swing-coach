import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Analysis } from "../api";
import QualityReportView from "../components/QualityReportView";
import { AlertIcon, CheckIcon } from "../components/icons";

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

export default function Processing() {
  const { id = "" } = useParams();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      <p role="alert" className="text-bad">
        {error}
      </p>
    ) : (
      <p className="text-mute">Loading…</p>
    );
  }

  const current = stageIndex(analysis);
  const failed = analysis.status === "failed";
  const done = analysis.status === "completed";

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <section className="card p-6 sm:p-8">
        <h1 className="text-2xl">
          {failed ? "The analysis failed" : done ? "Your analysis is ready" : "Analysing your swing"}
        </h1>
        <p className="mt-1 truncate text-sm text-mute">{analysis.video.originalFileName}</p>

        {!failed && (
          <div aria-live="polite" className="mt-6">
            <div
              className="h-2.5 overflow-hidden rounded-full bg-subtle"
              role="progressbar"
              aria-valuenow={analysis.progress}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Processing progress"
            >
              <div
                className="h-full rounded-full bg-brand transition-[width] duration-500"
                style={{ width: `${analysis.progress}%` }}
              />
            </div>
            <p className="tnum mt-2 text-sm text-mute">{analysis.progress}%</p>

            <ol className="mt-5 space-y-3">
              {STAGES.slice(1).map((s, j) => {
                const i = j + 1;
                const complete = i < current || done;
                const active = i === current && !done;
                return (
                  <li key={s} className={`flex items-center gap-3 text-sm ${complete || active ? "text-ink" : "text-mute"}`}>
                    <span
                      aria-hidden
                      className={`flex h-6 w-6 items-center justify-center rounded-full ${
                        complete ? "bg-brand text-white" : active ? "bg-brand-soft ring-2 ring-brand" : "bg-subtle"
                      }`}
                    >
                      {complete && <CheckIcon className="h-3.5 w-3.5" />}
                    </span>
                    {STAGE_LABEL[s]}
                  </li>
                );
              })}
            </ol>
          </div>
        )}

        {failed && (
          <div role="alert" className="mt-5 rounded-xl bg-bad-soft p-4 text-sm">
            <p className="flex gap-2 font-medium text-bad">
              <AlertIcon className="h-5 w-5 shrink-0" />
              {analysis.error ?? "The video could not be processed."}
            </p>
            <p className="mt-2 text-mute">
              Check that the file plays on your computer, then{" "}
              <Link to="/analyse" className="link">
                try again
              </Link>
              . Re-exporting as H.264 MP4 fixes most video format problems.
            </p>
          </div>
        )}

        {error && !failed && (
          <p className="mt-4 text-sm text-bad" role="status">
            Connection problem: {error}. Retrying…
          </p>
        )}

        {done && (
          <Link to={`/analyses/${analysis.id}`} className="btn btn-primary mt-6 w-full py-3">
            See your feedback
          </Link>
        )}
      </section>

      {done && analysis.quality && (
        <div className="card p-6">
          <QualityReportView quality={analysis.quality} />
        </div>
      )}
    </div>
  );
}
