"use client";

import React from "react";
import type { SimulationExplanationResponse } from "@/types";

interface SimulationAIExplanationProps {
  simulationId: string;
  explanation: SimulationExplanationResponse | null;
  isExplaining: boolean;
  explanationError: string | null;
  onRequestExplanation: () => void;
}

export function SimulationAIExplanation({
  simulationId,
  explanation,
  isExplaining,
  explanationError,
  onRequestExplanation,
}: SimulationAIExplanationProps) {
  return (
    <div
      id="simulation-ai-explanation-panel"
      data-simulation-id={simulationId}
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-5 print:bg-white print:border-zinc-300 print:text-black print:p-3 print:break-inside-avoid"
      aria-labelledby="simulation-ai-explanation-title"
    >
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <div className="flex items-center gap-2">
            <h4
              id="simulation-ai-explanation-title"
              className="text-xs font-semibold uppercase tracking-wider text-violet-400 print:text-black flex items-center gap-1.5"
            >
              <span aria-hidden="true" className="text-sm">✦</span>
              AI Qualitative Explanation & Epistemic Boundaries
            </h4>
            <span className="inline-flex items-center rounded-full bg-violet-950/70 border border-violet-800/60 px-2 py-0.5 text-[10px] font-medium text-violet-300 print:border-zinc-400 print:bg-zinc-100 print:text-black">
              AI-Interpreted (Non-Deterministic)
            </span>
          </div>
          <p className="text-[11px] text-zinc-400 print:text-zinc-600 mt-1 max-w-2xl">
            Grounded narrative explaining operational impacts, constraint boundaries, and modeling limitations.
            The deterministic engine calculations above remain authoritative.
          </p>
        </div>

        {explanation && (
          <div className="flex items-center gap-2 self-start sm:self-auto text-[11px] font-mono text-zinc-400 print:text-zinc-700">
            <span
              className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono font-medium ${
                explanation.generation_status === "cached"
                  ? "bg-zinc-800/80 text-zinc-300 border border-zinc-700"
                  : "bg-emerald-950/60 text-emerald-300 border border-emerald-800/50"
              } print:border-zinc-400 print:bg-zinc-100 print:text-black`}
            >
              {explanation.generation_status === "cached" ? "Cached Synthesis" : "Freshly Generated"}
            </span>
            {explanation.model_name && (
              <span className="hidden md:inline-block text-zinc-500 font-mono text-[10px]">
                {explanation.model_name}
              </span>
            )}
          </div>
        )}
      </div>

      {/* State 1: Error State with Retry Button */}
      {explanationError && (
        <div
          role="alert"
          className="rounded-lg border border-rose-900/50 bg-rose-950/20 p-4 space-y-3 print:border-rose-400 print:bg-white"
        >
          <div className="flex items-start gap-3">
            <span className="text-rose-400 text-base" aria-hidden="true">⚠</span>
            <div className="space-y-1">
              <h5 className="text-xs font-semibold text-rose-300 print:text-rose-700">
                Failed to Generate AI Explanation
              </h5>
              <p className="text-xs text-rose-300/80 print:text-zinc-700 font-mono">
                {explanationError}
              </p>
            </div>
          </div>
          <div className="flex justify-end print:hidden">
            <button
              id="retry-explanation-btn"
              type="button"
              onClick={onRequestExplanation}
              disabled={isExplaining}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-700/60 bg-rose-900/40 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-900/60 transition-colors focus:outline-none focus:ring-2 focus:ring-rose-500"
            >
              Retry Explanation
            </button>
          </div>
        </div>
      )}

      {/* State 2: Loading State */}
      {isExplaining && (
        <div
          role="status"
          aria-busy="true"
          className="rounded-lg border border-violet-900/40 bg-violet-950/10 p-6 flex flex-col items-center justify-center space-y-3 text-center print:bg-zinc-50"
        >
          <div className="relative w-8 h-8">
            <div className="w-8 h-8 rounded-full border-2 border-violet-500/20 border-t-violet-400 animate-spin" />
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-violet-200">
              Synthesizing Grounded Explanation with Gemini...
            </p>
            <p className="text-[11px] text-zinc-400">
              Analyzing adjusted parameters against operational constraints and scenario trajectories.
            </p>
          </div>
        </div>
      )}

      {/* State 3: Prompt to Request Explanation (Initial State) */}
      {!explanation && !isExplaining && !explanationError && (
        <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
          <div className="space-y-1">
            <h5 className="text-xs font-medium text-zinc-200">
              Need qualitative interpretation of these numerical results?
            </h5>
            <p className="text-[11px] text-zinc-400 max-w-xl">
              AURA can invoke Gemini on-demand to synthesize the strategic narrative, assess constraint margins,
              and highlight modeling limitations for this specific simulation.
            </p>
          </div>
          <button
            id="explain-simulation-btn"
            type="button"
            onClick={onRequestExplanation}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:from-violet-500 hover:to-indigo-500 transition-all focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2 focus:ring-offset-zinc-950 shrink-0"
          >
            <span aria-hidden="true">✦</span>
            Explain This Simulation
          </button>
        </div>
      )}

      {/* State 4: Successfully Loaded Explanation */}
      {explanation && !isExplaining && (
        <div className="space-y-5">
          {/* Executive Summary */}
          <div className="rounded-lg border border-violet-900/40 bg-violet-950/20 p-4 space-y-2 print:border-zinc-300 print:bg-zinc-50">
            <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-violet-400 print:text-black">
              Executive Summary
            </span>
            <p className="text-xs text-zinc-200 print:text-black leading-relaxed">
              {explanation.summary}
            </p>
          </div>

          {/* Grid: What Changed & Constraint Implications */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* What Changed */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-2.5 print:border-zinc-300 print:bg-white">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-zinc-400 print:text-black flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" aria-hidden="true" />
                What Changed
              </span>
              <ul className="space-y-1.5 list-disc list-inside text-xs text-zinc-300 print:text-zinc-800">
                {explanation.what_changed.map((item, idx) => (
                  <li key={idx} className="leading-snug">
                    <span className="text-zinc-300 print:text-black">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Constraint Implications */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-2.5 print:border-zinc-300 print:bg-white">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-amber-400 print:text-black flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" aria-hidden="true" />
                Constraint Implications & Margins
              </span>
              {explanation.constraint_implications.length > 0 ? (
                <ul className="space-y-1.5 list-disc list-inside text-xs text-zinc-300 print:text-zinc-800">
                  {explanation.constraint_implications.map((item, idx) => (
                    <li key={idx} className="leading-snug">
                      <span className="text-zinc-300 print:text-black">{item}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-zinc-500 italic">
                  No direct constraint threshold violations or safety margin reductions identified.
                </p>
              )}
            </div>
          </div>

          {/* Resilience Interpretation */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-2 print:border-zinc-300 print:bg-white">
            <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-emerald-400 print:text-black flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
              Resilience Interpretation
            </span>
            <p className="text-xs text-zinc-300 print:text-black leading-relaxed">
              {explanation.resilience_interpretation}
            </p>
          </div>

          {/* Grid: Limitations & Suggested Validation Steps */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Limitations */}
            <div className="rounded-lg border border-amber-900/30 bg-amber-950/10 p-4 space-y-2.5 print:border-zinc-300 print:bg-white">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-amber-300 print:text-black flex items-center gap-1.5">
                <span aria-hidden="true">⚠</span>
                Modeling Limitations & Caveats
              </span>
              <ul className="space-y-1.5 list-disc list-inside text-xs text-amber-200/90 print:text-zinc-800">
                {explanation.limitations.map((item, idx) => (
                  <li key={idx} className="leading-snug">
                    <span className="text-zinc-300 print:text-black">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Suggested Validation Steps */}
            <div className="rounded-lg border border-indigo-900/30 bg-indigo-950/10 p-4 space-y-2.5 print:border-zinc-300 print:bg-white">
              <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-indigo-300 print:text-black flex items-center gap-1.5">
                <span aria-hidden="true">✔</span>
                Suggested Empirical Validation Steps
              </span>
              <ul className="space-y-1.5 list-disc list-inside text-xs text-indigo-200/90 print:text-zinc-800">
                {explanation.suggested_validation_steps.map((item, idx) => (
                  <li key={idx} className="leading-snug">
                    <span className="text-zinc-300 print:text-black">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Authoritative Artifact References */}
          {explanation.evidence_or_artifact_references.length > 0 && (
            <div className="pt-2 border-t border-zinc-900 flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                Grounded Artifacts:
              </span>
              {explanation.evidence_or_artifact_references.map((ref, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center rounded bg-zinc-900 px-2 py-0.5 text-[10px] font-mono text-zinc-400 border border-zinc-800"
                >
                  {ref}
                </span>
              ))}
            </div>
          )}

          {/* Footer Controls */}
          <div className="flex justify-end pt-2 print:hidden">
            <button
              type="button"
              onClick={onRequestExplanation}
              disabled={isExplaining}
              className="text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1 underline underline-offset-4"
            >
              Regenerate Explanation
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
