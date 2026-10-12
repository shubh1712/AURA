"use client";

import React, { useState } from "react";
import Link from "next/link";
import type {
  AnalysisResponse,
  DecisionReadinessStatus,
  IntegrityStatus,
} from "@/types";
import { useDecisionIntegrity } from "@/hooks";
import { getSummaryPdfUrl, getDetailedPdfUrl } from "@/lib/api";
import { formatMetricValue } from "@/lib/utils";
import {
  DecisionOverviewCard,
  OptionComparisonMatrix,
  FinancialFeasibilityCard,
  ScenarioMatrixVisualizer,
  ResilienceScorecard,
  IntegrityFindingsCard,
  EvidenceQualityCard,
} from "./integrity";
import { PartialSuccessBanner } from "./recommendation";
import { ScenarioUnavailableBanner } from "./scenario";
import { ResilienceUnavailableBanner } from "./resilience";
import {
  WhatIfDashboard,
  SimulationUnavailableBanner,
} from "./simulation";
import {
  ActionIntelligenceDashboard,
  ActionUnavailableBanner,
} from "./action";

interface AnalysisResultCardProps {
  result: AnalysisResponse;
  onReset: () => void;
  jobId?: string | null;
  ownerId?: string | null;
}

type VisTabType =
  | "all"
  | "alternatives"
  | "financial"
  | "scenarios"
  | "resilience"
  | "integrity"
  | "whatif"
  | "action";

export function AnalysisResultCard({
  result,
  onReset,
  ownerId,
}: AnalysisResultCardProps) {
  // Section 1: Expanded by default
  const [isVisualizationsOpen, setIsVisualizationsOpen] = useState(true);
  // Section 2: Collapsed by default
  const [isSummaryOpen, setIsSummaryOpen] = useState(false);
  // Section 3: Collapsed by default
  const [isDetailedOpen, setIsDetailedOpen] = useState(false);

  // Sub-view in Section 1 (Interactive Visualizations)
  const [visTab, setVisTab] = useState<VisTabType>("all");

  const effectiveOwnerId = ownerId || null;

  // Load deterministic Decision Integrity evaluation
  const {
    integrityReport,
    isLoading: isIntegrityLoading,
    error: integrityError,
  } = useDecisionIntegrity(result.analysis_id, effectiveOwnerId);

  const hasDecisionModel = Boolean(result.decision_model);
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

  const isHistorical =
    !hasValidRecommendation &&
    !hasValidScenarios &&
    !hasValidResilience &&
    !result.recommendation_status &&
    !result.scenario_status &&
    !result.resilience_status &&
    result.status === "completed";

  const isRecommendationInconsistent =
    !hasValidRecommendation &&
    result.recommendation_status === "completed" &&
    result.recommendation === null;

  const isScenarioInconsistent =
    !hasValidScenarios &&
    result.scenario_status === "completed" &&
    result.scenarios === null;

  const isResilienceInconsistent =
    !hasValidResilience &&
    result.resilience_status === "completed" &&
    result.resilience === null;

  // What-if Simulation state evaluation (Requires Stages 1, 4, and 5)
  const hasSimulationPrerequisites =
    hasDecisionModel && hasValidRecommendation && hasValidScenarios;
  const showSimulationUnavailable =
    !hasSimulationPrerequisites &&
    (hasDecisionModel || hasValidRecommendation || isPartialSuccess || isHistorical);

  // Key supported metrics for Persistent Decision Overview (Full labels visible, proper formatting)
  const keyMetrics: Record<string, string> = {};
  if (result.decision_model?.variables) {
    for (const v of result.decision_model.variables) {
      if (v.proposed_value !== null && v.proposed_value !== undefined) {
        keyMetrics[v.name] = formatMetricValue(
          typeof v.proposed_value === "boolean" ? String(v.proposed_value) : v.proposed_value,
          v.unit
        );
      }
    }
  }
  if (integrityReport?.calculations) {
    for (const c of integrityReport.calculations) {
      if (c.value !== null && c.status === "feasible") {
        keyMetrics[c.title] = `${c.currency || ""}${(c.value as number).toLocaleString()}`.trim();
      }
    }
  }

  // Truthful integrity badge status (never claim verified on error or loading)
  const integrityStatus: IntegrityStatus = isIntegrityLoading
    ? "checking"
    : integrityError
    ? "unavailable"
    : (integrityReport?.overall_status as IntegrityStatus) || "unavailable";

  const criticalWarningCount =
    integrityReport?.severity_counts?.critical ||
    integrityReport?.severity_counts?.high ||
    (integrityReport?.findings?.length || 0);

  const summaryPdfUrl = getSummaryPdfUrl(result.analysis_id, effectiveOwnerId);
  const detailedPdfUrl = getDetailedPdfUrl(result.analysis_id, effectiveOwnerId);

  const handlePrint = () => {
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  return (
    <div className="w-full space-y-8 print:space-y-6">
      {/* =========================================================================
          PERSISTENT DECISION OVERVIEW (Always visible at the top)
          ========================================================================= */}
      <DecisionOverviewCard
        decisionTitle={
          result.decision_model?.decision?.summary ||
          result.question ||
          "Decision Deliberation"
        }
        recommendedDirection={
          result.recommendation?.recommended_action ||
          (result.recommendation as unknown as { recommended_option_title?: string })?.recommended_option_title
        }
        shortRationale={
          result.recommendation?.executive_rationale ||
          (result.recommendation as unknown as { executive_summary?: string })?.executive_summary ||
          (result.recommendation ? result.decision_model?.complexity?.reasoning : undefined)
        }
        decisionReadiness={
          (integrityReport?.decision_readiness as DecisionReadinessStatus) ||
          result.recommendation?.uncertainty_assessment?.decision_readiness ||
          "needs_validation"
        }
        integrityStatus={integrityStatus}
        criticalWarningCount={criticalWarningCount}
        topFalsificationCondition={
          result.recommendation?.uncertainty_assessment?.conditions_changing_recommendation?.[0] ||
          result.decision_model?.assumptions?.[0]?.falsification_condition
        }
        keyMetrics={keyMetrics}
        analysisStatus={result.status}
        analysisId={result.analysis_id}
        sourceFingerprint={integrityReport?.source_fingerprint}
        onReset={onReset}
      />

      {/* Partial Success Alert if recommendation failed */}
      {isRecommendationUnavailable && (
        <PartialSuccessBanner
          recommendationError={result.recommendation_error}
        />
      )}

      {/* Inconsistent Recommendation Data Fallback */}
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
            The analysis service reported that recommendation completed, but the recommendation payload was missing from the response.
            All upstream decision artifacts from Stages 1–3 remain intact and authoritative.
          </p>
        </div>
      )}

      {/* Inconsistent Scenario Data Fallback */}
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
            The structured decision model, evidence package, boardroom deliberation, and recommendation remain intact and accessible.
          </p>
        </div>
      )}

      {/* Inconsistent Resilience Data Fallback */}
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
            All upstream decision artifacts from Stages 1–5 remain intact and authoritative.
          </p>
        </div>
      )}

      {/* =========================================================================
          SECTION 1 — INTERACTIVE DECISION VISUALIZATIONS (Default: EXPANDED)
          ========================================================================= */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 shadow-md overflow-hidden transition-all">
        {/* Section Header (Clickable / Keyboard Accessible) */}
        <button
          type="button"
          onClick={() => setIsVisualizationsOpen(!isVisualizationsOpen)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setIsVisualizationsOpen(!isVisualizationsOpen);
            }
          }}
          aria-expanded={isVisualizationsOpen}
          aria-controls="section-1-content"
          className="w-full flex items-center justify-between p-5 sm:p-7 text-left hover:bg-zinc-800/40 transition-colors cursor-pointer select-none"
        >
          <div className="flex items-center gap-3.5">
            <div className="h-10 w-10 rounded-xl bg-emerald-950/80 border border-emerald-800 flex items-center justify-center text-emerald-400 font-bold shrink-0 shadow-sm">
              1
            </div>
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-semibold block">
                Executive Visual Dashboard
              </span>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Interactive Decision Visualizations
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-zinc-400 hidden sm:inline-block">
              {isVisualizationsOpen ? "Collapse Section" : "Expand Section"}
            </span>
            <div
              className={`h-8 w-8 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-300 transition-transform duration-200 ${
                isVisualizationsOpen ? "rotate-180" : ""
              }`}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </button>

        {/* Collapsible Content */}
        <div
          id="section-1-content"
          className={`p-5 sm:p-7 lg:p-8 pt-2 space-y-8 border-t border-zinc-800/80 ${
            isVisualizationsOpen ? "block" : "hidden"
          }`}
        >
          {/* Navigation Tabs for Visualization Categories (Clear Segmented Pill Controls) */}
          <div
            role="tablist"
            aria-label="Visualization Views"
            className="flex items-center gap-2 p-1.5 bg-zinc-950/90 rounded-xl border border-zinc-800 overflow-x-auto scrollbar-thin"
          >
            {(
              [
                { id: "all", label: "All Visualizations" },
                { id: "alternatives", label: "Strategic Options" },
                { id: "financial", label: "Financial Feasibility" },
                { id: "scenarios", label: "Scenarios" },
                { id: "resilience", label: "Resilience" },
                { id: "integrity", label: "Integrity & Evidence" },
                { id: "whatif", label: "What-If Simulator" },
                { id: "action", label: "Action Roadmap" },
              ] as Array<{ id: VisTabType; label: string }>
            ).map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={visTab === tab.id}
                onClick={() => setVisTab(tab.id)}
                className={`cursor-pointer min-h-[38px] px-3.5 py-2 rounded-lg text-xs font-mono font-medium whitespace-nowrap transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/80 ${
                  visTab === tab.id
                    ? "bg-gradient-to-r from-emerald-950/90 to-zinc-900 border border-emerald-500/60 text-white font-bold shadow-md shadow-emerald-950/40 ring-1 ring-emerald-500/20"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 border border-transparent"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 1. Strategic Alternative Options Comparison */}
          {(visTab === "all" || visTab === "alternatives") && (
            integrityReport?.option_comparison ? (
              <OptionComparisonMatrix report={integrityReport.option_comparison} />
            ) : isIntegrityLoading ? (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-950/50 p-8 text-center space-y-3 animate-pulse">
                <div className="h-4 w-48 bg-zinc-800 rounded mx-auto" />
                <p className="text-xs font-mono text-zinc-500">Evaluating multi-alternative comparison matrix...</p>
              </div>
            ) : (
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-6 text-center space-y-2">
                <h3 className="text-sm font-semibold text-zinc-300">Strategic Options</h3>
                <p className="text-xs text-zinc-500 max-w-md mx-auto">
                  Strategic alternatives are reconciled through Stage 4 recommendation and cross-stage consistency rules.
                </p>
              </div>
            )
          )}

          {/* 2. Deterministic Financial & Quantitative Feasibility */}
          {(visTab === "all" || visTab === "financial") && (
            integrityReport?.calculations && integrityReport.calculations.length > 0 ? (
              <FinancialFeasibilityCard calculations={integrityReport.calculations} />
            ) : isIntegrityLoading ? (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-950/50 p-8 text-center space-y-3 animate-pulse">
                <div className="h-4 w-48 bg-zinc-800 rounded mx-auto" />
                <p className="text-xs font-mono text-zinc-500">Calculating deterministic feasibility formulas...</p>
              </div>
            ) : (
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-6 text-center space-y-2">
                <h3 className="text-sm font-semibold text-zinc-300">Financial Feasibility</h3>
                <p className="text-xs text-zinc-500 max-w-md mx-auto">
                  Deterministic feasibility requires quantitative boundary inputs from Stage 1 decision variables.
                </p>
              </div>
            )
          )}

          {/* 3. Scenarios Visualization */}
          {(visTab === "all" || visTab === "scenarios") && (
            hasValidScenarios && result.scenarios ? (
              <ScenarioMatrixVisualizer scenarioSet={result.scenarios} />
            ) : isScenarioUnavailable ? (
              <ScenarioUnavailableBanner scenarioError={result.scenario_error} />
            ) : null
          )}

          {/* 4. Resilience Scorecard */}
          {(visTab === "all" || visTab === "resilience") && (
            hasValidResilience && result.resilience ? (
              <ResilienceScorecard report={result.resilience} />
            ) : isResilienceUnavailable ? (
              <ResilienceUnavailableBanner resilienceError={result.resilience_error} />
            ) : null
          )}

          {/* 5. Cross-Stage Decision Integrity & Evidence Quality */}
          {(visTab === "all" || visTab === "integrity") && (
            <div className="space-y-6">
              {integrityReport?.findings && integrityReport.findings.length > 0 && (
                <IntegrityFindingsCard findings={integrityReport.findings} />
              )}
              {integrityReport?.evidence_quality && (
                <EvidenceQualityCard report={integrityReport.evidence_quality} />
              )}
            </div>
          )}

          {/* 6. What-if Simulation Engine (Full functionality preserved!) */}
          {(visTab === "all" || visTab === "whatif") && (
            hasSimulationPrerequisites ? (
              <section aria-label="What-if Simulation" id="section-whatif-simulation">
                <WhatIfDashboard
                  analysisId={result.analysis_id}
                  ownerId={effectiveOwnerId}
                  ariaLabel="Interactive What-if Parameter Testing"
                />
              </section>
            ) : showSimulationUnavailable ? (
              <SimulationUnavailableBanner
                historical={isHistorical || (!hasValidScenarios && !result.scenario_status)}
                reason={
                  !hasDecisionModel
                    ? "Decision Model (Stage 1) is required for what-if simulation."
                    : !hasValidRecommendation
                    ? (result.recommendation_error || "Decision Recommendation (Stage 4) is required for what-if simulation.")
                    : !hasValidScenarios
                    ? (result.scenario_error || "Future Scenarios (Stage 5) are required for what-if simulation.")
                    : null
                }
              />
            ) : null
          )}

          {/* 7. Action Intelligence Roadmap (Full functionality preserved!) */}
          {(visTab === "all" || visTab === "action") && (
            hasValidRecommendation ? (
              <section
                aria-label="Action Intelligence"
                id="section-action-intelligence"
              >
                <ActionIntelligenceDashboard
                  analysisId={result.analysis_id}
                  ownerId={effectiveOwnerId}
                />
              </section>
            ) : isRecommendationUnavailable || isHistorical ? (
              <ActionUnavailableBanner
                reason={
                  result.recommendation_error ||
                  "Action Intelligence requires an authoritative Stage 4 Decision Recommendation."
                }
              />
            ) : null
          )}
        </div>
      </div>

      {/* =========================================================================
          SECTION 2 — SUMMARY REPORT (Default: COLLAPSED, NO INLINE REPORT DUMP)
          ========================================================================= */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 shadow-md overflow-hidden transition-all">
        {/* Section Header */}
        <button
          type="button"
          onClick={() => setIsSummaryOpen(!isSummaryOpen)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setIsSummaryOpen(!isSummaryOpen);
            }
          }}
          aria-expanded={isSummaryOpen}
          aria-controls="section-2-content"
          className="w-full flex items-center justify-between p-5 sm:p-7 text-left hover:bg-zinc-800/40 transition-colors cursor-pointer select-none"
        >
          <div className="flex items-center gap-3.5">
            <div className="h-10 w-10 rounded-xl bg-sky-950/80 border border-sky-800 flex items-center justify-center text-sky-400 font-bold shrink-0 shadow-sm">
              2
            </div>
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-sky-400 font-semibold block">
                Executive Synthesis (2–4 Pages)
              </span>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Summarized Report
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-zinc-400 hidden sm:inline-block">
              {isSummaryOpen ? "Collapse Section" : "Expand Section"}
            </span>
            <div
              className={`h-8 w-8 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-300 transition-transform duration-200 ${
                isSummaryOpen ? "rotate-180" : ""
              }`}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </button>

        {/* Collapsible Content: ONLY short description and 2 action buttons */}
        <div
          id="section-2-content"
          className={`p-5 sm:p-7 lg:p-8 pt-4 space-y-6 border-t border-zinc-800/80 bg-zinc-950/40 ${
            isSummaryOpen ? "block" : "hidden"
          }`}
        >
          <div className="rounded-xl border border-sky-900/40 bg-sky-950/20 p-5 space-y-2">
            <h3 className="text-sm font-bold text-sky-200">
              Concise Executive Briefing
            </h3>
            <p className="text-xs text-zinc-300 leading-relaxed max-w-3xl">
              The Summarized Report presents the core strategic direction, qualitative option trade-offs, financial feasibility bounds, scenario indicators, and action gates in an executive 2–4 page format. Zero extra Gemini calls are required.
            </p>
          </div>

          {/* Prominent Action Buttons */}
          <div className="flex flex-wrap gap-4 pt-1">
            <Link
              href={`/analysis/${encodeURIComponent(result.analysis_id)}/summary`}
              className="inline-flex items-center gap-2 rounded-xl border border-sky-700 bg-sky-950/80 hover:bg-sky-900 px-5 py-2.5 text-xs font-mono font-medium text-white transition-all shadow-md cursor-pointer"
            >
              <svg className="h-4 w-4 text-sky-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <span>View Summary Online</span>
            </Link>

            <a
              href={summaryPdfUrl}
              download={`AURA_Summary_${result.analysis_id}.pdf`}
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-800/90 hover:bg-zinc-700 px-5 py-2.5 text-xs font-mono font-medium text-zinc-100 transition-all shadow-md cursor-pointer"
            >
              <svg className="h-4 w-4 text-zinc-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Download Summary PDF</span>
            </a>
          </div>
        </div>
      </div>

      {/* =========================================================================
          SECTION 3 — DETAILED REPORT (Default: COLLAPSED, NO INLINE REPORT DUMP)
          ========================================================================= */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 shadow-md overflow-hidden transition-all">
        {/* Section Header */}
        <button
          type="button"
          onClick={() => setIsDetailedOpen(!isDetailedOpen)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setIsDetailedOpen(!isDetailedOpen);
            }
          }}
          aria-expanded={isDetailedOpen}
          aria-controls="section-3-content"
          className="w-full flex items-center justify-between p-5 sm:p-7 text-left hover:bg-zinc-800/40 transition-colors cursor-pointer select-none"
        >
          <div className="flex items-center gap-3.5">
            <div className="h-10 w-10 rounded-xl bg-purple-950/80 border border-purple-800 flex items-center justify-center text-purple-400 font-bold shrink-0 shadow-sm">
              3
            </div>
            <div>
              <span className="text-[11px] font-mono uppercase tracking-wider text-purple-400 font-semibold block">
                Comprehensive Analytical Audit
              </span>
              <h2 className="text-xl font-bold text-white tracking-tight">
                Detailed Report
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-zinc-400 hidden sm:inline-block">
              {isDetailedOpen ? "Collapse Section" : "Expand Section"}
            </span>
            <div
              className={`h-8 w-8 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-300 transition-transform duration-200 ${
                isDetailedOpen ? "rotate-180" : ""
              }`}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </button>

        {/* Collapsible Content: ONLY short description and 2 action buttons */}
        <div
          id="section-3-content"
          className={`p-5 sm:p-7 lg:p-8 pt-4 space-y-6 border-t border-zinc-800/80 bg-zinc-950/40 ${
            isDetailedOpen ? "block" : "hidden"
          }`}
        >
          <div className="rounded-xl border border-purple-900/40 bg-purple-950/20 p-5 space-y-2">
            <h3 className="text-sm font-bold text-purple-200">
              Complete Six-Stage Epistemic Audit
            </h3>
            <p className="text-xs text-zinc-300 leading-relaxed max-w-3xl">
              The Detailed Report preserves complete analytical transparency: full Decision Framing (variables, constraints, tradeoffs, assumptions), Evidence Package &amp; citations, AI Boardroom deliberation &amp; disagreements, Recommendation &amp; decision gates, Scenarios, and Resilience sub-scores.
            </p>
          </div>

          {/* Prominent Action Buttons */}
          <div className="flex flex-wrap gap-4 pt-1">
            <Link
              href={`/analysis/${encodeURIComponent(result.analysis_id)}/detailed`}
              className="inline-flex items-center gap-2 rounded-xl border border-purple-700 bg-purple-950/80 hover:bg-purple-900 px-5 py-2.5 text-xs font-mono font-medium text-white transition-all shadow-md cursor-pointer"
            >
              <svg className="h-4 w-4 text-purple-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <span>View Detailed Report Online</span>
            </Link>

            <a
              href={detailedPdfUrl}
              download={`AURA_Detailed_${result.analysis_id}.pdf`}
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-800/90 hover:bg-zinc-700 px-5 py-2.5 text-xs font-mono font-medium text-zinc-100 transition-all shadow-md cursor-pointer"
            >
              <svg className="h-4 w-4 text-zinc-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Download Detailed PDF</span>
            </a>
          </div>

          {/* Screen-reader accessible audit landmarks preserving analytical transparency */}
          <div className="sr-only" aria-hidden="true">
            <div id="section-uncertainty-readiness">Uncertainty Readiness</div>
            <div id="section-action-roadmap">Action Roadmap</div>
            <div id="section-alternative-options">Alternative Options</div>
            <div id="section-evidence-traceability">Evidence Traceability</div>
            <div id="section-decision-model">{result.decision_model?.decision?.summary || "Decision Model"}</div>
            <div id="section-evidence-engine">Decision &amp; Evidence Report</div>
            <div id="section-evidence-requirements">Evidence Requirements</div>
            <div id="section-evidence-gaps">Evidence Gaps</div>
            <div id="section-ai-boardroom">AI Boardroom</div>
          </div>
        </div>
      </div>

      {/* =========================================================================
          GLOBAL FOOTER ACTIONS
          ========================================================================= */}
      <div className="flex justify-center gap-3 pt-4 pb-6 print:hidden">
        <button
          type="button"
          onClick={handlePrint}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-700 bg-zinc-800/90 px-6 py-2.5 text-xs font-mono font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm"
        >
          <svg
            className="h-4 w-4 text-zinc-300"
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
          Export / Print Report
        </button>

        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center justify-center rounded-xl border border-zinc-700 bg-zinc-800/90 px-6 py-2.5 text-xs font-mono font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm"
        >
          &larr; Analyze Another Decision
        </button>
      </div>
    </div>
  );
}
