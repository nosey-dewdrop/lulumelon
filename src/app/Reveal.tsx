"use client";

/**
 * Two behaviours the page needs and one rule they both obey.
 *
 * A block arrives when it is scrolled to, and a figure counts up to the number
 * it is. Neither is decoration here: the figures are the measurements this
 * repository paid for, and a number that lands on 339 after climbing to it is
 * read rather than skipped.
 *
 * The rule both obey is `prefers-reduced-motion`. Somebody who has asked their
 * machine to stop moving things gets the finished state on the first frame,
 * which is also what a crawler and a printed page get: the markup carries the
 * final text either way, so nothing here is content that only exists in motion.
 */
import { useEffect, useRef, useState } from "react";

function usesMotion(): boolean {
  if (typeof window === "undefined") return false;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** True once this element has been on screen, and true forever after. */
function useSeen<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (!usesMotion() || typeof IntersectionObserver === "undefined") {
      setSeen(true);
      return;
    }
    const watcher = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          watcher.disconnect();
        }
      },
      // A little before the edge, so a block is finished arriving by the time
      // it is properly in view rather than animating under the reader's eye.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.15 },
    );
    watcher.observe(node);
    return () => watcher.disconnect();
  }, []);

  return { ref, seen };
}

export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  /** Milliseconds, for staggering neighbours in a row. */
  delay?: number;
  className?: string;
}) {
  const { ref, seen } = useSeen<HTMLDivElement>();

  return (
    <div
      ref={ref}
      className={`reveal ${seen ? "reveal-in" : ""} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

const DURATION = 900;

/**
 * A figure that climbs to itself.
 *
 * `value` is the string as it should end up, so the money sign, the decimal
 * places and the thousands separator are the page's rather than this
 * component's. Only the digits move.
 */
export function CountUp({ value }: { value: string }) {
  const { ref, seen } = useSeen<HTMLSpanElement>();
  const [shown, setShown] = useState<string | null>(null);

  useEffect(() => {
    if (!seen) return;
    if (!usesMotion()) {
      setShown(value);
      return;
    }

    const digits = value.match(/[\d.]+/);
    if (!digits) {
      setShown(value);
      return;
    }
    const target = Number(digits[0]);
    const decimals = (digits[0].split(".")[1] ?? "").length;
    if (!Number.isFinite(target)) {
      setShown(value);
      return;
    }

    let frame = 0;
    const started = performance.now();
    const step = (now: number) => {
      const through = Math.min(1, (now - started) / DURATION);
      // Eased out, so it decelerates into the number rather than snapping.
      const eased = 1 - Math.pow(1 - through, 3);
      const at = (target * eased).toFixed(decimals);
      setShown(value.replace(digits[0], at));
      if (through < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [seen, value]);

  // The real value is in the markup from the first render, so what a crawler
  // reads and what a reader ends on are the same string.
  return (
    <span ref={ref} className="tabular-nums">
      {shown ?? value}
    </span>
  );
}
