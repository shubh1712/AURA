"use client";

import React from "react";
import type { DecisionGate } from "@/types";

interface DecisionGateCardProps {
  gate: DecisionGate;
  index?: number;
}

export function DecisionGateCard({ gate, index }: DecisionGateCardProps) {
  return (
    <div
      className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-4 sm:p-4.5 space-y-3.5 text-xs text-zinc-200 transition-colors"
      role="region"
      aria-label={`Decision Gate: ${gate.target_milestone}`}
    >
      {/* Top Header: Gate Badge & Milestone Target */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-amber-900/30">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-950/70 text-amber-300 border border-amber-800/80">
            <svg
              className="h-3 w-3 text-amber-400"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            DECISION GATE {typeof index === "number" ? `#${index + 1}` : ""}
          </span>

          <span className="text-[11px] font-mono text-zinc-300 bg-zinc-900/80 px-2 py-0.5 rounded border border-zinc-800">
            Milestone: <strong className="text-white font-medium">{gate.target_milestone}</strong>
          </span>
        </div>

        <span className="font-mono text-[10px] text-zinc-500">
          ID: {gate.id}
        </span>
      </div>

      {/* Prerequisite Gate Condition */}
      <div className="space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-amber-400 font-semibold block">
          Gate Prerequisite Condition
        </span>
        <p className="text-zinc-100 text-xs sm:text-sm font-medium leading-relaxed bg-zinc-950/60 p-3 rounded-lg border border-zinc-800/80">
          {gate.condition}
        </p>
      </div>

      {/* Verification Method & Fallback Action Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
        {/* Verification Method */}
        <div className="space-y-1 bg-zinc-950/40 p-3 rounded-lg border border-zinc-800/60">
          <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400 font-semibold flex items-center gap-1">
            <svg
              className="h-3 w-3 text-sky-400"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            Verification &amp; Audit Method
          </span>
          <p className="text-zinc-300 text-xs leading-relaxed font-sans">
            {gate.verification_method}
          </p>
        </div>

        {/* Fallback Action */}
        <div className="space-y-1 bg-zinc-950/40 p-3 rounded-lg border border-zinc-800/60">
          <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold flex items-center gap-1">
            <svg
              className="h-3 w-3 text-rose-400"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Fallback if Condition Fails
          </span>
          <p className="text-zinc-300 text-xs leading-relaxed font-sans">
            {gate.fallback_action}
          </p>
        </div>
      </div>
    </div>
  );
}
