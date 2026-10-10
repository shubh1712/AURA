"use client";

import React from "react";

interface PartialSuccessBannerProps {
  recommendationError?: string | null;
}

export function PartialSuccessBanner({
  recommendationError,
}: PartialSuccessBannerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-2xl border border-amber-800/80 bg-amber-950/30 p-6 sm:p-7 space-y-4 text-zinc-100 shadow-md backdrop-blur-sm print:bg-zinc-50 print:border-zinc-400 print:text-black"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-amber-900/40 print:border-zinc-300">
        <div className="flex items-center gap-2.5">
          <span className="flex h-3 w-3 rounded-full bg-amber-400 shrink-0" />
          <h3 className="text-base sm:text-lg font-semibold text-amber-200 print:text-zinc-900 tracking-tight">
            Partial Analysis Complete — Recommendation Unavailable
          </h3>
        </div>

        <span className="rounded bg-amber-950/60 px-2.5 py-1 text-xs font-mono text-amber-300 border border-amber-800/60 shrink-0 print:bg-zinc-100 print:text-zinc-800 print:border-zinc-300">
          Stage 4 Partial Success
        </span>
      </div>

      {/* Primary Message Required by Specification */}
      <div className="space-y-2 text-xs sm:text-sm leading-relaxed text-zinc-200 print:text-zinc-800 font-sans">
        <p className="font-medium text-white print:text-black">
          The Decision Framer, Evidence Engine, and AI Boardroom completed successfully, but the recommendation could not be generated.
        </p>
        <p className="text-zinc-300 print:text-zinc-700">
          All analytical artifacts from Stages 1 through 3 — including the structured decision decomposition,
          empirical evidence findings, and multi-perspective boardroom deliberation — are preserved and fully
          inspectable below.
        </p>
      </div>

      {/* Optional Stage 4 Error Context */}
      {recommendationError && (
        <div className="rounded-lg border border-amber-900/50 bg-zinc-950/60 p-3.5 space-y-1 text-xs print:bg-white print:border-zinc-300">
          <span className="text-[10px] font-mono uppercase tracking-wider text-amber-400 font-semibold block">
            Stage 4 Pipeline Context:
          </span>
          <p className="font-mono text-zinc-300 print:text-zinc-800 break-words text-[11px]">
            {recommendationError}
          </p>
        </div>
      )}

      {/* Quick Links to Available Stages */}
      <nav aria-label="Available analytical sections" className="pt-2 flex flex-wrap items-center gap-2 print:hidden">
        <span className="text-xs text-zinc-400 font-medium mr-1">Explore Available Stages:</span>
        <a
          href="#section-decision-model"
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
        >
          1. Decision Framer
        </a>
        <a
          href="#section-evidence-engine"
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
        >
          2. Evidence Engine
        </a>
        <a
          href="#section-ai-boardroom"
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
        >
          3. AI Boardroom
        </a>
      </nav>
    </div>
  );
}
