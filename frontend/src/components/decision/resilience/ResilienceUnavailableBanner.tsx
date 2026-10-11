"use client";

import React from "react";

interface ResilienceUnavailableBannerProps {
  resilienceError?: string | null;
}

export function ResilienceUnavailableBanner({
  resilienceError,
}: ResilienceUnavailableBannerProps) {
  const defaultMessage =
    "Stage 6 decision resilience evaluation was unavailable or could not complete. All upstream artifacts from Stages 1–5 (decision structure, evidence, boardroom deliberation, recommendation, and future scenarios) remain authoritative and fully preserved below.";
  const displayMessage = resilienceError || defaultMessage;

  return (
    <section
      role="alert"
      aria-label="Resilience Evaluation Notice"
      className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-5 text-xs text-amber-200 space-y-2.5 print:bg-zinc-50 print:border-zinc-300 print:text-black"
    >
      <div className="flex items-center gap-2.5 font-semibold text-amber-300 print:text-black">
        <span className="h-2 w-2 rounded-full bg-amber-400" />
        <span className="font-mono text-xs uppercase tracking-wider">
          Stage 6: Decision Resilience Evaluation Unavailable
        </span>
      </div>

      <p className="leading-relaxed text-zinc-300 print:text-black">
        {displayMessage}
      </p>

      <div className="pt-2 border-t border-amber-900/40 print:border-zinc-300 flex items-center justify-between text-[11px] text-amber-300/80 print:text-zinc-600 font-mono">
        <span>Partial Pipeline Execution</span>
        <span>Decision Foundation (Stages 1–5) Intact</span>
      </div>
    </section>
  );
}
