"use client";

import React from "react";

interface ActionUnavailableBannerProps {
  reason?: string | null;
  historical?: boolean;
}

export function ActionUnavailableBanner({
  reason,
  historical = false,
}: ActionUnavailableBannerProps) {
  return (
    <div
      id="action-unavailable-banner"
      role="region"
      aria-label="Action Intelligence Unavailable Notice"
      className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 sm:p-7 space-y-3 text-zinc-100 shadow-sm print:border-zinc-300 print:bg-white print:text-black"
    >
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-zinc-500" />
        <h3 className="text-base font-semibold text-white print:text-black tracking-tight">
          Action Intelligence Unavailable
        </h3>
      </div>

      <p className="text-xs sm:text-sm leading-relaxed text-zinc-400 print:text-zinc-600">
        {historical
          ? "This historical analysis was executed without an authoritative Stage 4 Decision Recommendation. Action Intelligence requires a completed Stage 4 recommendation to synthesize an operational roadmap."
          : reason ||
            "Action Intelligence requires an authoritative Stage 4 Decision Recommendation. Upstream analysis artifacts must complete successfully before action plans can be generated."}
      </p>
    </div>
  );
}
