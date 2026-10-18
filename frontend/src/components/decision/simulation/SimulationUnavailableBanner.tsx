"use client";

import React from "react";

interface SimulationUnavailableBannerProps {
  reason?: string | null;
  historical?: boolean;
}

export function SimulationUnavailableBanner({
  reason,
  historical,
}: SimulationUnavailableBannerProps) {
  const defaultHistoricalMessage =
    "This historical analysis does not contain the multi-stage artifacts required for interactive what-if simulation (Stages 1, 4, and 5: Decision Model, Recommendation, and Future Scenarios). Upstream decision artifacts remain authoritative and preserved below.";

  const defaultPartialMessage =
    "What-if simulation is unavailable because one or more prerequisite pipeline stages (Decision Model, Recommendation, or Future Scenarios) did not complete. Upstream decision artifacts remain authoritative and preserved below.";

  const displayMessage =
    reason || (historical ? defaultHistoricalMessage : defaultPartialMessage);

  return (
    <section
      role="alert"
      aria-label="What-if Simulation Notice"
      className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-5 text-xs text-amber-200 space-y-2.5 print:bg-zinc-50 print:border-zinc-300 print:text-black"
    >
      <div className="flex items-center gap-2.5 font-semibold text-amber-300 print:text-black">
        <span className="h-2 w-2 rounded-full bg-amber-400" />
        <span className="font-mono text-xs uppercase tracking-wider">
          What-if Simulation Unavailable
        </span>
      </div>

      <p className="leading-relaxed text-zinc-300 print:text-black">
        {displayMessage}
      </p>

      <div className="pt-2 border-t border-amber-900/40 print:border-zinc-300 flex items-center justify-between text-[11px] text-amber-300/80 print:text-zinc-600 font-mono">
        <span>Prerequisites: Stages 1, 4 &amp; 5</span>
        <span>Decision Foundation Intact</span>
      </div>
    </section>
  );
}
