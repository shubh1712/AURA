"use client";

import React from "react";
import { DecisionFormData, JobStatus, PipelineStage } from "@/types";
import { StageAwareProgress } from "./StageAwareProgress";

interface DecisionFormProps {
  formData: DecisionFormData;
  isLoading: boolean;
  jobStatus?: JobStatus | null;
  pipelineStage?: PipelineStage | null;
  progressMessage?: string | null;
  jobId?: string | null;
  validationError: string | null;
  apiError: string | null;
  apiErrorStatusCode?: number | null;
  onFieldChange: (field: keyof DecisionFormData, value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onReset: () => void;
  onClearError: () => void;
  onRetry?: () => void;
  onStop?: () => void;
}

export function DecisionForm({
  formData,
  isLoading,
  jobStatus,
  pipelineStage,
  progressMessage,
  jobId,
  validationError,
  apiError,
  apiErrorStatusCode,
  onFieldChange,
  onSubmit,
  onReset,
  onClearError,
  onRetry,
  onStop,
}: DecisionFormProps) {
  const isFormDirty =
    Boolean(formData.question.trim()) ||
    Boolean(formData.context.trim()) ||
    Boolean(formData.constraints.trim());

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      {/* Error State Callouts */}
      {validationError && (
        <div
          role="alert"
          className="rounded-lg border border-amber-800/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-200 flex items-start justify-between gap-3"
        >
          <div className="flex items-start gap-2.5">
            <span className="font-semibold text-amber-400 select-none">&bull;</span>
            <p className="leading-relaxed">{validationError}</p>
          </div>
          <button
            type="button"
            onClick={onClearError}
            className="text-amber-400 hover:text-amber-200 text-xs font-mono"
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {apiError && !jobStatus && (
        <div
          role="alert"
          className="rounded-lg border border-red-800/50 bg-red-950/30 p-4 text-xs text-red-200 space-y-1.5"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-red-300">
                {apiErrorStatusCode === 504
                  ? "503 — AI Service Temporarily Unavailable"
                  : "Analysis Error"}
              </span>
              {apiErrorStatusCode && apiErrorStatusCode !== 504 && (
                <span className="rounded bg-red-900/60 px-1.5 py-0.5 text-[10px] font-mono font-medium text-red-200 border border-red-800/60">
                  HTTP {apiErrorStatusCode}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={onClearError}
              className="text-red-400 hover:text-red-200 text-xs font-mono"
              aria-label="Dismiss error"
            >
              &times;
            </button>
          </div>
          <p className="text-red-300/90 leading-relaxed font-sans">
            {apiErrorStatusCode === 504
              ? "Gemini may be experiencing high traffic or taking longer than expected to respond. Your analysis couldn't be completed in time. Please try again shortly."
              : apiError}
          </p>
        </div>
      )}

      {/* 1. Large Question Input */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label
            htmlFor="decision-question"
            className="block text-sm font-medium text-zinc-200 tracking-tight"
          >
            What decision are you facing? <span className="text-zinc-500">*</span>
          </label>
          <span className="text-[11px] text-zinc-500 font-mono">Required</span>
        </div>
        <textarea
          id="decision-question"
          rows={3}
          disabled={isLoading}
          value={formData.question}
          onChange={(e) => onFieldChange("question", e.target.value)}
          placeholder="e.g., Should we migrate our core database architecture to a distributed cluster or optimize PostgreSQL with read replicas?"
          className="w-full rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 text-base sm:text-lg text-zinc-100 placeholder-zinc-500 focus:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400 transition-colors disabled:opacity-50 resize-y leading-relaxed font-sans"
        />
      </div>

      {/* 2. Optional Context Input */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label
            htmlFor="decision-context"
            className="block text-xs font-medium uppercase tracking-wider text-zinc-400"
          >
            Context <span className="text-zinc-500 font-normal lowercase">(optional)</span>
          </label>
        </div>
        <textarea
          id="decision-context"
          rows={3}
          disabled={isLoading}
          value={formData.context}
          onChange={(e) => onFieldChange("context", e.target.value)}
          placeholder="Provide background, scale metrics, current tech stack, affected teams, or timeline..."
          className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400 transition-colors disabled:opacity-50 resize-y leading-relaxed"
        />
      </div>

      {/* 3. Optional Constraints Input */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label
            htmlFor="decision-constraints"
            className="block text-xs font-medium uppercase tracking-wider text-zinc-400"
          >
            Constraints <span className="text-zinc-500 font-normal lowercase">(optional)</span>
          </label>
        </div>
        <textarea
          id="decision-constraints"
          rows={2}
          disabled={isLoading}
          value={formData.constraints}
          onChange={(e) => onFieldChange("constraints", e.target.value)}
          placeholder="Non-negotiable boundaries (e.g., Zero downtime migration, budget under $50k, completion by Q4)..."
          className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400 transition-colors disabled:opacity-50 resize-y leading-relaxed"
        />
      </div>

      {/* Form Action Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-3">
        <div className="flex items-center gap-3">
          {/* Analyze Decision button */}
          <button
            type="submit"
            disabled={isLoading || !formData.question.trim()}
            className="inline-flex items-center justify-center rounded-lg bg-zinc-100 px-5 py-2.5 text-sm font-semibold text-zinc-900 hover:bg-white active:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-sm min-w-[160px]"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg
                  className="animate-spin h-4 w-4 text-zinc-900"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
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
                <span>Analyzing Decision...</span>
              </span>
            ) : (
              "Analyze Decision"
            )}
          </button>

          {/* Stop Analyzing button during active processing */}
          {isLoading && onStop && (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-800/70 bg-rose-950/40 px-4 py-2.5 text-sm font-semibold text-rose-200 hover:bg-rose-900/60 hover:text-white transition-colors cursor-pointer shadow-sm active:scale-95"
              aria-label="Stop active analysis"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
              <span>Stop Analyzing</span>
            </button>
          )}

          {/* Reset button */}
          {isFormDirty && !isLoading && (
            <button
              type="button"
              onClick={onReset}
              className="rounded-lg border border-zinc-800 bg-transparent px-4 py-2.5 text-sm font-medium text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 transition-colors cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>

        <span className="text-xs text-zinc-400 sm:text-right flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
          <span>Autonomous 6-Stage Deliberation</span>
        </span>
      </div>

      {/* Stage-Aware Progress & Error Callout */}
      {(isLoading || jobStatus === "succeeded" || jobStatus === "failed" || jobStatus === "timed_out") && (
        <StageAwareProgress
          status={jobStatus ?? (isLoading ? "running" : null)}
          stage={pipelineStage ?? null}
          progressMessage={progressMessage}
          jobId={jobId}
          error={apiError}
          errorStatusCode={apiErrorStatusCode}
          onRetry={onRetry}
          onStop={onStop}
        />
      )}
    </form>
  );
}
