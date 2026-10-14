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
    retryRestoration,
  } = useDecisionAnalysis();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitAnalysis();
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-950 text-zinc-100 selection:bg-zinc-800 selection:text-white">
      {/* Top Navigation */}
      <Header />

      {/* Main Workspace Area: 1536px on large desktops, centered with responsive horizontal padding */}
      <main className="flex-1 w-full max-w-[1536px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 py-8 sm:py-12 space-y-8">
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
        ) : (
          /* Decision Input Form */
          <div className={`${apiResponse ? "w-full" : "max-w-4xl mx-auto"} rounded-2xl border border-zinc-800/80 bg-zinc-900/30 p-6 sm:p-8 backdrop-blur-sm shadow-sm`}>
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
