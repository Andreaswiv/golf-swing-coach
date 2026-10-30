import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Analysis } from "../api";
import StatusPill from "../components/StatusPill";
import { ArrowRight, LockIcon, TrashIcon, UploadIcon } from "../components/icons";
import { TONE_CLASS, swingTitle, verdict } from "../swingLabels";

/** The finding title flagged most often (improve or watch) across completed swings. */
function mostCommonFocus(analyses: Analysis[]): { title: string; count: number } | null {
  const counts = new Map<string, number>();
  for (const a of analyses) {
    for (const f of a.swing?.feedback?.findings ?? []) {
      if (f.kind !== "strength") counts.set(f.title, (counts.get(f.title) ?? 0) + 1);
    }
  }
  let best: { title: string; count: number } | null = null;
  for (const [title, count] of counts) if (!best || count > best.count) best = { title, count };
  return best;
}

export default function Dashboard() {
  const [analyses, setAnalyses] = useState<Analysis[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .list()
      .then((a) => {
        setAnalyses(a);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  async function remove(a: Analysis) {
    if (!window.confirm(`Delete this swing ("${a.video.originalFileName}") and its analysis? This cannot be undone.`))
      return;
    try {
      await api.remove(a.id);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const completed = analyses?.filter((a) => a.status === "completed") ?? [];
  const latest = completed[0];
  const latestVerdict = verdict(latest?.swing?.feedback);
  const focus = analyses ? mostCommonFocus(completed) : null;

  return (
    <div className="space-y-10">
      <section className="relative overflow-hidden rounded-3xl bg-brand px-6 py-10 text-white sm:px-10 sm:py-12">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-white/10"
        />
        <div aria-hidden className="pointer-events-none absolute -bottom-32 right-24 h-64 w-64 rounded-full bg-white/5" />
        <div className="relative max-w-xl">
          <h1 className="text-3xl sm:text-4xl">Clear feedback on your golf swing</h1>
          <p className="mt-3 text-white/80">
            Film a swing, upload it, and get plain-language feedback with drills, based on how your body actually
            moves.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Link to="/analyse" className="btn bg-white text-brand hover:bg-brand-soft">
              <UploadIcon className="h-4 w-4" />
              Analyse a swing
            </Link>
            <span className="flex items-center gap-1.5 text-sm text-white/75">
              <LockIcon className="h-4 w-4" />
              Videos stay on this computer
            </span>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3" aria-label="Overview">
        <div className="card p-5">
          <p className="text-sm text-mute">Swings analysed</p>
          <p className="tnum mt-1 font-display text-4xl font-semibold">{analyses ? completed.length : "–"}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-mute">Latest swing</p>
          {latestVerdict ? (
            <p className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${TONE_CLASS[latestVerdict.tone]}`}>
              {latestVerdict.title}
            </p>
          ) : (
            <p className="mt-2 text-sm text-mute">No results yet</p>
          )}
        </div>
        <div className="card p-5">
          <p className="text-sm text-mute">Flagged most often</p>
          <p className="mt-2 font-medium">{focus ? focus.title : "Nothing flagged yet"}</p>
          {focus && (
            <p className="text-sm text-mute">
              in {focus.count} of {completed.length} {completed.length === 1 ? "swing" : "swings"}
            </p>
          )}
        </div>
      </section>

      <section aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="text-xl">
          My swings
        </h2>
        {error && (
          <p role="alert" className="mt-3 text-sm text-bad">
            {error}
          </p>
        )}
        {analyses && analyses.length === 0 && !error && (
          <div className="card mt-4 flex flex-col items-center px-6 py-12 text-center">
            <p className="font-medium">No swings yet</p>
            <p className="mt-1 max-w-sm text-sm text-mute">Your swings and their feedback will show up here.</p>
            <Link to="/analyse" className="btn btn-primary mt-5">
              Analyse your first swing
            </Link>
          </div>
        )}
        {analyses && analyses.length > 0 && (
          <ul className="mt-4 grid gap-4 md:grid-cols-2">
            {analyses.slice(0, 20).map((a) => {
              const { title, date } = swingTitle(a);
              const v = verdict(a.swing?.feedback);
              const href = a.status === "completed" ? `/analyses/${a.id}` : `/analyses/${a.id}/processing`;
              return (
                <li key={a.id} className="card group relative flex flex-col p-5 transition-shadow hover:shadow-lg">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link to={href} className="font-semibold after:absolute after:inset-0 after:rounded-2xl">
                        {title}
                      </Link>
                      <p className="text-sm text-mute">
                        {date} · {a.video.handedness === "right" ? "Right" : "Left"}-handed
                        {a.video.club ? ` · ${a.video.club}` : ""}
                      </p>
                    </div>
                    <StatusPill status={a.status} />
                  </div>
                  {a.swing?.feedback && (
                    <p className="mt-3 line-clamp-2 text-sm text-mute">{a.swing.feedback.summary}</p>
                  )}
                  <div className="mt-4 flex items-center justify-between gap-3">
                    {v ? (
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${TONE_CLASS[v.tone]}`}>
                        {v.title}
                      </span>
                    ) : (
                      <span className="truncate text-xs text-mute">{a.video.originalFileName}</span>
                    )}
                    <span className="flex items-center gap-1">
                      <button
                        onClick={() => remove(a)}
                        className="btn-quiet relative z-10 rounded-lg"
                        aria-label={`Delete ${title} from ${date}`}
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                      <ArrowRight className="h-4 w-4 text-mute transition-transform group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
