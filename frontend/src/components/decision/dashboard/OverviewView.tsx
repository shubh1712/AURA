"use client";

import React, { useState } from "react";
import type { AnalysisResponse } from "@/types";
import {
  extractConciseRecommendation,
  evaluateDecisionIntegrity,
  formatEnumLabel,
} from "@/lib/formatters";
import { FeasibilityTargetChart } from "../charts/FeasibilityTargetChart";
import { AlternativesComparisonMatrix } from "../charts/AlternativesComparisonMatrix";
import { BoardroomAlignmentGauge } from "../charts/BoardroomAlignmentGauge";
import { ExecutiveKpiGrid } from "../charts/ExecutiveKpiGrid";
import { RiskUncertaintyMatrix } from "../charts/RiskUncertaintyMatrix";
import { deriveExecutiveKPIs } from "@/lib/visualIntelligence";
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
  const [showFullRationale, setShowFullRationale] = useState(false);
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

  // Visual Intelligence KPIs
  const kpis = deriveExecutiveKPIs(result);

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
        <div className="min-w-0">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block mb-1">
            Decision Focal Question
          </span>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight leading-snug break-words [overflow-wrap:anywhere] min-w-0">
            {decisionTitle}
          </h2>
        </div>

        {/* Visual Intelligence Executive KPI Grid */}
        {kpis.length > 0 && <ExecutiveKpiGrid kpis={kpis} />}

        {/* 1–2 Sentence Recommendation Card with Progressive Disclosure */}
        <div className="rounded-xl border border-emerald-900/60 bg-emerald-950/25 p-5 space-y-2.5 min-w-0 overflow-hidden">
          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-bold block">
            AURA Recommendation
          </span>
          <p className="text-base sm:text-lg font-semibold text-emerald-100 leading-snug break-words [overflow-wrap:anywhere] min-w-0">
            {conciseRecommendation}
          </p>

          {executiveRationale && (
            <div className="pt-1 min-w-0">
              <button
                type="button"
                onClick={() => setShowFullRationale(!showFullRationale)}
                className="text-xs text-emerald-400 hover:text-emerald-300 font-mono inline-flex items-center gap-1.5 cursor-pointer select-none transition-colors duration-150 motion-reduce:transition-none"
                aria-expanded={showFullRationale}
              >
                <span>{showFullRationale ? "Hide Detailed Rationale" : "Read Full Executive Rationale"}</span>
                <span className="text-[10px]">{showFullRationale ? "▲" : "▼"}</span>
              </button>

              <div
                className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
                  showFullRationale
                    ? "grid-rows-[1fr] opacity-100 mt-2 pt-2.5 border-t border-emerald-900/40"
                    : "grid-rows-[0fr] opacity-0"
                }`}
              >
                <div className="overflow-hidden min-w-0">
                  <p className="text-xs sm:text-sm text-zinc-300 font-sans leading-relaxed break-words [overflow-wrap:anywhere]">
                    {executiveRationale}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Quick Nav CTA Bar */}
        <div className="flex flex-wrap items-center gap-3 pt-2">
          {onExploreClick && (
            <button
              type="button"
              onClick={onExploreClick}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-all duration-200 motion-reduce:transition-none cursor-pointer"
            >
              <span>Explore Scenarios &amp; What-If</span>
              <span>&rarr;</span>
            </button>
          )}
          {onActionClick && (
            <button
              type="button"
              onClick={onActionClick}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-all duration-200 motion-reduce:transition-none cursor-pointer"
            >
              <span>View Action Plan</span>
              <span>&rarr;</span>
            </button>
          )}
          {onDetailsClick && (
            <button
              type="button"
              onClick={onDetailsClick}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors duration-150 motion-reduce:transition-none cursor-pointer underline ml-auto"
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

      {/* 3. AI Boardroom Consensus & Alignment Gauge (Multi-Perspective Deliberation) */}
      {result.reasoning_board && (
        <BoardroomAlignmentGauge board={result.reasoning_board} />
      )}

      {/* 4. Quantitative & Financial Feasibility (Only where supported!) */}
      <FeasibilityTargetChart decisionModel={decision_model} />

      {/* 5. Comparison of Viable Alternatives (Comparison Matrix) */}
      {alternatives.length > 0 && (
        <AlternativesComparisonMatrix
          primaryAction={conciseRecommendation}
          alternatives={alternatives}
        />
      )}

      {/* 6. Visual Epistemic Risks & Dynamic Pivot Triggers Matrix */}
      <RiskUncertaintyMatrix
        missingInputs={missingInputs}
        changingConditions={changingConditions}
      />

      {/* 6. Action Intelligence & Execution Roadmap Shortcut */}
      {onActionClick && (
        <section
          aria-label="Action Intelligence Discovery"
          className="rounded-2xl border border-emerald-900/40 bg-gradient-to-r from-emerald-950/25 via-zinc-950 to-zinc-950 p-6 sm:p-7 text-zinc-100 shadow-sm transition-all hover:border-emerald-700/60"
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">
            <div className="space-y-2 max-w-2xl">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded">
                  Action Intelligence
                </span>
                <span className="text-xs text-zinc-400">Execution Framework</span>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Turn Recommendation Into a Grounded Execution Roadmap
              </h3>
              <p className="text-xs text-zinc-300 font-sans leading-relaxed">
                Explore chronological action sequences, operational owners, validation checkpoints, and pre-computed decision gates to execute this choice safely.
              </p>
            </div>

            <button
              type="button"
              onClick={onActionClick}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:bg-emerald-600 px-5 py-3 text-xs font-semibold text-zinc-950 transition-colors cursor-pointer shrink-0 shadow-md font-sans"
              aria-label="Navigate to Action Plan tab"
            >
              <span>Open Action Plan &amp; Roadmap</span>
              <span className="text-sm font-bold">&rarr;</span>
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
