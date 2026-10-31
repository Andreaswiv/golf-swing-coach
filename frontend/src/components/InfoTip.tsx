import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Info } from "lucide-react";

interface Props {
  /** Visible text next to the (i). */
  label: string;
  /** What the explanation is about, for screen readers: "What does low confidence mean?" */
  question: string;
  /** Show only the (i); `label` is still read out. */
  iconOnly?: boolean;
  /** Which way the pop-up extends from the (i): "end" (leftward) or "start" (rightward). */
  align?: "start" | "end";
  children: ReactNode;
}

/**
 * A label with an (i) that explains it. Opens on hover, on keyboard focus and on tap (touch
 * screens have no hover); closes on Escape, on tapping elsewhere or when focus leaves.
 */
export default function InfoTip({ label, question, iconOnly = false, align = "end", children }: Props) {
  const id = useId();
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const open = pinned || hovered;

  useEffect(() => {
    if (!pinned) return;
    const close = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setPinned(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [pinned]);

  return (
    <span
      ref={root}
      className="relative inline-flex items-center"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        aria-label={`${label}. ${question}`}
        onClick={(e) => {
          e.stopPropagation();
          setPinned((p) => !p);
        }}
        onFocus={() => setPinned(true)}
        onBlur={() => setPinned(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setPinned(false);
            setHovered(false);
          }
        }}
        className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
      >
        {!iconOnly && label}
        <Info className="size-3.5" />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`absolute bottom-full ${align === "start" ? "left-0" : "right-0"} z-20 mb-1.5 w-60 rounded-lg border bg-popover px-3 py-2.5 text-left text-xs font-normal leading-snug text-popover-foreground shadow-lg`}
        >
          {children}
        </span>
      )}
    </span>
  );
}
