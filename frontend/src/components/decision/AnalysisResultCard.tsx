"use client";

import React, { useState } from "react";
import type { AnalysisResponse } from "@/types";
import { DecisionModelSummary } from "./DecisionModelSummary";
import { EvidenceOverview } from "./evidence/EvidenceOverview";
import { RequirementList } from "./evidence/RequirementList";
import { EvidenceGapsSection } from "./evidence/EvidenceGapsSection";
import { SourceList } from "./evidence/SourceList";
import { ReasoningBoardSection } from "./boardroom/ReasoningBoardSection";
import {
  RecommendationDashboard,
  PartialSuccessBanner,
} from "./recommendation";

interface AnalysisResultCardProps {
  result: AnalysisResponse;
  onReset: () => void;
}

export function AnalysisResultCard({ result, onReset }: AnalysisResultCardProps) {
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

  const hasDecisionModel = Boolean(result.decision_model);
  const hasEvidencePackage = Boolean(result.evidence_package);
  const hasReasoningBoard = Boolean(result.reasoning_board);

  // Analysis result state evaluation
  const isPartialSuccess =
    result.status === "partial_success" ||
    (result.recommendation_status === "unavailable" && !result.recommendation);

  const hasValidRecommendation = Boolean(result.recommendation);

  const isInconsistent =
    result.recommendation_status === "completed" && !result.recommendation;

  const isHistorical =
    !hasValidRecommendation &&
    !result.recommendation_status &&
    result.status === "completed";

  return (
    <div className="space-y-8 print:space-y-6">
      {/* 1. Analysis Metadata Card */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:bg-white print:border-zinc-300 print:text-black">
        {/* Header with Title and Status */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
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

        {/* Structured Details */}
        <div className="space-y-4">
          {/* Analysis ID */}
          <div>
            <label className="block text-xs font-medium uppercase tracking-wider text-zinc-400 print:text-zinc-600 mb-1.5">
              Analysis ID
            </label>
            <div className="flex items-center justify-between rounded-lg border border-zinc-800/90 bg-zinc-950/60 px-3.5 py-2.5 print:bg-zinc-50 print:border-zinc-300">
              <span className="font-mono text-xs sm:text-sm text-zinc-300 print:text-black break-all select-all">
                {result.analysis_id}
              </span>
              <button
                type="button"
                onClick={handleCopyId}
                className="ml-3 shrink-0 rounded px-2.5 py-1 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition-colors cursor-pointer border border-zinc-800 print:hidden"
                title="Copy Analysis ID"
                aria-label="Copy analysis ID to clipboard"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>

          {/* Question */}
          <div>
            <label className="block text-xs font-medium uppercase tracking-wider text-zinc-400 print:text-zinc-600 mb-1.5">
              Decision Question
            </label>
            <div className="rounded-lg border border-zinc-800/90 bg-zinc-950/60 p-4 text-sm sm:text-base text-zinc-200 print:text-black print:bg-zinc-50 print:border-zinc-300 leading-relaxed break-words font-medium">
              {result.question}
            </div>
          </div>

          {/* Message / Synthesis */}
          {result.message && (
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-zinc-400 print:text-zinc-600 mb-1.5">
                Executive Synthesis
              </label>
              <div className="rounded-lg border border-zinc-800/70 bg-zinc-950/40 p-4 text-sm text-zinc-300 print:text-zinc-900 print:bg-zinc-50 print:border-zinc-300 leading-relaxed font-sans">
                {result.message}
              </div>
            </div>
          )}
        </div>

        {/* Quick Actions Footer */}
        <div className="pt-4 border-t border-zinc-800/80 print:border-zinc-300 flex items-center justify-between print:hidden">
          <span className="text-xs text-zinc-500 font-mono">
            AURA Decision Intelligence Engine
          </span>
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800/80 px-4 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm"
          >
            Analyze Another Decision
          </button>
        </div>
      </div>

      {/* 2. Executive Recommendation Dashboard (Stage 4) */}
      {hasValidRecommendation && result.recommendation && (
        <section aria-label="Executive Recommendation">
          <RecommendationDashboard
            recommendation={result.recommendation}
            decisionModel={result.decision_model}
            evidencePackage={result.evidence_package}
            reasoningBoard={result.reasoning_board}
          />
        </section>
      )}

      {/* 2b. Partial Success Banner (Stage 4 Failed while Stages 1-3 Succeeded) */}
      {isPartialSuccess && (
        <section aria-label="Partial Analysis Notice">
          <PartialSuccessBanner
            recommendationError={result.recommendation_error}
          />
        </section>
      )}

      {/* 2c. Unexpected Inconsistent Data Fallback */}
      {isInconsistent && (
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
            The structured decision model, evidence package, and boardroom deliberation remain intact and accessible below.
          </p>
        </div>
      )}

      {/* 2d. Historical Day 4 Analysis Note (Only rendered if user needs clarification, but no error or failure message) */}
      {isHistorical && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 text-xs text-zinc-400 flex items-center justify-between print:hidden">
          <span>
            Historical Day 4 Analysis: Stages 1–3 Deliberation Report loaded.
          </span>
          <span className="text-[11px] font-mono text-zinc-500">
            Legacy Mode
          </span>
        </div>
      )}

      {/* 3. Structured Decision Model Summary */}
      {hasDecisionModel && result.decision_model && (
        <section aria-label="Decision Model" id="section-decision-model">
          <DecisionModelSummary model={result.decision_model} />
        </section>
      )}

      {/* 4. Evidence Package: Overview, Requirements, Gaps, Sources */}
      {hasEvidencePackage && result.evidence_package && (
        <div className="space-y-8" id="section-evidence-engine">
          {/* Evidence Overview Metrics */}
          <section aria-label="Evidence Overview">
            <EvidenceOverview pkg={result.evidence_package} />
          </section>

          {/* Requirement-Oriented Evidence List (includes Entity-Level Evidence section) */}
          <section aria-label="Evidence Requirements" id="section-evidence-requirements">
            <RequirementList pkg={result.evidence_package} />
          </section>

          {/* Evidence Gaps */}
          {result.evidence_package.gaps && result.evidence_package.gaps.length > 0 && (
            <section aria-label="Evidence Gaps" id="section-evidence-gaps">
              <EvidenceGapsSection
                gaps={result.evidence_package.gaps}
                items={result.evidence_package.items}
              />
            </section>
          )}

          {/* Source Provenance Directory */}
          {result.evidence_package.sources && result.evidence_package.sources.length > 0 && (
            <section aria-label="Source Directory" id="section-source-directory">
              <SourceList sources={result.evidence_package.sources} />
            </section>
          )}
        </div>
      )}

      {/* 5. AI Boardroom Deliberation */}
      {hasReasoningBoard && result.reasoning_board && (
        <section aria-label="AI Boardroom Deliberation" id="section-ai-boardroom">
          <ReasoningBoardSection
            board={result.reasoning_board}
            evidencePackage={result.evidence_package}
            decisionModel={result.decision_model}
          />
        </section>
      )}

      {/* Fallback note if model, evidence, and board are all missing */}
      {!hasDecisionModel && !hasEvidencePackage && !hasReasoningBoard && !hasValidRecommendation && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 text-center text-xs text-zinc-500">
          No structured decision model, evidence package, or boardroom deliberation was returned for this analysis.
        </div>
      )}

      {/* Bottom Action Footer */}
      <div className="flex justify-center gap-3 pt-2 pb-6 print:hidden">
        <button
          type="button"
          onClick={handlePrint}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800 px-5 py-2.5 text-sm font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm"
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
          className="inline-flex items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800 px-6 py-2.5 text-sm font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm"
        >
          &larr; Analyze Another Decision
        </button>
      </div>
    </div>
  );
}
