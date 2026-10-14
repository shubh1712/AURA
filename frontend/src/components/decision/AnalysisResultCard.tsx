"use client";

import React, { useState } from "react";
import type { AnalysisResponse } from "@/types";
import { VisualDecisionDashboard } from "./dashboard/VisualDecisionDashboard";
import { PartialSuccessBanner } from "./recommendation/PartialSuccessBanner";
import { ScenarioUnavailableBanner } from "./scenario/ScenarioUnavailableBanner";
import { ResilienceUnavailableBanner } from "./resilience/ResilienceUnavailableBanner";

interface AnalysisResultCardProps {
  result: AnalysisResponse;
  onReset: () => void;
  jobId?: string | null;
  ownerId?: string | null;
}

export function AnalysisResultCard({
  result,
  onReset,
  ownerId,
}: AnalysisResultCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(result.analysis_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handlePrint = () => {
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  const effectiveOwnerId = ownerId || null;

  // Stage 4 Recommendation state evaluation
  const hasValidRecommendation = Boolean(result.recommendation);
  const isRecommendationUnavailable =
    !hasValidRecommendation &&
    (result.recommendation_status === "unavailable" ||
      (result.status === "partial_success" && !result.recommendation));

  // Stage 5 Scenario Engine state evaluation
  const hasValidScenarios = Boolean(
    result.scenarios &&
      result.scenarios.scenarios &&
      result.scenarios.scenarios.length === 3
  );

  const isScenarioUnavailable =
    !hasValidScenarios &&
    (result.scenario_status === "unavailable" ||
      (result.status === "partial_success" && Boolean(result.scenario_error)));

  // Stage 6 Resilience Engine state evaluation
  const hasValidResilience = Boolean(result.resilience);
  const isResilienceUnavailable =
    !hasValidResilience &&
    (result.resilience_status === "unavailable" ||
      (result.status === "partial_success" && Boolean(result.resilience_error)));

  // Overall analysis state evaluation
  const isPartialSuccess =
    result.status === "partial_success" ||
    isRecommendationUnavailable ||
    isScenarioUnavailable ||
    isResilienceUnavailable;

  // Inconsistent state evaluations
  const isRecommendationInconsistent =
    result.recommendation_status === "completed" && !result.recommendation;

  const isScenarioInconsistent =
    result.scenario_status === "completed" && !result.scenarios;

  const isResilienceInconsistent =
    result.resilience_status === "completed" && !result.resilience;

  return (
    <div className="space-y-6 print:space-y-6">
      {/* 1. Analysis Metadata Card */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-7 space-y-4 text-zinc-100 shadow-sm print:bg-white print:border-zinc-300 print:text-black">
        {/* Header with Title and Status */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80 print:border-zinc-300">
          <div>
            <span
              className={`text-xs font-mono uppercase tracking-wider font-semibold ${
                isPartialSuccess
                  ? "text-amber-400 print:text-zinc-700"
                  : "text-emerald-400 print:text-zinc-700"
              }`}
            >
              {isPartialSuccess
                ? "Partial Analysis Complete"
                : "Analysis Complete"}
            </span>
            <h2 className="text-xl font-semibold text-white print:text-black tracking-tight mt-0.5">
              Decision &amp; Evidence Report
            </h2>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center space-x-2">
              <span className="text-xs text-zinc-400 print:text-zinc-600">Status:</span>
              <span
                className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-mono font-medium ${
                  isPartialSuccess
                    ? "border-amber-800/60 bg-amber-950/40 text-amber-300 print:bg-zinc-100 print:text-black print:border-zinc-300"
                    : "border-emerald-800/60 bg-emerald-950/40 text-emerald-300 print:bg-zinc-100 print:text-black print:border-zinc-300"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full mr-1.5 ${
                    isPartialSuccess ? "bg-amber-400" : "bg-emerald-400"
                  }`}
                />
                {result.status}
              </span>
            </div>

            {/* Print / Export Report Button */}
            <button
              type="button"
              onClick={handlePrint}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3 py-1 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm print:hidden"
              title="Print or export decision report to PDF"
              aria-label="Export or print report"
            >
              <svg
                className="h-3.5 w-3.5 text-zinc-300"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="6 9 6 2 18 2 18 9" />
                <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
                <rect x="6" y="14" width="12" height="8" />
              </svg>
              <span>Export / Print</span>
            </button>
          </div>
        </div>

        {/* Question */}
        <div>
          <label className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 mb-1">
            Decision Question
          </label>
          <div className="rounded-lg border border-zinc-800/90 bg-zinc-950/60 p-3.5 text-sm sm:text-base text-zinc-200 print:text-black print:bg-zinc-50 print:border-zinc-300 leading-relaxed break-words font-medium">
            {result.question}
          </div>
        </div>

        {/* Partial Success Banners (When stages failed) */}
        {isRecommendationUnavailable && (
          <section aria-label="Partial Analysis Notice">
            <PartialSuccessBanner recommendationError={result.recommendation_error} />
          </section>
        )}
        {isScenarioUnavailable && (
          <section aria-label="Scenario Unavailable Notice">
            <ScenarioUnavailableBanner scenarioError={result.scenario_error} />
          </section>
        )}
        {isResilienceUnavailable && (
          <section aria-label="Resilience Evaluation Notice">
            <ResilienceUnavailableBanner resilienceError={result.resilience_error} />
          </section>
        )}

        {/* Inconsistent State Fallbacks */}
        {isRecommendationInconsistent && (
          <div
            role="alert"
            className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-5 text-xs text-amber-200 space-y-2 print:bg-zinc-50 print:border-zinc-300 print:text-black"
          >
            <div className="flex items-center gap-2 font-semibold text-amber-300 print:text-black">
              <span className="h-2 w-2 rounded-full bg-amber-400" />
              Inconsistent Recommendation State Detected
            </div>
            <p className="leading-relaxed">
              The analysis service reported that Stage 4 completed, but the recommendation payload was missing from the response.
            </p>
          </div>
        )}

        {isScenarioInconsistent && (
          <div
            role="alert"
            className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-5 text-xs text-amber-200 space-y-2 print:bg-zinc-50 print:border-zinc-300 print:text-black"
          >
            <div className="flex items-center gap-2 font-semibold text-amber-300 print:text-black">
              <span className="h-2 w-2 rounded-full bg-amber-400" />
              Inconsistent Scenario State Detected
            </div>
            <p className="leading-relaxed">
              The analysis service reported that Stage 5 completed, but the scenarios payload was missing from the response.
            </p>
          </div>
        )}

        {isResilienceInconsistent && (
          <div
            role="alert"
            className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-5 text-xs text-amber-200 space-y-2 print:bg-zinc-50 print:border-zinc-300 print:text-black"
          >
            <div className="flex items-center gap-2 font-semibold text-amber-300 print:text-black">
              <span className="h-2 w-2 rounded-full bg-amber-400" />
              Inconsistent Resilience State Detected
            </div>
            <p className="leading-relaxed">
              The analysis service reported that Stage 6 completed, but the resilience report payload was missing from the response.
            </p>
          </div>
        )}
      </div>

      {/* 2. Primary Four-View Visual Decision Dashboard */}
      <VisualDecisionDashboard
        result={result}
        onReset={onReset}
        ownerId={effectiveOwnerId}
      />
    </div>
  );
}
