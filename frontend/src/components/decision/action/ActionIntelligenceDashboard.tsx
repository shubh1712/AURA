"use client";

import React, { useState } from "react";
import { useActionIntelligence } from "@/hooks/useActionIntelligence";
import { ActionStrategyOverview } from "./ActionStrategyOverview";
import { ActionIntelligenceRoadmapSection } from "./ActionRoadmapSection";
import { ActionDecisionGates } from "./ActionDecisionGates";
import { ActionValidationWarnings } from "./ActionValidationWarnings";
import { ActionUnresolvedQuestions } from "./ActionUnresolvedQuestions";

interface ActionIntelligenceDashboardProps {
  analysisId: string;
  ownerId?: string | null;
  enabled?: boolean;
}

export function ActionIntelligenceDashboard({
  analysisId,
  ownerId,
  enabled = true,
}: ActionIntelligenceDashboardProps) {
  const {
    plan,
    status,
    isLoading,
    isGenerating,
    isPolling,
    isPollingTimeout,
    cached,
    error,
    errorStatusCode,
    warnings,
    generate,
    refreshStatus,
    clearError,
  } = useActionIntelligence(analysisId, enabled, ownerId);

  const [confirmRegenerate, setConfirmRegenerate] = useState(false);

  const handleGenerateClick = async () => {
    await generate(false);
  };

  const handleRegenerateClick = async () => {
    setConfirmRegenerate(false);
    await generate(true);
  };

  const isBusy = isGenerating || isPolling || isLoading;

  return (
    <section
      id="section-action-intelligence"
      aria-label="Action Intelligence"
      className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:border-zinc-300 print:bg-white print:text-black"
    >
      {/* 1. Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-zinc-800/80 pb-5 print:border-zinc-200">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider font-semibold text-indigo-400 print:text-zinc-700">
              Stage 4 Operationalization
            </span>
            <span className="inline-flex items-center rounded-md border border-indigo-800/60 bg-indigo-950/40 px-2 py-0.5 text-[10px] font-mono font-medium text-indigo-300 print:border-zinc-300 print:bg-zinc-100 print:text-black">
              Gemini Powered
            </span>
          </div>
          <h2 className="text-xl font-semibold text-white print:text-black tracking-tight mt-1">
            Action Intelligence
          </h2>
        </div>

        {/* Action Controls for Ready State */}
        {status === "ready" && (
          <div className="flex items-center gap-3 print:hidden">
            {confirmRegenerate ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-400">Regenerate?</span>
                <button
                  type="button"
                  onClick={handleRegenerateClick}
                  disabled={isBusy}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 cursor-pointer disabled:opacity-50 transition-colors shadow-sm"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRegenerate(false)}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 cursor-pointer transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                id="regenerate-action-plan-btn"
                onClick={() => setConfirmRegenerate(true)}
                disabled={isBusy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800/90 px-3.5 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer shadow-sm disabled:opacity-50"
              >
                <svg
                  className="h-3.5 w-3.5 text-zinc-400"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H4.5a.75.75 0 00-.75.75v3.733a.75.75 0 001.5 0v-2.07l.394.393a7 7 0 1010.597-4.103.75.75 0 10-1.429.462z"
                    clipRule="evenodd"
                  />
                </svg>
                Regenerate Roadmap
              </button>
            )}
          </div>
        )}
      </div>

      {/* 2. Initial Not-Generated State */}
      {status === "not_generated" && !isBusy && (
        <div
          id="action-plan-empty-state"
          className="rounded-xl border border-dashed border-zinc-800 bg-zinc-950/40 p-6 sm:p-8 text-center space-y-4 print:hidden"
        >
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-950/50 border border-indigo-800/40 text-indigo-400">
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="1.75"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m8.9-4.5c.376.023.75.05 1.124.08 1.131.094 1.976 1.057 1.976 2.192V19.5A2.25 2.25 0 0118 21.75H6a2.25 2.25 0 01-2.25-2.25V6.108c0-1.135.845-2.098 1.976-2.192.373-.03.748-.057 1.124-.08"
              />
            </svg>
          </div>

          <div className="max-w-md mx-auto space-y-1.5">
            <h3 className="text-base font-semibold text-white tracking-tight">
              Operationalize Decision Recommendation
            </h3>
            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              Transform Stage 4 recommended strategy into a grounded, prioritized execution roadmap with responsible roles, sequenced steps, decision gates, and rollback criteria.
            </p>
          </div>

          <div className="pt-2">
            <button
              type="button"
              id="generate-action-plan-btn"
              onClick={handleGenerateClick}
              disabled={isBusy}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 cursor-pointer disabled:opacity-50 transition-colors"
            >
              <svg
                className="h-4 w-4 text-indigo-200"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M15.98 1.804a1 1 0 00-1.96 0l-.24 1.192a8.001 8.001 0 00-4.576 4.576l-1.192.24a1 1 0 000 1.96l1.192.24a8.001 8.001 0 004.576 4.576l.24 1.192a1 1 0 001.96 0l.24-1.192a8.001 8.001 0 004.576-4.576l1.192-.24a1 1 0 000-1.96l-1.192-.24a8.001 8.001 0 00-4.576-4.576l-.24-1.192zM6.91 10.91a1 1 0 00-1.82 0l-.133.53a4 4 0 00-2.517 2.517l-.53.133a1 1 0 000 1.82l.53.133a4 4 0 002.517 2.517l.133.53a1 1 0 001.82 0l.133-.53a4 4 0 002.517-2.517l.53-.133a1 1 0 000-1.82l-.53-.133a4 4 0 00-2.517-2.517l-.133-.53z" />
              </svg>
              Generate Action Plan
            </button>
          </div>

          <div className="text-[11px] font-mono text-zinc-500 max-w-sm mx-auto">
            Grounded generation utilizes Google Cloud Vertex AI / Gemini. Processing typically takes 15–30 seconds.
          </div>
        </div>
      )}

      {/* 3. Running / Loading State */}
      {(status === "running" || isBusy) && !isPollingTimeout && status !== "ready" && (
        <div
          id="action-plan-loading-state"
          role="status"
          className="rounded-xl border border-indigo-900/40 bg-indigo-950/15 p-8 text-center space-y-4 print:hidden"
        >
          <div className="mx-auto flex h-10 w-10 items-center justify-center">
            <svg
              className="h-8 w-8 animate-spin text-indigo-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>

          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-white tracking-tight">
              Synthesizing Grounded Execution Roadmap...
            </h3>
            <p className="text-xs text-indigo-300/80">
              {isPolling
                ? "Generation running in background. Polling status endpoint..."
                : "Invoking Gemini structured extraction with upstream decision artifacts..."}
            </p>
          </div>

          <div className="text-[11px] font-mono text-zinc-500">
            Enforcing strict zero-hallucination checks and Stage 4 action grounding.
          </div>
        </div>
      )}

      {/* 3b. Polling Timeout State (Generation In Progress, Client Polling Paused) */}
      {isPollingTimeout && status !== "ready" && (
        <div
          id="action-plan-polling-timeout-state"
          role="status"
          className="rounded-xl border border-amber-900/60 bg-amber-950/20 p-6 space-y-4 text-xs text-amber-200 print:border-zinc-300 print:bg-zinc-50 print:text-black"
        >
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
            <h4 className="text-sm font-semibold text-amber-300 print:text-black">
              Generation In Progress (Client Polling Paused)
            </h4>
          </div>

          <p className="leading-relaxed text-zinc-300 print:text-black">
            Action plan generation is taking longer than usual on the server. The backend has not reported a failure. Click Check Status or refresh the page to see if your roadmap is ready.
          </p>

          <div className="flex items-center gap-3 pt-2 print:hidden">
            <button
              type="button"
              id="check-action-plan-status-btn"
              onClick={refreshStatus}
              disabled={isBusy}
              className="rounded-lg bg-amber-700 hover:bg-amber-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors cursor-pointer disabled:opacity-50"
            >
              Check Status Now
            </button>
            <button
              type="button"
              id="retry-action-plan-polling-btn"
              onClick={handleGenerateClick}
              disabled={isBusy}
              className="text-xs font-mono text-zinc-400 hover:text-zinc-200 underline cursor-pointer"
            >
              Restart Generation
            </button>
          </div>
        </div>
      )}

      {/* 4. Failure State */}
      {status === "failed" && (
        <div
          id="action-plan-error-state"
          role="alert"
          className="rounded-xl border border-rose-900/60 bg-rose-950/20 p-6 space-y-4 text-xs text-rose-200 print:border-zinc-300 print:bg-zinc-50 print:text-black"
        >
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-rose-400" />
            <h4 className="text-sm font-semibold text-rose-300 print:text-black">
              Action Plan Generation Failed
            </h4>
            {errorStatusCode && (
              <span className="font-mono text-[10px] text-rose-400">
                (Status: {errorStatusCode})
              </span>
            )}
          </div>

          <p className="leading-relaxed text-zinc-300 print:text-black">
            {error || "An unexpected error occurred during action plan generation."}
          </p>

          <div className="flex items-center gap-3 pt-2 print:hidden">
            <button
              type="button"
              id="retry-action-plan-btn"
              onClick={handleGenerateClick}
              disabled={isBusy}
              className="rounded-lg bg-rose-700 hover:bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors cursor-pointer disabled:opacity-50"
            >
              Retry Generation
            </button>
            <button
              type="button"
              onClick={clearError}
              className="text-xs font-mono text-zinc-400 hover:text-zinc-200 underline cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* 5. Ready State: Complete Dashboard */}
      {status === "ready" && plan && (
        <div className="space-y-6">
          {/* Strategy Overview */}
          <ActionStrategyOverview plan={plan} cached={cached} />

          {/* Validation Warnings / Governance Notices */}
          {warnings.length > 0 && (
            <ActionValidationWarnings warnings={warnings} />
          )}

          {/* Prioritized Execution Roadmap */}
          <ActionIntelligenceRoadmapSection actions={plan.actions} />

          {/* Decision Gates */}
          <ActionDecisionGates
            decisionGates={plan.decision_gates}
            actions={plan.actions}
          />

          {/* Unresolved Questions & Limitations */}
          <ActionUnresolvedQuestions
            unresolvedQuestions={plan.unresolved_questions}
            limitations={plan.limitations}
          />
        </div>
      )}
    </section>
  );
}
