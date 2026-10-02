"use client";

import React, { useState } from "react";
import { AnalysisResponse } from "@/types";

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

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm">
      {/* Header with Title and Status */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-5 border-b border-zinc-800/80">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">
            Intake Confirmation
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Analysis Request Staged
          </h2>
        </div>

        <div className="flex items-center space-x-2.5">
          <span className="text-xs text-zinc-400">Status:</span>
          <span className="inline-flex items-center rounded-md border border-emerald-800/60 bg-emerald-950/40 px-2.5 py-1 text-xs font-mono font-medium text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mr-1.5" />
            {result.status}
          </span>
        </div>
      </div>

      {/* Structured Details */}
      <div className="space-y-5">
        {/* Analysis ID */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-zinc-400 mb-1.5">
            Analysis ID
          </label>
          <div className="flex items-center justify-between rounded-lg border border-zinc-800/90 bg-zinc-950/60 px-3.5 py-2.5">
            <span className="font-mono text-xs sm:text-sm text-zinc-300 break-all select-all">
              {result.analysis_id}
            </span>
            <button
              type="button"
              onClick={handleCopyId}
              className="ml-3 shrink-0 rounded px-2 py-1 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition-colors cursor-pointer border border-zinc-800"
              title="Copy Analysis ID"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>

        {/* Question */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-zinc-400 mb-1.5">
            Question
          </label>
          <div className="rounded-lg border border-zinc-800/90 bg-zinc-950/60 p-4 text-sm sm:text-base text-zinc-200 leading-relaxed break-words">
            {result.question}
          </div>
        </div>

        {/* Message */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-zinc-400 mb-1.5">
            Message
          </label>
          <div className="rounded-lg border border-zinc-800/70 bg-zinc-950/40 p-4 text-sm text-zinc-300 leading-relaxed font-sans">
            {result.message}
          </div>
        </div>
      </div>

      {/* Action Footer */}
      <div className="pt-4 border-t border-zinc-800/80 flex items-center justify-between">
        <span className="text-xs text-zinc-500">
          Staged in AURA Engine (FastAPI)
        </span>
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800/80 px-4 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-750 hover:text-white transition-colors cursor-pointer shadow-sm"
        >
          Analyze Another Decision
        </button>
      </div>
    </div>
  );
}
