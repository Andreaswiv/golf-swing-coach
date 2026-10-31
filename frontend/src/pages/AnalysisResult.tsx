import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ChevronDown, ChevronLeft, Download, RefreshCw, Trash2 } from "lucide-react";
import { api, formatDuration, type Analysis } from "@/api";
import ClubTrackingView from "@/components/ClubTrackingView";
import ConfirmDelete from "@/components/ConfirmDelete";
import QualityReportView from "@/components/QualityReportView";
import SwingFeedbackView from "@/components/SwingFeedbackView";
import SwingPlayer, { type SwingPlayerHandle } from "@/components/SwingPlayer";
import SwingResults from "@/components/SwingResults";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { swingTitle, verdict } from "@/swingLabels";

/** A card that folds open: title and one-line description, content below a divider. */
function FoldCard({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Collapsible asChild>
      <Card className="group gap-0 py-0">
        <CollapsibleTrigger className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-xl p-6 text-left">
          <span>
            <span className="block font-semibold">{title}</span>
            <span className="text-sm text-muted-foreground">{description}</span>
          </span>
          <ChevronDown className="size-5 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="border-t p-6">{children}</CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

/** The dark-green band at the top, shared by the page and its loading state. */
function Band({ children }: { children: ReactNode }) {
  return (
    <section className="bg-[radial-gradient(90%_120%_at_75%_0%,#2a5a3c_0%,#1a3d29_55%,#0f2618_100%)] text-white">
      <div className="mx-auto max-w-[90rem] px-6 pt-28 pb-12 sm:px-10">{children}</div>
    </section>
  );
}

/** Placeholder in the page's shape while it loads. */
function PageSkeleton() {
  return (
    <>
      <Band>
        <div className="space-y-3">
          <div className="h-4 w-24 animate-pulse rounded-full bg-white/15" />
          <div className="h-12 w-80 animate-pulse rounded-full bg-white/15" />
          <div className="flex gap-3 pt-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-16 w-36 animate-pulse rounded-2xl bg-white/10" />
            ))}
          </div>
        </div>
      </Band>
      <div className="mx-auto grid max-w-[90rem] gap-6 px-6 py-12 sm:px-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Skeleton className="h-[560px] rounded-[24px]" />
        <div className="space-y-4">
          <Skeleton className="h-[160px] rounded-[24px]" />
          <Skeleton className="h-[190px] rounded-[24px]" />
          <Skeleton className="h-[170px] rounded-[24px]" />
        </div>
      </div>
    </>
  );
}

/** A number in the header band, on glass. */
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-32 rounded-2xl border border-white/15 bg-white/10 px-5 py-3.5 backdrop-blur-md">
      <p className="text-[13px] font-medium text-white/65">{label}</p>
      <p className="mt-1 text-[26px] leading-none font-semibold tracking-[-0.02em] tabular-nums">{value}</p>
    </div>
  );
}

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
      <>
        <Band>
          <h1 className="text-3xl">Swing not available</h1>
        </Band>
        <div className="mx-auto max-w-[90rem] px-6 py-12 sm:px-10">
          <Alert variant="destructive">
            <AlertCircle />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </div>
      </>
    );
  }
  if (!analysis) return <PageSkeleton />;
  if (analysis.status !== "completed") {
    return (
      <Band>
        <h1 className="text-3xl">This analysis is not finished</h1>
        <Button asChild variant="white" className="mt-6">
          <Link to={`/analyses/${analysis.id}/processing`}>View progress</Link>
        </Button>
      </Band>
    );
  }

  const v = analysis.video;
  const { title, date } = swingTitle(analysis);
  const seek = (f: number) => player.current?.seekToFrame(f);
  const portrait = (v.height ?? 0) > (v.width ?? 0);
  const swing = analysis.swing;
  const rated = swing?.measurements.filter((m) => m.rating) ?? [];
  const good = rated.filter((m) => m.rating === "good").length;
  const tempo = swing?.measurements.find((m) => m.name === "tempo_ratio");
  const findings = swing?.feedback?.findings ?? [];
  const verdictText = verdict(swing?.feedback);

  return (
    <div className="animate-in fade-in-0 duration-500">
      <Band>
        <div className="flex flex-wrap items-end justify-between gap-8">
          <div className="min-w-0">
            <Link
              to="/"
              className="inline-flex items-center gap-1 text-[15px] text-white/70 transition-colors duration-200 hover:text-white"
            >
              <ChevronLeft className="size-4" />
              My swings
            </Link>
            <p className="mt-6 text-[15px] font-medium text-white/65">
              {date} · {v.handedness === "right" ? "Right" : "Left"}-handed{v.club ? ` · ${v.club}` : ""}
            </p>
            <h1 className="mt-2 text-[clamp(2.2rem,4.5vw,3.75rem)] leading-[1.02] tracking-[-0.03em]">{title}</h1>
            {verdictText && (
              <p className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-1.5 text-[14px] font-medium text-[#cfeac2] backdrop-blur-md">
                <span className="size-2 rounded-full bg-[#7cc35f]" />
                {verdictText.title}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            {swing && (
              <Button variant="glass" onClick={reanalyze} disabled={reanalyzing}>
                <RefreshCw className={reanalyzing ? "animate-spin" : undefined} />
                {reanalyzing ? "Analysing…" : "Re-analyse"}
              </Button>
            )}
            <ConfirmDelete
              description="This video and its analysis will be deleted from this computer. This cannot be undone."
              onConfirm={remove}
              trigger={
                <Button variant="glass" className="hover:border-[#ff8f80]/50 hover:bg-[#c4372b]/40">
                  <Trash2 />
                  Delete
                </Button>
              }
            />
          </div>
        </div>
        {swing?.status === "ok" && (
          <div className="mt-10 flex flex-wrap gap-3">
            <Stat label="Rated good" value={rated.length ? `${Math.round((good / rated.length) * 100)}%` : "–"} />
            <Stat label="Tempo" value={tempo ? `${tempo.value.toFixed(1)} : 1` : "–"} />
            <Stat label="Strengths" value={String(findings.filter((f) => f.kind === "strength").length)} />
            <Stat label="To work on" value={String(findings.filter((f) => f.kind !== "strength").length)} />
          </div>
        )}
      </Band>

      <div className="mx-auto max-w-[90rem] space-y-6 px-6 py-12 sm:px-10">
      {reanalyzeError && (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertDescription>{reanalyzeError}</AlertDescription>
        </Alert>
      )}

      <div
        className={`grid items-start gap-6 ${
          portrait ? "lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]" : "lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]"
        }`}
      >
        <div className="lg:sticky lg:top-24">
          <SwingPlayer
            ref={player}
            videoUrl={api.videoUrl(analysis.id)}
            keypointsUrl={analysis.keypoints ? api.keypointsUrl(analysis.id) : null}
            phases={analysis.swing?.phases}
            plane={analysis.swing?.club?.plane}
            clubTrack={analysis.swing?.club?.track}
            rejectedLandmarks={analysis.swing?.rejected_landmarks}
          />
        </div>

        <div className="space-y-4">
          {analysis.swing?.feedback && <SwingFeedbackView feedback={analysis.swing.feedback} onSeek={seek} />}

          {(!analysis.swing || (analysis.swing.status === "ok" && !analysis.swing.feedback)) && (
            <Card className="gap-4 p-6">
              <div>
                <h2 className="text-lg">Get your feedback</h2>
                <p className="mt-1 text-muted-foreground">
                  This swing was analysed before feedback existed. It takes a second and uses the joint positions
                  already found.
                </p>
              </div>
              <Button onClick={reanalyze} disabled={reanalyzing} className="w-fit">
                {reanalyzing ? "Analysing…" : "Get feedback"}
              </Button>
            </Card>
          )}

          {analysis.swing && analysis.swing.status !== "ok" && (
            <Card className="gap-1 p-6">
              <h2 className="text-lg">
                {analysis.swing.status === "no_swing_found" ? "No full swing found" : "The analysis failed"}
              </h2>
              <p className="text-muted-foreground">
                {analysis.swing.notes[0]?.message ?? "Try a clip with the whole swing, from setup to finish."}
              </p>
            </Card>
          )}

          {analysis.swing && analysis.swing.status === "ok" && <ClubTrackingView swing={analysis.swing} />}

          {analysis.swing && analysis.swing.status === "ok" && <SwingResults swing={analysis.swing} onSeek={seek} />}

          {analysis.quality && (
            <FoldCard title="Video quality" description="How well the video could be analysed">
              <QualityReportView quality={analysis.quality} />
            </FoldCard>
          )}

          <FoldCard title="Technical details" description="File, format and analysis versions">
            <dl className="divide-y text-sm">
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
                  analysis.swing?.smoothing ? `Savitzky–Golay, ${analysis.swing.smoothing.window_frames} frames` : "–",
                ],
              ].map(([k, val]) => (
                <div key={k} className="flex justify-between gap-4 py-2">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="tnum truncate text-right" title={val}>
                    {val}
                  </dd>
                </div>
              ))}
            </dl>
            <Button asChild variant="link" className="mt-3 h-auto px-0">
              <a href={api.keypointsUrl(analysis.id)} download={`keypoints-${analysis.id}.json`}>
                <Download />
                Download raw keypoints (JSON)
              </a>
            </Button>
            <p className="mt-2 text-xs text-muted-foreground">
              Video black? Some browsers cannot play HEVC (H.265); re-export the clip as H.264 MP4.
            </p>
          </FoldCard>
        </div>
      </div>
      </div>
    </div>
  );
}
