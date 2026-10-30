import type { CameraAngle } from "../api";

/**
 * Top-down sketch of where to put the camera. The golfer stands at the centre,
 * the ball sits on the target line (dashed), and the phone icon shows the camera.
 */
export default function CameraDiagram({ angle }: { angle: CameraAngle }) {
  // Target line runs left -> right. Face-on camera is in front of the golfer
  // (below in the sketch); down-the-line camera is behind the ball, looking along the line.
  const camera = angle === "face_on" ? { x: 90, y: 112, rot: 0 } : { x: 16, y: 60, rot: 90 };
  return (
    <svg viewBox="0 0 180 130" className="h-28 w-full" role="img" aria-label={`Camera position for ${angle === "face_on" ? "face-on" : "down-the-line"}`}>
      <line x1="8" y1="60" x2="172" y2="60" stroke="#b9c2b4" strokeWidth="1.5" strokeDasharray="4 4" />
      <path d="M166 55l6 5-6 5" fill="none" stroke="#b9c2b4" strokeWidth="1.5" />
      <ellipse cx="90" cy="40" rx="15" ry="7" fill="#1d6a43" opacity="0.9" />
      <circle cx="90" cy="40" r="4.5" fill="#ffffff" />
      <circle cx="116" cy="60" r="3" fill="#16201a" />
      <g transform={`translate(${camera.x} ${camera.y}) rotate(${camera.rot})`}>
        <rect x="-9" y="-6" width="18" height="12" rx="3" fill="#4aa3df" />
        <path d="M-5 -6 L0 -16 L5 -6" fill="none" stroke="#4aa3df" strokeWidth="1.5" opacity="0.7" />
      </g>
    </svg>
  );
}
