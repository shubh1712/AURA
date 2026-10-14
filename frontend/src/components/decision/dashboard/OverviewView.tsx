"use client";

import React from "react";
import type { AnalysisResponse } from "@/types";
import {
  extractConciseRecommendation,
  evaluateDecisionIntegrity,
  formatEnumLabel,
} from "@/lib/formatters";
import { FeasibilityTargetChart } from "../charts/FeasibilityTargetChart";
import { AlternativesComparisonMatrix } from "../charts/AlternativesComparisonMatrix";
import { getStatusConfig } from "@/lib/recommendationHelpers";

interface OverviewViewProps {
  result: AnalysisResponse;
  onExploreClick?: () => void;
  onActionClick?: () => void;
  onDetailsClick?: () => void;
}

export function OverviewView({
  result,
  onExploreClick,
  onActionClick,
  onDetailsClick,
}: OverviewViewProps) {
  const { decision_model, recommendation } = result;

  // Extract decision title cleanly
  const decisionTitle =
    decision_model?.decision?.summary || result.question || "Strategic Decision";

  // Recommendation status
  const statusCfg = recommendation
    ? getStatusConfig(recommendation.decision_status)
    : null;

  // Integrity evaluation (no green badges on unresolved critical issues)
  const integrity = evaluateDecisionIntegrity(result);

  // Concise recommendation (1-2 sentences)
  const conciseRecommendation = recommendation
    ? extractConciseRecommendation(recommendation.recommended_action)
    : result.message || "Analysis computed.";

  // Rationale short paragraph
  const executiveRationale = recommendation?.executive_rationale || result.message;

  // Top 3 Decision-changing missing inputs
  const missingInputs =
    recommendation?.uncertainty_assessment?.critical_missing_information?.slice(0, 3) || [];

  // Conditions that would change recommendation
  const changingConditions =
    recommendation?.uncertainty_assessment?.conditions_changing_recommendation?.slice(0, 3) || [];

  // Primary alternatives
  const alternatives = recommendation?.alternative_options || [];

  return (
    <div className="space-y-6" aria-label="Executive Recommendation Overview">
      {/* 1. Executive Summary & Recommendation Hero */}
      <section
        aria-label="Executive Recommendation"
        className="rounded-2xl border border-zinc-800 bg-gradient-to-b from-zinc-900/60 via-zinc-900/30 to-zinc-950 p-6 sm:p-8 space-y-5 text-zinc-100 shadow-md"
      >
        {/* Status & Integrity Badges */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
              Executive Recommendation
            </span>

            {/* Recommendation Status */}
            {statusCfg && (
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-xs font-mono font-semibold border ${statusCfg.badgeClass}`}
              >
                <span className={`h-2 w-2 rounded-full ${statusCfg.dotClass}`} />
                {statusCfg.label}
              </span>
            )}

            {/* Decision Readiness / Integrity Badge */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium border ${integrity.badgeBorderClass} ${integrity.badgeBgClass} ${integrity.badgeTextClass}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${integrity.dotClass}`} />
              {integrity.readinessLabel}
            </span>
          </div>

          <div className="text-[11px] font-mono text-zinc-400">
            {decision_model?.decision?.time_horizon && (
              <span>Horizon: {formatEnumLabel(decision_model.decision.time_horizon)}</span>
            )}
          </div>
        </div>

        {/* Decision Title */}
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block mb-1">
            Decision Focal Question
          </span>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight leading-snug">
            {decisionTitle}
          </h2>
        </div>

        {/* 1–2 Sentence Recommendation Card */}
        <div className="rounded-xl border border-emerald-900/60 bg-emerald-950/25 p-5 space-y-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-bold block">
            AURA Recommendation
          </span>
          <p className="text-base sm:text-lg font-semibold text-emerald-100 leading-snug">
            {conciseRecommendation}
          </p>
          {executiveRationale && (
            <p className="text-xs sm:text-sm text-zinc-300 font-sans leading-relaxed pt-1">
              {executiveRationale}
            </p>
          )}
        </div>

        {/* Quick Nav CTA Bar */}
        <div className="flex flex-wrap items-center gap-3 pt-2">
          {onExploreClick && (
            <button
              type="button"
              onClick={onExploreClick}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer"
            >
              <span>Explore Scenarios &amp; What-If</span>
              <span>&rarr;</span>
            </button>
          )}
          {onActionClick && (
            <button
              type="button"
              onClick={onActionClick}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer"
            >
              <span>View Action Plan</span>
              <span>&rarr;</span>
            </button>
          )}
          {onDetailsClick && (
            <button
              type="button"
              onClick={onDetailsClick}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer underline ml-auto"
            >
              <span>Full 6-Stage Details</span>
            </button>
          )}
        </div>
      </section>

      {/* 2. Critical Integrity Findings Callout (Never green when issues exist) */}
      {integrity.hasCriticalIssues && integrity.issues.length > 0 && (
        <div
          role="alert"
          className="rounded-xl border border-amber-900/60 bg-amber-950/25 p-5 space-y-2.5 text-xs text-amber-200 shadow-sm"
        >
          <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            Decision Integrity Findings &amp; Unresolved Calculations
          </div>
          <p className="text-zinc-300 leading-relaxed font-sans">
            AURA detected boundary conditions or unverified prerequisites that require executive awareness prior to broad commitment:
          </p>
          <ul className="space-y-1.5 list-disc list-inside text-amber-200/90 pl-1">
            {integrity.issues.map((issue, idx) => (
              <li key={idx} className="leading-snug">
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 3. Quantitative & Financial Feasibility (Only where supported!) */}
      <FeasibilityTargetChart decisionModel={decision_model} />

      {/* 4. Comparison of Viable Alternatives (Comparison Matrix) */}
      {alternatives.length > 0 && (
        <AlternativesComparisonMatrix
          primaryAction={conciseRecommendation}
          alternatives={alternatives}
        />
      )}

      {/* 5. Two-Column Governance Grid: Top 3 Missing Inputs & Trigger Conditions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Top Three Decision-Changing Missing Inputs */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3 text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80">
            <span className="font-mono text-[10px] uppercase tracking-wider text-sky-400 font-semibold">
              Epistemic Risks
            </span>
            <span className="font-mono text-[10px] text-zinc-500">Ranked by Impact</span>
          </div>
          <h4 className="text-sm font-semibold text-white tracking-tight">
            Top Missing Inputs That Could Shift Decision
          </h4>

          {missingInputs.length > 0 ? (
            <ul className="space-y-2 pt-1">
              {missingInputs.map((input, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 text-zinc-200"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-sky-950 text-sky-300 font-mono text-[10px] font-bold border border-sky-800/60">
                    {idx + 1}
                  </span>
                  <span className="leading-snug font-sans">{input}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-zinc-500 italic">
              No critical missing inputs identified; baseline inputs sufficient for determination.
            </p>
          )}
        </div>

        {/* Conditions That Would Change the Recommendation */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3 text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80">
            <span className="font-mono text-[10px] uppercase tracking-wider text-amber-400 font-semibold">
              Pivot Triggers
            </span>
            <span className="font-mono text-[10px] text-zinc-500">Reversal Conditions</span>
          </div>
          <h4 className="text-sm font-semibold text-white tracking-tight">
            Conditions That Would Reverse Recommendation
          </h4>

          {changingConditions.length > 0 ? (
            <ul className="space-y-2 pt-1">
              {changingConditions.map((cond, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 text-zinc-200"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-amber-950 text-amber-300 font-mono text-[10px] font-bold border border-amber-800/60">
                    !
                  </span>
                  <span className="leading-snug font-sans">{cond}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-zinc-500 italic">
              Recommendation remains robust under baseline modelled conditions.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
