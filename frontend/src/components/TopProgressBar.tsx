import { useIsFetching } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { safeHex, useBranding } from "../branding";

const MIN_VISIBLE_MS = 550;

/** §20 "lively, not ornamental" motion applied to navigation itself. Two
 * independent triggers keep this honest instead of dry:
 *   1. Every `<Route>` change bursts it — even a page whose data is already
 *      cached (so `useIsFetching` never rises) still gets a clear, visible
 *      "you moved" signal.
 *   2. Any in-flight query (global, no per-route wiring needed since every
 *      page mounts at least one `useQuery`) keeps it running until data
 *      actually lands.
 * Always finishes at 100% before fading, and never shows for less than
 * MIN_VISIBLE_MS, so a cache-hit navigation still reads as a deliberate,
 * felt transition rather than a blip. Colored with the tenant's own brand
 * color when set (CLAUDE.md §21), falling back to the platform gradient. */
export function TopProgressBar() {
  const isFetching = useIsFetching();
  const location = useLocation();
  const branding = useBranding();
  const [visible, setVisible] = useState(false);
  const [width, setWidth] = useState(0);
  const growTimer = useRef<number | null>(null);
  const hideTimer = useRef<number | null>(null);
  const shownAt = useRef(0);

  function beginBurst() {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    setVisible((wasVisible) => {
      if (!wasVisible) shownAt.current = Date.now();
      return true;
    });
    setWidth((w) => (w < 15 ? 15 : w));
    if (growTimer.current === null) {
      growTimer.current = window.setInterval(() => {
        setWidth((w) => (w < 85 ? w + (85 - w) * 0.12 : w));
      }, 180);
    }
  }

  function settle() {
    if (growTimer.current) {
      window.clearInterval(growTimer.current);
      growTimer.current = null;
    }
    setWidth(100);
    const remaining = Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt.current));
    hideTimer.current = window.setTimeout(() => {
      setVisible(false);
      setWidth(0);
    }, remaining + 150);
  }

  // Trigger 1: every navigation, regardless of query state.
  useEffect(() => {
    beginBurst();
    const settleTimer = window.setTimeout(() => {
      if (isFetching === 0) settle();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, MIN_VISIBLE_MS);
    return () => window.clearTimeout(settleTimer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Trigger 2: any query fetching, in either direction.
  useEffect(() => {
    if (isFetching > 0) beginBurst();
    else settle();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFetching]);

  useEffect(
    () => () => {
      if (growTimer.current) window.clearInterval(growTimer.current);
      if (hideTimer.current) window.clearTimeout(hideTimer.current);
    },
    [],
  );

  if (!visible) return null;

  const primary = safeHex(branding.primaryColor);
  const accent = safeHex(branding.accentColor) ?? primary;

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[4px] bg-transparent">
      <div
        className={`relative h-full overflow-hidden rounded-r-full transition-[width] duration-300 ease-out ${
          primary ? "" : "bg-gradient-to-r from-violet-500 via-indigo-500 to-blue-500"
        }`}
        style={{
          width: `${width}%`,
          backgroundImage: primary ? `linear-gradient(to right, ${primary}, ${accent})` : undefined,
          boxShadow: primary ? `0 0 12px 1px ${primary}a6` : "0 0 12px 1px rgba(99,102,241,0.65)",
        }}
      >
        {/* A lighter band sweeping across the fill — reads as "actively
            working" instead of a bar that only ever jumps in size. */}
        <div className="animate-progress-shimmer absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-white/60 to-transparent" />
      </div>
    </div>
  );
}
