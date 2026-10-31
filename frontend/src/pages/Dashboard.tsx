import { useCallback, useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { api, type Analysis } from "@/api";
import { HeroExample } from "@/components/home/HeroExample";
import { MetricsBento } from "@/components/home/MetricsBento";
import { SwingGrid } from "@/components/home/SwingGrid";
import { swingPoints } from "@/swingStats";

/** The homepage: the latest swing on video, its numbers, then every swing. */
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
    try {
      await api.remove(a.id);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const points = analyses ? swingPoints(analyses) : [];
  const latest = points.at(-1)?.analysis ?? null;
  return (
    <div className="bg-white">
      <HeroExample />
      {error && (
        <p role="alert" className="mx-auto max-w-[90rem] px-6 pt-8 text-sm text-destructive sm:px-10">
          {error}
        </p>
      )}
      <MetricsBento latest={latest} points={points} />
      <SwingGrid analyses={analyses} onDelete={remove} />
      <footer className="border-t border-[#ececea] bg-white">
        <div className="mx-auto flex max-w-[90rem] flex-wrap items-center justify-between gap-4 px-6 py-10 font-aspekta text-[14px] text-[#6b6b68] sm:px-10">
          <span className="font-medium text-[#111]">Swing Coach</span>
          <span className="flex items-center gap-2">
            <Lock className="size-4" />
            Videos stay on this computer
          </span>
          <span>Feedback from 2D video: a guide, not a diagnosis.</span>
        </div>
      </footer>
    </div>
  );
}
