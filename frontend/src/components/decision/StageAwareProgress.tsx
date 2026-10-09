"use client";

import React from "react";
import type { JobStatus, PipelineStage } from "@/types";

interface StageAwareProgressProps {
  status: JobStatus | null;
  stage: PipelineStage | null;
  progressMessage?: string | null;
  jobId?: string | null;
  error?: string | null;
  errorStatusCode?: number | null;
  onRetry?: () => void;
}

interface StageStep {
  key: PipelineStage;
  label: string;
  description: string;
}

const STAGES: StageStep[] = [
  {
    key: "queued",
    label: "Queued",
    description: "Waiting for an execution worker in bounded pool",
  },
  {
    key: "stage1_decision_framer",
    label: "Understanding your decision",
    description: "Structuring problem, objectives, and constraints",
  },
  {
    key: "stage2_evidence_engine",
    label: "Gathering and evaluating evidence",
    description: "Retrieving sources, mapping findings, and identifying gaps",
  },
  {
    key: "stage3_ai_boardroom",
    label: "Convening the AI Boardroom",
    description: "Evaluating across Growth, Finance, Customer, and Risk",
  },
  {
    key: "completed",
    label: "Complete",
    description: "Validated analysis report assembled",
  },
];

const STAGE_ORDER: Record<string, number> = {
  queued: 0,
  stage1_decision_framer: 1,
  stage2_evidence_engine: 2,
  stage3_ai_boardroom: 3,
  completed: 4,
};

export function StageAwareProgress({
  status,
  stage,
  progressMessage,
  jobId,
  error,
  errorStatusCode,
  onRetry,
}: StageAwareProgressProps) {
  const isError = status === "failed" || status === "timed_out" || Boolean(error);
  const currentStageIndex = stage ? (STAGE_ORDER[stage] ?? 0) : 0;

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-2xl border border-zinc-800/90 bg-zinc-950/80 p-5 sm:p-6 text-zinc-100 shadow-md space-y-6"
    >
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80">
        <div className="flex items-center gap-2.5">
          {isError ? (
            <span className="flex h-3 w-3 rounded-full bg-red-400" />
          ) : (
            <span className="flex h-3 w-3 rounded-full bg-indigo-400 animate-ping" />
          )}
          <h3 className="text-sm font-semibold text-zinc-100 tracking-tight">
            {isError
              ? status === "timed_out"
                ? "Analysis Timed Out"
                : "Analysis Interrupted"
              : "Analysis in Progress"}
          </h3>
        </div>

        {jobId && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-zinc-400">Job:</span>
            <code className="text-[11px] font-mono text-zinc-300 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800 break-all">
              {jobId}
            </code>
          </div>
        )}
      </div>

      {/* Error Presentation */}
      {isError && (
        <div className="rounded-xl border border-red-800/60 bg-red-950/30 p-4 text-xs text-red-200 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-red-300 text-sm">
                {status === "timed_out" ? "Processing Deadline Exceeded" : "Execution Error"}
                {errorStatusCode && ` (HTTP ${errorStatusCode})`}
              </p>
              <p className="text-red-300/90 leading-relaxed mt-1 font-sans">
                {error ||
                  (status === "timed_out"
                    ? "The decision analysis exceeded the allowed time ceiling. Try refining your question."
                    : "The analysis engine encountered an unexpected error.")}
              </p>
            </div>
          </div>

          {onRetry && (
            <div className="pt-2">
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center justify-center rounded-lg bg-red-800/80 hover:bg-red-700 px-4 py-2 text-xs font-semibold text-white transition-colors cursor-pointer shadow-sm"
              >
                Retry Analysis
              </button>
            </div>
          )}
        </div>
      )}

      {/* Stage Progression Timeline */}
      {!isError && (
        <div className="space-y-4">
          <ol className="space-y-3">
            {STAGES.map((step, idx) => {
              const isPast = idx < currentStageIndex;
              const isCurrent = idx === currentStageIndex;
              const isPending = idx > currentStageIndex;

              return (
                <li
                  key={step.key}
                  className={`flex items-start gap-3.5 transition-opacity ${
                    isPending ? "opacity-40" : "opacity-100"
                  }`}
                >
                  {/* Step Status Indicator */}
                  <div className="mt-0.5 shrink-0">
                    {isPast && (
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                        <svg
                          className="h-3 w-3"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth="3"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      </span>
                    )}

                    {isCurrent && (
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500/20 border border-indigo-400">
                        <svg
                          className="animate-spin h-3 w-3 text-indigo-400"
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
                      </span>
                    )}

                    {isPending && (
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-zinc-900 border border-zinc-800">
                        <span className="h-1.5 w-1.5 rounded-full bg-zinc-600" />
                      </span>
                    )}
                  </div>

                  {/* Step Label & Subtitle */}
                  <div className="space-y-0.5">
                    <p
                      className={`text-xs sm:text-sm font-medium ${
                        isCurrent
                          ? "text-indigo-300 font-semibold"
                          : isPast
                          ? "text-zinc-200"
                          : "text-zinc-400"
                      }`}
                    >
                      {step.label}
                    </p>
                    <p className="text-[11px] text-zinc-400 leading-normal font-sans">
                      {step.description}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>

          {/* Contextual Progress Message */}
          {progressMessage && (
            <div className="pt-3 border-t border-zinc-900 text-[11px] text-zinc-400 font-mono">
              Status: {progressMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
