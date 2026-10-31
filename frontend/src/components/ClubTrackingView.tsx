import type { SwingAnalysis } from "@/api";
import { Card } from "@/components/ui/card";

function pct(v: number | undefined): string {
  return v === undefined ? "–" : `${Math.round(v * 100)}%`;
}

/** How well the club was tracked (cv-service/app/swing/club.py), or why it was not. */
export default function ClubTrackingView({ swing }: { swing: SwingAnalysis }) {
  const club = swing.club;

  if (!club?.tracked) {
    return (
      <Card className="gap-0 p-6">
        <h2 className="text-base">Club tracking</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          The club was not tracked in this swing, so there is no club feedback or swing plane. Swings uploaded
          before club tracking was added have to be uploaded again: “Re-analyse” reuses the saved joint positions
          and does not look at the video.
        </p>
      </Card>
    );
  }

  const share = club.found_share;
  const parts: [string, number | undefined][] = [
    ["Shaft", share?.shaft],
    ["Hands", share?.hands],
    ["Club head", share?.head],
  ];
  return (
    <Card className="gap-0 p-6">
      <h2 className="text-base">Club tracking</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Share of the checked frames where each part of the club was found.
        {club.frames_checked !== undefined &&
          club.frames_total !== undefined &&
          club.frames_checked < club.frames_total &&
          ` To save time, only the ${club.frames_checked} frames around the swing were checked (of ${club.frames_total}).`}
        {!!club.rejected_frames &&
          ` In ${club.rejected_frames} ${club.rejected_frames === 1 ? "frame" : "frames"}, a detection that could not be the club (too far from the hands, or longer than the club) was left out.`}
      </p>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        {parts.map(([label, v]) => (
          <div key={label} className="rounded-lg bg-muted px-2 py-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className={`tnum text-lg font-semibold ${v !== undefined && v < 0.5 ? "text-warn" : ""}`}>{pct(v)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-muted-foreground">
        The club head blurs in the fast part of the swing, so it is found less often than the shaft. Where it is
        missing, its position is taken from the end of the shaft (drawn dashed on the video).
        {swing.camera_angle === "down_the_line"
          ? club.plane
            ? " The dashed red line is the swing plane: the shaft line at address, from the ball through the hands."
            : " No swing plane: the club was not found clearly enough at address."
          : " The swing plane is only drawn for down-the-line videos."}
      </p>
    </Card>
  );
}
