"use client";

import React from "react";
import { Header } from "@/components/common/Header";
import { DecisionHero } from "@/components/decision/DecisionHero";
import { DecisionForm } from "@/components/decision/DecisionForm";
import { AnalysisResultCard } from "@/components/decision/AnalysisResultCard";
import { useDecisionAnalysis } from "@/hooks";

export default function AuraPage() {
  const {
    formData,
    isLoading,
    isRestoring,
    restorationError,
    jobId,
    jobStatus,
    pipelineStage,
    progressMessage,
    validationError,
    apiError,
    apiErrorStatusCode,
    apiResponse,
    updateField,
    reset,
    clearError,
    submitAnalysis,
    stopAnalysis,
    retryRestoration,
  } = useDecisionAnalysis();

  const [isFormExpanded, setIsFormExpanded] = React.useState<boolean>(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitAnalysis();
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-950 text-zinc-100 selection:bg-zinc-800 selection:text-white">
      {/* Top Navigation */}
      <Header />

      {/* Main Workspace Area: 1536px on large desktops, centered with responsive horizontal padding */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10 space-y-8">
        {/* 1 & 2: AURA Logo/Name & Short Description */}
        <div className={apiResponse ? "w-full" : "max-w-4xl mx-auto"}>
          <DecisionHero />
        </div>

        {/* Session Restoration Loading State */}
        {isRestoring ? (
          <div
            role="status"
            aria-live="polite"
            className="max-w-4xl mx-auto rounded-2xl border border-zinc-800/80 bg-zinc-900/30 p-8 sm:p-10 text-center backdrop-blur-sm shadow-sm space-y-4"
          >
            <div className="flex items-center justify-center space-x-3 text-emerald-400">
              <svg
                className="animate-spin h-5 w-5 text-emerald-400"
                viewBox="0 0 24 24"
                fill="none"
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
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>
              <span className="font-medium text-sm text-zinc-200">
                Restoring your previous analysis&hellip;
              </span>
            </div>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              Reconnecting to AURA engine and retrieving verified decision artifacts.
            </p>
          </div>
        ) : restorationError ? (
          /* Session Restoration Notice / Error State */
          <div
            role="alert"
            className="max-w-4xl mx-auto rounded-2xl border border-amber-900/40 bg-amber-950/20 p-6 space-y-4 text-zinc-200 shadow-sm"
          >
            <div className="flex items-start space-x-3">
              <span className="text-amber-400 text-lg leading-none select-none">&#9888;</span>
              <div>
                <h3 className="text-sm font-semibold text-amber-300">Previous Analysis Notice</h3>
                <p className="text-xs text-zinc-400 mt-1">{restorationError}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-3 pt-2">
              <button
                type="button"
                onClick={() => retryRestoration()}
                className="px-3.5 py-1.5 text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition-colors cursor-pointer"
              >
                Retry Connection
              </button>
              <button
                type="button"
                onClick={() => reset()}
                className="px-3.5 py-1.5 text-xs font-medium bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded-lg transition-colors cursor-pointer"
              >
                Start New Analysis
              </button>
            </div>
          </div>
        ) : apiResponse && !isLoading ? (
          /* Collapsible Decision Form (Summary Bar When Results Available) */
          isFormExpanded ? (
            <div className="w-full rounded-2xl border border-zinc-800/80 bg-zinc-900/30 p-6 sm:p-8 backdrop-blur-sm shadow-sm space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80">
                <span className="text-xs font-mono uppercase tracking-wider text-zinc-400 font-semibold">
                  Decision Inquiry &amp; Parameters
                </span>
                <button
                  type="button"
                  onClick={() => setIsFormExpanded(false)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs text-zinc-400 hover:text-white transition-colors cursor-pointer rounded hover:bg-zinc-800"
                  aria-label="Collapse decision parameters form"
                >
                  <span>▲ Collapse Form</span>
                </button>
              </div>
              <DecisionForm
                formData={formData}
                isLoading={isLoading}
                jobId={jobId}
                jobStatus={jobStatus}
                pipelineStage={pipelineStage}
                progressMessage={progressMessage}
                validationError={validationError}
                apiError={apiError}
                apiErrorStatusCode={apiErrorStatusCode}
                onFieldChange={updateField}
                onSubmit={handleSubmit}
                onReset={() => {
                  setIsFormExpanded(false);
                  reset();
                }}
                onClearError={clearError}
                onRetry={submitAnalysis}
                onStop={stopAnalysis}
              />
            </div>
          ) : (
            <div
              role="region"
              aria-label="Analyzed Decision Summary"
              className="w-full rounded-2xl border border-zinc-800/80 bg-zinc-900/40 p-4 sm:p-5 backdrop-blur-sm shadow-sm transition-all flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
            >
              <div className="space-y-1 min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold bg-emerald-950/60 border border-emerald-800/50 px-2 py-0.5 rounded">
                    Analyzed Decision
                  </span>
                  {formData.constraints && (
                    <span className="text-[10px] font-mono text-zinc-400 bg-zinc-800/60 px-2 py-0.5 rounded border border-zinc-700">
                      Constraints Specified
                    </span>
                  )}
                  {formData.context && (
                    <span className="text-[10px] font-mono text-zinc-400 bg-zinc-800/60 px-2 py-0.5 rounded border border-zinc-700">
                      Context Loaded
                    </span>
                  )}
                </div>
                <p className="text-sm sm:text-base font-semibold text-white tracking-tight truncate leading-snug">
                  &ldquo;{formData.question || apiResponse.question}&rdquo;
                </p>
              </div>

              <div className="flex items-center gap-2.5 shrink-0">
                <button
                  type="button"
                  onClick={() => setIsFormExpanded(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 hover:text-white text-zinc-200 transition-colors cursor-pointer shadow-sm"
                  aria-label="Edit Question"
                >
                  <svg className="h-3.5 w-3.5 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  <span>Edit Question</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setIsFormExpanded(false);
                    reset();
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 hover:text-white text-zinc-400 transition-colors cursor-pointer"
                  aria-label="New Analysis"
                >
                  <svg className="h-3.5 w-3.5 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                  </svg>
                  <span>New Analysis</span>
                </button>
              </div>
            </div>
          )
        ) : (
          /* Active Intake / Processing Decision Input Form */
          <div className="max-w-4xl mx-auto rounded-2xl border border-zinc-800/80 bg-zinc-900/30 p-6 sm:p-8 backdrop-blur-sm shadow-sm">
            <DecisionForm
              formData={formData}
              isLoading={isLoading}
              jobId={jobId}
              jobStatus={jobStatus}
              pipelineStage={pipelineStage}
              progressMessage={progressMessage}
              validationError={validationError}
              apiError={apiError}
              apiErrorStatusCode={apiErrorStatusCode}
              onFieldChange={updateField}
              onSubmit={handleSubmit}
              onReset={reset}
              onClearError={clearError}
              onRetry={submitAnalysis}
              onStop={stopAnalysis}
            />
          </div>
        )}

        {/* 9: Analysis Result Card (displayed once real FastAPI response returns or is restored) */}
        {!isRestoring && apiResponse && (
          <section aria-labelledby="analysis-result-title" className="w-full">
            <AnalysisResultCard result={apiResponse} onReset={reset} jobId={jobId} />
          </section>
        )}
      </main>

      {/* Minimal Footer */}
      <footer className="border-t border-zinc-900 py-6 text-center text-xs text-zinc-500 font-sans">
        AURA &mdash; Decision intelligence for complex choices.
      </footer>
    </div>
  );
}
