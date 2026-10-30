// Display names and plain-language meanings for the swing analysis.
// Definitions live in cv-service/app/swing/measurements.py; keep the two in sync.

import {
  angleLabel,
  type Analysis,
  type MomentName,
  type PhaseName,
  type Rating,
  type SwingFeedback,
  type SwingFinding,
  type SwingMeasurement,
} from "./api";

export const PHASE_LABEL: Record<PhaseName, string> = {
  address: "Address",
  takeaway: "Takeaway",
  top: "Top",
  impact: "Impact",
  finish: "Finish",
};

export const PHASE_HINT: Record<PhaseName, string> = {
  address: "Set-up before the swing starts",
  takeaway: "Hands start moving back (the clubhead can start a little earlier)",
  top: "Hands start down from their highest point",
  impact: "Hands at their lowest point in the downswing",
  finish: "Hands reach their highest follow-through position",
};

export const MOMENT_LABEL: Record<MomentName, string> = { ...PHASE_LABEL, downswing: "Downswing" };

interface MeasurementInfo {
  label: string;
  meaning: string;
}

const INFO: Record<string, MeasurementInfo> = {
  tempo_ratio: {
    label: "Tempo (backswing : downswing)",
    meaning: "Takeaway-to-top time divided by top-to-impact time.",
  },
  backswing_duration: { label: "Backswing time", meaning: "From takeaway to the top." },
  downswing_duration: { label: "Downswing time", meaning: "From the top to impact." },
  spine_angle_address: {
    label: "Spine angle at address",
    meaning: "Forward bend of the hip-to-shoulder line, measured from vertical.",
  },
  spine_angle_top: { label: "Spine angle at the top", meaning: "Forward bend of the hip-to-shoulder line." },
  spine_angle_impact: { label: "Spine angle at impact", meaning: "Forward bend of the hip-to-shoulder line." },
  spine_angle_change_impact: {
    label: "Spine angle change, address to impact",
    meaning: "Negative = more upright at impact than at address.",
  },
  trail_knee_flex_address: { label: "Trail knee flex at address", meaning: "0° = a straight leg." },
  rear_hip_toward_ball_impact: {
    label: "Backside toward the ball, address to impact",
    meaning: "Rearmost hip joint (the backside line). Positive = moved toward the ball.",
  },
  head_rise_top: { label: "Head height change at the top", meaning: "Positive = higher than at address." },
  head_rise_impact: { label: "Head height change at impact", meaning: "Positive = higher than at address." },
  shoulder_tilt_address: { label: "Shoulder tilt at address", meaning: "Positive = lead shoulder higher." },
  shoulder_tilt_top: { label: "Shoulder tilt at the top", meaning: "Positive = lead shoulder higher." },
  shoulder_tilt_impact: { label: "Shoulder tilt at impact", meaning: "Positive = lead shoulder higher." },
  hip_shift_top: {
    label: "Hip shift at the top",
    meaning: "Sideways move of the hip centre since address. Positive = toward the target.",
  },
  hip_shift_impact: {
    label: "Hip shift at impact",
    meaning: "Sideways move of the hip centre since address. Positive = toward the target.",
  },
  head_shift_top: {
    label: "Head shift at the top",
    meaning: "Sideways move of the head since address. Positive = toward the target.",
  },
  head_shift_impact: {
    label: "Head shift at impact",
    meaning: "Sideways move of the head since address. Positive = toward the target.",
  },
  lead_arm_bend_top: { label: "Lead arm bend at the top", meaning: "0° = a straight lead arm." },
  stance_width_address: { label: "Stance width", meaning: "Distance between the ankles divided by shoulder width." },
  // Club measurements (cv-service/app/swing/club.py).
  shaft_points_downswing: {
    label: "Where the shaft points, halfway down",
    meaning: "Shaft extended to the ground. Positive = beyond the ball (steep, over the top); negative = inside it.",
  },
  hand_path_downswing: {
    label: "Hand path, down vs. back",
    meaning: "Positive = the hands come down outside the path they went back on.",
  },
  shaft_past_parallel_top: {
    label: "Shaft at the top",
    meaning: "0° = parallel to the ground. Positive = past parallel; negative = short of it.",
  },
};

/** Measurements that come from club tracking rather than the body. */
export const CLUB_MEASUREMENTS = new Set(["shaft_points_downswing", "hand_path_downswing", "shaft_past_parallel_top"]);

export function isClubFinding(f: SwingFinding): boolean {
  return f.measurements.some((m) => CLUB_MEASUREMENTS.has(m));
}

export function measurementInfo(name: string): MeasurementInfo {
  return INFO[name] ?? { label: name.replace(/_/g, " "), meaning: "" };
}

export function formatMeasurement(m: SwingMeasurement): string {
  const sign = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "");
  switch (m.unit) {
    case "deg":
      return m.name.includes("change") || m.name.includes("past_parallel")
        ? `${sign(m.value)}${Math.abs(m.value).toFixed(1)}°`
        : `${m.value.toFixed(1)}°`;
    case "% torso":
      return `${sign(m.value)}${Math.abs(m.value).toFixed(1)}% of torso`;
    case "s":
      return `${m.value.toFixed(2)} s`;
    case "ratio":
      return m.name === "tempo_ratio" ? `${m.value.toFixed(1)} : 1` : `${m.value.toFixed(2)}×`;
    default:
      return `${m.value} ${m.unit}`;
  }
}

export const RATING: Record<Rating, { text: string; value: string; pill: string; dot: string }> = {
  good: { text: "Good", value: "text-good", pill: "bg-good-soft text-good", dot: "bg-good" },
  watch: { text: "Slightly off", value: "text-warn", pill: "bg-warn-soft text-warn", dot: "bg-warn" },
  bad: { text: "Clearly off", value: "text-bad", pill: "bg-bad-soft text-bad", dot: "bg-bad" },
};

export function confidenceLabel(c: number): { text: string; cls: string } {
  if (c >= 0.75) return { text: "High confidence", cls: "text-good" };
  if (c >= 0.5) return { text: "Medium confidence", cls: "text-warn" };
  return { text: "Low confidence", cls: "text-bad" };
}

export type Tone = "good" | "warn" | "bad" | "neutral";

/** One-line verdict for a swing, from the counts of finding kinds. */
export function verdict(feedback: SwingFeedback | null | undefined): { title: string; tone: Tone } | null {
  if (!feedback) return null;
  const count = (k: string) => feedback.findings.filter((f) => f.kind === k).length;
  const improve = count("improve");
  const watch = count("watch");
  if (improve > 0) return { title: `${improve} ${improve === 1 ? "thing" : "things"} to work on`, tone: "bad" };
  if (watch > 0) return { title: `Looking good, ${watch} ${watch === 1 ? "thing" : "things"} worth checking`, tone: "warn" };
  if (feedback.findings.length > 0) return { title: "Looking good", tone: "good" };
  return { title: "Not enough reliable data", tone: "neutral" };
}

export const TONE_CLASS: Record<Tone, string> = {
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  neutral: "bg-subtle text-mute",
};

/** "Down-the-line swing" plus a readable date, instead of the uploaded file name. */
export function swingTitle(a: Analysis): { title: string; date: string } {
  return {
    title: `${angleLabel(a.video.cameraAngle)} swing`,
    date: new Date(a.createdAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
  };
}
