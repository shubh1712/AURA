"use client";

import React from "react";
import type {
  DecisionModel,
  DecisionRecommendation,
  ResilienceReport,
  ScenarioSet,
} from "@/types";
import { ResilienceScoreGauge } from "./ResilienceScoreGauge";
import { ResiliencePillarBreakdown } from "./ResiliencePillarBreakdown";
import { ResilienceVulnerabilityPanel } from "./ResilienceVulnerabilityPanel";
import { ResilienceHedgeActions } from "./ResilienceHedgeActions";
import { getRatingMetadata, getStressTestMetadata } from "@/lib/resilienceHelpers";

interface ResilienceDashboardProps {
  report: ResilienceReport;
  decisionModel?: DecisionModel | null;
  recommendation?: DecisionRecommendation | null;
  scenarioSet?: ScenarioSet | null;
  decisionTitle?: string;
}

export function ResilienceDashboard({
  report,
  recommendation,
  decisionTitle,
}: ResilienceDashboardProps) {
  // Defensive guard in case report is null or undefined
  if (!report) {
    return null;
  }

  const ratingMeta = getRatingMetadata(report.rating || report.overall_score);
  const stressMeta = getStressTestMetadata(Boolean(report.stress_test_passed));
  const actionCount = recommendation?.action_plan?.actions?.length;

  return (
    <section
      aria-label="Decision Resilience Dashboard"
      id="section-resilience-dashboard"
      className="space-y-7 print:space-y-6"
    >
      {/* Dashboard Executive Header */}
      <div className="rounded-2xl border border-zinc-800 bg-gradient-to-r from-zinc-950 via-zinc-900/60 to-zinc-950 p-6 sm:p-7 space-y-4 text-zinc-100 shadow-md print:bg-white print:border-zinc-300 print:text-black">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-zinc-800/80 print:border-zinc-300">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono uppercase tracking-wider text-indigo-400 print:text-zinc-700 font-semibold">
                Stage 6: Resilience Engine
              </span>
              <span className="h-1 w-1 rounded-full bg-zinc-600 print:hidden" />
              <span className="text-[11px] font-mono text-zinc-400 print:text-zinc-600">
                Deterministic Stress-Testing
              </span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-white print:text-black tracking-tight">
              Decision Resilience &amp; Stress-Test Analysis
            </h2>
          </div>

          {/* Quick Badges */}
          <div className="flex items-center gap-2.5 flex-wrap">
            <span
              className={`inline-flex items-center rounded-md border px-3 py-1 text-xs font-mono font-semibold uppercase tracking-wider ${ratingMeta.colorClass.badgeBg} ${ratingMeta.colorClass.badgeBorder} ${ratingMeta.colorClass.badgeText} print:bg-zinc-100 print:text-black print:border-zinc-300`}
            >
              {ratingMeta.label}
            </span>
            <span
              className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-mono font-medium ${
                stressMeta.passed
                  ? "border-emerald-800/80 bg-emerald-950/40 text-emerald-300 print:bg-zinc-100 print:text-black"
                  : "border-rose-800/80 bg-rose-950/40 text-rose-300 print:bg-zinc-100 print:text-black"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full mr-1.5 ${
                  stressMeta.passed ? "bg-emerald-400" : "bg-rose-400"
                }`}
              />
              {stressMeta.badgeLabel}
            </span>
          </div>
        </div>

        <p className="text-xs sm:text-sm text-zinc-300 print:text-zinc-700 leading-relaxed max-w-4xl font-sans">
          Evaluates the mathematical and structural robustness of the recommended course of action across hard constraint tolerances, pessimistic scenario survivability, contingency coverage, and information uncertainty.
          {decisionTitle && (
            <span className="block mt-1 text-zinc-400 print:text-zinc-600 italic">
              Decision Context: &ldquo;{decisionTitle}&rdquo;
            </span>
          )}
        </p>
      </div>

      {/* 1. Overall Score & Heuristic Rating Gauge */}
      <ResilienceScoreGauge
        score={report.overall_score}
        rating={report.rating}
        stressTestPassed={report.stress_test_passed}
        calculationVersion={report.calculation_version}
        reportId={report.id}
      />

      {/* 2. Four-Pillar Breakdown */}
      <ResiliencePillarBreakdown subScores={report.sub_scores} />

      {/* 3. Vulnerabilities & Recommended Hedges Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-7">
        {/* Left: Critical Vulnerabilities */}
        <ResilienceVulnerabilityPanel
          criticalVulnerabilities={report.critical_vulnerabilities}
        />

        {/* Right: Recommended Hedges */}
        <ResilienceHedgeActions
          recommendedHedges={report.recommended_hedges}
          recommendationActionCount={actionCount}
        />
      </div>
    </section>
  );
}
