import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { api, type HealthReport } from "../api";
import { AlertIcon, BrandMark } from "./icons";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium transition-colors sm:px-3.5 ${
    isActive ? "bg-brand-soft text-brand" : "text-mute hover:bg-subtle hover:text-ink"
  }`;

/** Small banner shown only when a backend dependency is down. */
function HealthBanner() {
  const [health, setHealth] = useState<HealthReport | "unreachable" | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => !cancelled && setHealth(h))
      .catch(() => !cancelled && setHealth("unreachable"));
    return () => {
      cancelled = true;
    };
  }, []);

  if (!health) return null;
  let message: string | null = null;
  if (health === "unreachable") {
    message = "The API is not reachable. Start the stack with docker compose up, then reload.";
  } else if (!health.database) {
    message = "The API is running but cannot reach the database.";
  } else if (!health.cvService) {
    message = "The computer-vision service is not responding. Uploads will queue until it is back.";
  } else if (health.poseModelPresent === false) {
    message =
      "The pose model file is missing from the computer-vision service. Run scripts/download_pose_model.sh or rebuild the image.";
  }
  if (!message) return null;
  return (
    <div role="alert" className="bg-bad-soft px-4 py-2.5 text-sm text-bad">
      <div className="mx-auto flex max-w-6xl items-center gap-2 sm:px-2">
        <AlertIcon className="h-4 w-4 shrink-0" />
        {message}
      </div>
    </div>
  );
}

export default function Layout() {
  return (
    <div className="min-h-screen">
      <HealthBanner />
      <header className="sticky top-0 z-20 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-2.5 whitespace-nowrap font-display text-lg font-semibold tracking-tight">
            <BrandMark />
            <span className="hidden sm:inline">Swing Coach</span>
          </Link>
          <nav className="flex gap-1" aria-label="Main">
            <NavLink to="/" end className={navClass}>
              My swings
            </NavLink>
            <NavLink to="/analyse" className={navClass}>
              <span className="sm:hidden">Analyse</span>
              <span className="hidden sm:inline">Analyse a swing</span>
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  );
}
