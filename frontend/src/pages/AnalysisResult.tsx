import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, formatDuration, type Analysis } from "../api";
import { ChevronLeft, DownloadIcon, RefreshIcon, TrashIcon } from "../components/icons";
import QualityReportView from "../components/QualityReportView";
import SwingPlayer, { type SwingPlayerHandle } from "../components/SwingPlayer";
import SwingFeedbackView from "../components/SwingFeedbackView";
import SwingResults from "../components/SwingResults";
import { swingTitle } from "../swingLabels";

export default function AnalysisResult() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeError, setReanalyzeError] = useState<string | null>(null);
  const player = useRef<SwingPlayerHandle>(null);

  useEffect(() => {
    api
      .get(id)
      .then(setAnalysis)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  async function remove() {
    if (!analysis) return;
    if (!window.confirm("Delete this video and its analysis data from this computer? This cannot be undone.")) return;
    try {
      await api.remove(analysis.id);
      navigate("/");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function reanalyze() {
    if (!analysis) return;
    setReanalyzing(true);
    setReanalyzeError(null);
    try {
      setAnalysis(await api.reanalyze(analysis.id));
    } catch (e) {
      setReanalyzeError((e as Error).message);
    } finally {
      setReanalyzing(false);
    }
  }

  if (error) {
    return (
      <p role="alert" className="text-bad">
        {error}
      </p>
    );
  }
  if (!analysis) return <p className="text-mute">Loading…</p>;
  if (analysis.status !== "completed") {
    return (
      <p>
        This analysis is not finished.{" "}
        <Link to={`/analyses/${analysis.id}/processing`} className="link">
          View progress
        </Link>
      </p>
    );
  }

  const v = analysis.video;
  const { title, date } = swingTitle(analysis);
  const seek = (f: number) => player.current?.seekToFrame(f);
  const portrait = (v.height ?? 0) > (v.width ?? 0);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link to="/" className="mb-2 inline-flex items-center gap-1 text-sm text-mute hover:text-ink">
            <ChevronLeft className="h-4 w-4" />
            My swings
          </Link>
          <h1 className="text-3xl">{title}</h1>
          <p className="mt-1 text-mute">
            {date} · {v.handedness === "right" ? "Right" : "Left"}-handed{v.club ? ` · ${v.club}` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          {analysis.swing && (
            <button onClick={reanalyze} disabled={reanalyzing} className="btn btn-secondary px-3 py-2 text-sm">
              <RefreshIcon className={`h-4 w-4 ${reanalyzing ? "animate-spin" : ""}`} />
              {reanalyzing ? "Analysing…" : "Re-analyse"}
            </button>
          )}
          <button onClick={remove} className="btn btn-secondary px-3 py-2 text-sm hover:!border-bad hover:text-bad">
            <TrashIcon className="h-4 w-4" />
            Delete
          </button>
        </div>
      </header>

      {reanalyzeError && (
        <p role="alert" className="rounded-xl bg-bad-soft p-3 text-sm text-bad">
          {reanalyzeError}
        </p>
      )}

      <div
        className={`grid items-start gap-6 ${
          portrait ? "lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]" : "lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]"
        }`}
      >
        <div className="lg:sticky lg:top-20">
          <SwingPlayer
            ref={player}
            videoUrl={api.videoUrl(analysis.id)}
            keypointsUrl={analysis.keypoints ? api.keypointsUrl(analysis.id) : null}
            phases={analysis.swing?.phases}
          />
        </div>

        <div className="space-y-4">
          {analysis.swing?.feedback && <SwingFeedbackView feedback={analysis.swing.feedback} onSeek={seek} />}

          {(!analysis.swing || (analysis.swing.status === "ok" && !analysis.swing.feedback)) && (
            <div className="card p-6">
              <h2 className="text-lg">Get your feedback</h2>
              <p className="mt-1 text-mute">
                This swing was analysed before feedback existed. It takes a second and uses the joint positions
                already found.
              </p>
              <button onClick={reanalyze} disabled={reanalyzing} className="btn btn-primary mt-4">
                {reanalyzing ? "Analysing…" : "Get feedback"}
              </button>
            </div>
          )}

          {analysis.swing && analysis.swing.status !== "ok" && (
            <div className="card p-6">
              <h2 className="text-lg">
                {analysis.swing.status === "no_swing_found" ? "No full swing found" : "The analysis failed"}
              </h2>
              <p className="mt-1 text-mute">
                {analysis.swing.notes[0]?.message ?? "Try a clip with the whole swing, from setup to finish."}
              </p>
            </div>
          )}

          {analysis.swing && analysis.swing.status === "ok" && <SwingResults swing={analysis.swing} onSeek={seek} />}

          {analysis.quality && (
            <details className="card group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5 [&::-webkit-details-marker]:hidden">
                <span>
                  <span className="block font-display font-semibold">Video quality</span>
                  <span className="text-sm text-mute">How well the video could be analysed</span>
                </span>
                <ChevronLeft className="h-5 w-5 rotate-180 text-mute transition-transform group-open:rotate-[270deg]" />
              </summary>
              <div className="border-t border-line p-5">
                <QualityReportView quality={analysis.quality} />
              </div>
            </details>
          )}

          <details className="card group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5 [&::-webkit-details-marker]:hidden">
              <span>
                <span className="block font-display font-semibold">Technical details</span>
                <span className="text-sm text-mute">File, format and analysis versions</span>
              </span>
              <ChevronLeft className="h-5 w-5 rotate-180 text-mute transition-transform group-open:rotate-[270deg]" />
            </summary>
            <div className="border-t border-line p-5">
              <dl className="divide-y divide-line text-sm">
                {[
                  ["File", v.originalFileName],
                  ["Resolution", v.width && v.height ? `${v.width} × ${v.height}` : "–"],
                  ["Frame rate", v.fps ? `${v.fps} fps` : "–"],
                  ["Duration", formatDuration(v.durationSeconds)],
                  ["Frames analysed", analysis.keypoints ? String(analysis.keypoints.frameCount) : "–"],
                  ["Pose model", analysis.poseModel ?? "–"],
                  ["Pipeline version", analysis.pipelineVersion ?? "–"],
                  ["Swing analysis", analysis.swing?.version ?? "–"],
                  [
                    "Smoothing",
                    analysis.swing?.smoothing
                      ? `Savitzky–Golay, ${analysis.swing.smoothing.window_frames} frames`
                      : "–",
                  ],
                ].map(([k, val]) => (
                  <div key={k} className="flex justify-between gap-4 py-2">
                    <dt className="text-mute">{k}</dt>
                    <dd className="tnum truncate text-right" title={val}>
                      {val}
                    </dd>
                  </div>
                ))}
              </dl>
              <a
                href={api.keypointsUrl(analysis.id)}
                download={`keypoints-${analysis.id}.json`}
                className="link mt-4 inline-flex items-center gap-1.5 text-sm"
              >
                <DownloadIcon className="h-4 w-4" />
                Download raw keypoints (JSON)
              </a>
              <p className="mt-3 text-xs text-mute">
                Video black? Some browsers cannot play HEVC (H.265); re-export the clip as H.264 MP4.
              </p>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
