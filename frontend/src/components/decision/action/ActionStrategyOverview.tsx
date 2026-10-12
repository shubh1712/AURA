"use client";

import React from "react";
import type { IntelligentActionPlan } from "@/types";

interface ActionStrategyOverviewProps {
  plan: IntelligentActionPlan;
  cached?: boolean;
}

export function ActionStrategyOverview({
  plan,
  cached = false,
}: ActionStrategyOverviewProps) {
  const formattedDate = plan.created_at
    ? new Date(plan.created_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not specified";

  return (
    <div
      id="action-strategy-overview"
      className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 sm:p-6 space-y-4 text-zinc-100 shadow-sm print:border-zinc-300 print:bg-white print:text-black"
    >
      {/* Header with Badges */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/80 pb-4 print:border-zinc-200">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <h3 className="text-base font-semibold text-white print:text-black tracking-tight">
              Operational Strategy Overview
            </h3>
            {cached && (
              <span className="inline-flex items-center rounded-md border border-zinc-700 bg-zinc-800/80 px-2 py-0.5 text-[11px] font-mono text-zinc-300 print:border-zinc-300 print:bg-zinc-100 print:text-zinc-800">
                Cached Roadmap
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-400 print:text-zinc-600">
            Synthesized from Stage 4 recommendation and upstream analytical constraints.
          </p>
        </div>

        {/* Metadata Tags */}
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-zinc-400 print:text-zinc-600">
          <span className="rounded bg-zinc-800/80 px-2 py-1 border border-zinc-700/60 print:bg-zinc-100 print:border-zinc-300">
            Generated: {formattedDate}
          </span>
          <span className="rounded bg-zinc-800/80 px-2 py-1 border border-zinc-700/60 print:bg-zinc-100 print:border-zinc-300" title={`Fingerprint: ${plan.source_recommendation_fingerprint}`}>
            FP: {plan.source_recommendation_fingerprint.slice(0, 13)}...
          </span>
          {Boolean(plan.generation_metadata?.model_name) && (
            <span className="rounded bg-zinc-800/80 px-2 py-1 border border-zinc-700/60 print:bg-zinc-100 print:border-zinc-300">
              {String(plan.generation_metadata.model_name)}
            </span>
          )}
          <span className="rounded bg-zinc-800/80 px-2 py-1 border border-zinc-700/60 print:bg-zinc-100 print:border-zinc-300">
            v{plan.generator_version}
          </span>
        </div>
      </div>

      {/* Strategy Summary */}
      <div className="space-y-2">
        <h4 className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold">
          Executive Rationale &amp; Strategic Trajectory
        </h4>
        <p className="text-sm leading-relaxed text-zinc-200 print:text-black font-normal">
          {plan.strategy_summary || "Not specified"}
        </p>
      </div>

      {/* AI Guidance Disclaimer Banner */}
      <div
        role="note"
        className="rounded-lg border border-indigo-900/40 bg-indigo-950/20 px-3.5 py-2.5 text-xs text-indigo-300/90 flex items-start gap-2.5 print:border-zinc-300 print:bg-zinc-50 print:text-zinc-800"
      >
        <svg
          className="h-4 w-4 text-indigo-400 shrink-0 mt-0.5 print:text-zinc-600"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
            clipRule="evenodd"
          />
        </svg>
        <div className="leading-relaxed">
          <span className="font-semibold text-indigo-200 print:text-black">
            AI-Assisted Operational Guidance:
          </span>{" "}
          This roadmap structures the recommended strategy into verifiable execution steps and decision gates. It does not provide guaranteed quantitative ROI or replace executive oversight.
        </div>
      </div>
    </div>
  );
}
