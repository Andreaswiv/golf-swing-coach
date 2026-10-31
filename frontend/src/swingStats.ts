// Numbers for the dashboard, computed from the analyses the API returns (newest first).

import type { Analysis, Rating } from "./api";

export interface SwingPoint {
  analysis: Analysis;
  date: Date;
  /** Share of rated measurements that are "good", 0..100; null when the swing has no ratings. */
  goodShare: number | null;
  ratings: Record<Rating, number>;
  /** Backswing : downswing; null when the clip changes speed during the swing (tempo is left out). */
  tempo: number | null;
  issues: number;
}

/** Completed swings with an ok analysis, oldest first. */
export function swingPoints(analyses: Analysis[]): SwingPoint[] {
  return analyses
    .filter((a) => a.status === "completed" && a.swing?.status === "ok")
    .map((a) => {
      const ratings: Record<Rating, number> = { good: 0, watch: 0, bad: 0 };
      for (const m of a.swing!.measurements) if (m.rating) ratings[m.rating] += 1;
      const rated = ratings.good + ratings.watch + ratings.bad;
      const tempo = a.swing!.measurements.find((m) => m.name === "tempo_ratio")?.value ?? null;
      return {
        analysis: a,
        date: new Date(a.createdAt),
        goodShare: rated ? (ratings.good / rated) * 100 : null,
        ratings,
        tempo,
        issues: (a.swing!.feedback?.findings ?? []).filter((f) => f.kind !== "strength").length,
      };
    })
    .sort((x, y) => x.date.getTime() - y.date.getTime());
}

/** Swings per day for the last 7 days, oldest first (today last). */
export function swingsPerDay(points: SwingPoint[], now = new Date()): { label: string; count: number; today: boolean }[] {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = day(now);
  return Array.from({ length: 7 }, (_, i) => {
    const start = today - (6 - i) * 86_400_000;
    const d = new Date(start);
    return {
      label: d.toLocaleDateString(undefined, { weekday: "short" }),
      count: points.filter((p) => day(p.date) === start).length,
      today: i === 6,
    };
  });
}

/** Swings in the last 7 days, and in the 7 days before. */
export function weekCounts(points: SwingPoint[], now = new Date()): { thisWeek: number; lastWeek: number } {
  const t = now.getTime();
  const week = 7 * 86_400_000;
  return {
    thisWeek: points.filter((p) => t - p.date.getTime() < week).length,
    lastWeek: points.filter((p) => t - p.date.getTime() >= week && t - p.date.getTime() < 2 * week).length,
  };
}

/** Feedback flagged across all swings (work on / worth checking), most frequent first. */
export function flaggedIssues(points: SwingPoint[]): { title: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const p of points) {
    for (const f of p.analysis.swing?.feedback?.findings ?? []) {
      if (f.kind !== "strength") counts.set(f.title, (counts.get(f.title) ?? 0) + 1);
    }
  }
  return [...counts].map(([title, count]) => ({ title, count })).sort((a, b) => b.count - a.count);
}

/** The latest point with a value for `pick`, and the one before it. */
export function latestTwo<T>(points: SwingPoint[], pick: (p: SwingPoint) => T | null): { latest: T | null; previous: T | null } {
  const values = points.map(pick).filter((v): v is T => v !== null);
  return { latest: values.at(-1) ?? null, previous: values.at(-2) ?? null };
}
