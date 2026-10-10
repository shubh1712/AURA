"use client";

import React from "react";
import type { DecisionRecommendation } from "@/types";
import { getStatusConfig } from "@/lib/recommendationHelpers";

interface ExecutiveRecommendationHeroProps {
  recommendation: DecisionRecommendation;
}

export function ExecutiveRecommendationHero({
  recommendation,
}: ExecutiveRecommendationHeroProps) {
  const statusCfg = getStatusConfig(recommendation.decision_status);

  return (
    <section
      aria-labelledby="executive-recommendation-heading"
      className={`rounded-2xl border ${statusCfg.borderClass} ${statusCfg.bgClass} p-6 sm:p-8 space-y-6 text-zinc-100 shadow-lg backdrop-blur-sm print:break-inside-avoid print:bg-white print:text-black print:border-zinc-300`}
    >
      {/* Top Header: Badge, Tagline, & Timestamp */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-xs font-mono uppercase tracking-wider text-indigo-400 font-semibold print:text-zinc-700">
              Stage 4 &bull; Executive Synthesis
            </span>

            {/* Decision Status Badge */}
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold border ${statusCfg.badgeClass} print:border-zinc-400 print:bg-zinc-100 print:text-black`}
            >
              <span className={`h-2 w-2 rounded-full ${statusCfg.dotClass} print:bg-zinc-800`} />
              {statusCfg.label}
            </span>
          </div>

          <p className="text-xs sm:text-sm text-zinc-300 print:text-zinc-600 font-sans mt-0.5">
            {statusCfg.tagline}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 text-[11px] font-mono text-zinc-400 print:text-zinc-600">
          <span>Recommendation ID:</span>
          <code className="text-zinc-300 print:text-zinc-800 bg-zinc-950/80 px-2 py-0.5 rounded border border-zinc-800 print:border-zinc-300 break-all">
            {recommendation.id}
          </code>
        </div>
      </div>

      {/* Prominent Insufficient Evidence Warning Banner */}
      {statusCfg.isInsufficientEvidence && (
        <div
          role="alert"
          className="rounded-xl border border-orange-800/80 bg-orange-950/40 p-4 sm:p-5 space-y-2 text-xs sm:text-sm text-orange-200 print:border-zinc-400 print:bg-zinc-50 print:text-zinc-900"
        >
          <div className="flex items-center gap-2 font-semibold text-orange-300 print:text-zinc-900 text-sm sm:text-base">
            <svg
              className="h-5 w-5 text-orange-400 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            Evidence Inconclusive — High Strategic Caution Required
          </div>
          <p className="leading-relaxed text-orange-200/90 print:text-zinc-700">
            The available evidence gathered across consulted sources does not justify a confident
            affirmative commitment. Proceeding without addressing critical missing information or resolving
            contested claims introduces unbounded operational and financial downside.
          </p>
        </div>
      )}

      {/* Non-Approval Notice (Defer or Reject) */}
      {!statusCfg.isApproval && !statusCfg.isInsufficientEvidence && (
        <div
          role="alert"
          className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 space-y-1 text-xs text-zinc-300 print:border-zinc-300 print:bg-zinc-50 print:text-zinc-800"
        >
          <span className="font-semibold text-zinc-100 print:text-zinc-900 uppercase font-mono tracking-wider text-[11px] block">
            Advisory Determination: {statusCfg.label}
          </span>
          <p className="leading-relaxed">
            {recommendation.decision_status === "reject"
              ? "AURA advises against this proposal due to critical strategic trade-offs or insurmountable constraint violations."
              : "AURA recommends deferring this choice until temporal prerequisites, pending data, or external milestones are reached."}
          </p>
        </div>
      )}

      {/* Recommended Action (Primary Focal Point) */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold">
            Recommended Course of Action
          </span>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-5 sm:p-6 text-zinc-100 print:bg-zinc-50 print:text-black print:border-zinc-300">
          <h2
            id="executive-recommendation-heading"
            className="text-lg sm:text-2xl font-bold tracking-tight text-white print:text-black leading-snug break-words"
          >
            {recommendation.recommended_action}
          </h2>
        </div>
      </div>

      {/* Executive Rationale (Answering 'Why') */}
      <div className="space-y-2">
        <span className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold block">
          Executive Rationale &amp; Strategic Alignment
        </span>
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/50 p-4 sm:p-5 text-zinc-300 print:bg-white print:text-zinc-900 print:border-zinc-300 leading-relaxed font-sans text-xs sm:text-sm whitespace-pre-line break-words">
          {recommendation.executive_rationale}
        </div>
      </div>

      {/* Quick In-Page Navigation Bar */}
      <nav
        aria-label="Recommendation sections"
        className="pt-2 flex flex-wrap items-center gap-2 print:hidden"
      >
        <span className="text-xs text-zinc-400 font-medium mr-1">Jump to:</span>
        <a
          href="#section-uncertainty-readiness"
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
        >
          Uncertainty &amp; Readiness
        </a>
        <a
          href="#section-action-roadmap"
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
        >
          Action Roadmap ({recommendation.action_plan.actions.length})
        </a>
        {recommendation.alternative_options.length > 0 && (
          <a
            href="#section-alternative-options"
            className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
          >
            Alternatives ({recommendation.alternative_options.length})
          </a>
        )}
        <a
          href="#section-evidence-traceability"
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors"
        >
          Evidence Traceability
        </a>
      </nav>
    </section>
  );
}
