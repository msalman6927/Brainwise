"use client";

import { useEffect, useState } from "react";
import { LevelBadge } from "@/components/Chips";
import type { ScoreResult } from "@/lib/types";

/** Score reveal card: count-up to the server-provided IQ (~800ms) + level badge
 *  scale-in (§5.3, §8.5, §14.4). The number is never computed client-side —
 *  the animation only interpolates the display toward `score.iq_score`.
 *  `prefers-reduced-motion` → jump straight to the final value. */
export function ScoreReveal({ score }: { score: ScoreResult }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    if (reduced) {
      // defer so the value lands after mount without a sync setState in the effect
      raf = requestAnimationFrame(() => setDisplay(score.iq_score));
      return () => cancelAnimationFrame(raf);
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / 800, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(score.iq_score * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [score.iq_score]);

  return (
    <div
      role="status"
      className="relative overflow-hidden rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 via-white to-sky-50 p-5 text-center shadow-sm md:p-6"
    >
      <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">
        Your readiness score
      </p>
      <p className="mt-1 text-5xl font-extrabold tracking-tight text-slate-900 md:text-6xl">
        {display}
      </p>
      <div className="mt-3 flex justify-center bw-scale-in">
        <LevelBadge level={score.level} size="lg" />
      </div>
      <p className="mt-3 text-sm text-muted">This sets the depth of your explanation.</p>
      <span className="sr-only">
        Score: IQ {score.iq_score}, level {score.level}.
      </span>
    </div>
  );
}
