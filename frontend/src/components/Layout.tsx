import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { api, type HealthReport } from "@/api";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { BrandMark } from "./icons";

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex h-9 items-center rounded-full px-4 text-[15px] font-medium whitespace-nowrap transition-colors duration-200",
    isActive ? "bg-foreground/[0.07] text-foreground" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
  );

/** Shown only when a backend dependency is down. */
function HealthBanner({ className }: { className?: string }) {
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
    <div className={cn("mx-auto max-w-6xl px-4 pt-4 sm:px-8", className)}>
      <Alert variant="destructive">
        <AlertCircle />
        <AlertDescription>{message}</AlertDescription>
      </Alert>
    </div>
  );
}

/** True once the page has scrolled past `threshold` px: the overlay header turns into a frosted bar. */
function useScrolledPast(threshold: number) {
  const [past, setPast] = useState(false);
  useEffect(() => {
    const onScroll = () => setPast(window.scrollY > threshold);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);
  return past;
}

/**
 * Header over a dark-green top (the homepage hero, the analysis header): transparent with white text,
 * a frosted white bar once the green has scrolled away.
 */
function OverlayHeader({ home }: { home: boolean }) {
  const past = useScrolledPast(home ? window.innerHeight * 0.85 : 260);
  const link = cn(
    "rounded-full px-4 py-2 transition-colors duration-200",
    past ? "hover:bg-black/5" : "hover:bg-white/10",
  );
  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-30 transition-[background-color,color,box-shadow] duration-300",
        past ? "bg-white/85 text-[#111] shadow-[0_1px_0_#e6e6e2] backdrop-blur-md" : "text-white",
      )}
    >
      <div className="mx-auto flex h-18 max-w-[90rem] items-center justify-between gap-6 px-6 sm:px-10">
        <Link to="/" className="flex items-center gap-2.5 text-[19px] font-medium tracking-tight">
          <BrandMark className="size-7" />
          Swing Coach
        </Link>
        <nav className="hidden items-center gap-1 text-[15px] font-medium md:flex" aria-label="Main">
          {home ? (
            <>
              <a href="#metrics" className={link}>
                Your numbers
              </a>
              <a href="#swings" className={link}>
                Your swings
              </a>
            </>
          ) : (
            <Link to="/" className={link}>
              My swings
            </Link>
          )}
        </nav>
        <Button asChild variant={past ? "default" : "white"}>
          <Link to="/analyse">Analyse a swing</Link>
        </Button>
      </div>
    </header>
  );
}

export default function Layout() {
  const path = useLocation().pathname;
  const home = path === "/";
  // A finished analysis opens with a dark-green header like the homepage; its progress page does not.
  const analysis = /^\/analyses\/[^/]+$/.test(path);
  if (home || analysis) {
    return (
      <div className="min-h-screen bg-background">
        <OverlayHeader home={home} />
        <HealthBanner className="absolute inset-x-0 top-20 z-20" />
        <Outlet />
      </div>
    );
  }
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-background/85 shadow-[0_1px_0_#e6e6e2] backdrop-blur-md">
        <div className="mx-auto flex h-18 max-w-6xl items-center justify-between gap-8 px-4 sm:px-8">
          <div className="flex items-center gap-8">
            <Link to="/" className="flex shrink-0 items-center gap-2.5 text-[19px] font-medium tracking-tight whitespace-nowrap">
              <BrandMark className="size-7" />
              <span className="hidden sm:inline">Swing Coach</span>
            </Link>
            <nav className="flex items-center gap-1" aria-label="Main">
              <NavLink to="/" end className={navClass}>
                My swings
              </NavLink>
              <NavLink to="/analyse" className={navClass}>
                <span className="sm:hidden">Analyse</span>
                <span className="hidden sm:inline">Analyse a swing</span>
              </NavLink>
            </nav>
          </div>
        </div>
      </header>
      <HealthBanner />
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-8 sm:py-12">
        <Outlet />
      </main>
    </div>
  );
}
