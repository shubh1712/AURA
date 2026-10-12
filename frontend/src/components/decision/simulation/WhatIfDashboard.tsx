"use client";

import React from "react";
import { useWhatIfSimulation } from "@/hooks/useWhatIfSimulation";
import { SimulationVariableControls } from "./SimulationVariableControls";
import { SimulationComparisonPanel } from "./SimulationComparisonPanel";
import { SimulationConstraintImpacts } from "./SimulationConstraintImpacts";
import { SimulationAIExplanation } from "./SimulationAIExplanation";
import { SimulationHistory } from "./SimulationHistory";

interface WhatIfDashboardProps {
  analysisId: string;
  ownerId?: string | null;
  ariaLabel?: string;
}

export function WhatIfDashboard({
  analysisId,
  ownerId,
  ariaLabel = "What-if Simulation",
}: WhatIfDashboardProps) {
  const {
    isLoadingDiscovery,
    discoveryError,
    discoveryErrorStatusCode,
    discovery,
    adjustments,
    rawInputs,
    inputErrors,
    hasChanges,
    isValid,
    isSimulating,
    simulationError,
    simulationErrorStatusCode,
    activeResult,
    history,
    isLoadingHistory,
    historyError,
    selectedSimulationId,
    explanation,
    isExplaining,
    explanationError,
    requestExplanation,
    setAdjustment,
    resetToBaseline,
    runSimulation,
    loadHistory,
    selectSavedSimulation,
    reloadDiscovery,
  } = useWhatIfSimulation(analysisId, true, ownerId);

  return (
    <section
      id="section-what-if-simulation"
      aria-label={ariaLabel}
      className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:bg-white print:border-zinc-300 print:text-black"
    >
      {/* 1. Header & Cognitive Framework Disclaimer */}
      <div className="space-y-4 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-wider font-semibold text-sky-400 print:text-zinc-700">
                Decision Laboratory
              </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono border border-sky-800/60 bg-sky-950/40 text-sky-300 print:hidden">
                Deterministic
              </span>
            </div>
            <h3 className="text-xl font-semibold text-white print:text-black tracking-tight mt-0.5">
              What-if Simulation Engine
            </h3>
          </div>

          {/* Status Badges */}
          <div className="flex items-center gap-2 flex-wrap">
            {discovery && (
              <span
                className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono border border-zinc-800 bg-zinc-950/60 text-zinc-400 print:border-zinc-300 print:bg-zinc-100 print:text-black"
                title={`Baseline Fingerprint: ${discovery.baseline_fingerprint}`}
              >
                <span className="text-zinc-500 mr-1.5">Baseline:</span>
                <span className="truncate max-w-[120px] sm:max-w-[160px]">
                  {discovery.baseline_fingerprint}
                </span>
              </span>
            )}

            <span
              className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-mono font-medium ${
                isSimulating
                  ? "border-sky-800/60 bg-sky-950/40 text-sky-300 print:bg-zinc-100 print:text-black"
                  : activeResult
                  ? "border-emerald-800/60 bg-emerald-950/40 text-emerald-300 print:bg-zinc-100 print:text-black"
                  : "border-zinc-700 bg-zinc-800/60 text-zinc-300 print:bg-zinc-100 print:text-black"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full mr-1.5 ${
                  isSimulating
                    ? "bg-sky-400 animate-pulse"
                    : activeResult
                    ? "bg-emerald-400"
                    : "bg-zinc-400"
                }`}
              />
              {isSimulating
                ? "Simulating..."
                : activeResult
                ? "Simulation Active"
                : "Baseline Loaded"}
            </span>
          </div>
        </div>

        {/* Feature Explanation & Epistemic Guardrail */}
        <p className="text-xs sm:text-sm text-zinc-300 print:text-zinc-800 leading-relaxed font-sans">
          Interactively adjust modeled operational assumptions to evaluate threshold breaches against decision constraints. Simulations execute deterministically on deep copies, leaving your baseline analysis artifacts strictly immutable.
        </p>

        {/* Epistemic Guardrail: Modeled Assumptions vs Verified Facts */}
        <div className="rounded-lg border border-sky-900/40 bg-sky-950/15 p-3.5 text-xs text-sky-200/90 print:bg-zinc-50 print:border-zinc-300 print:text-zinc-900 flex items-start gap-2.5">
          <svg
            className="h-4 w-4 text-sky-400 shrink-0 mt-0.5 print:hidden"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          <div className="space-y-1">
            <span className="font-semibold text-sky-300 print:text-black block">
              Distinction Between Modeled Assumptions and Verified Facts
            </span>
            <p className="leading-relaxed text-[11px] text-zinc-300 print:text-zinc-700">
              Modifying candidate variables recalculates mathematical constraint equations deterministically. It does not alter verified empirical evidence, boardroom findings, scenario narratives, or baseline probability distributions.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Loading Discovery State */}
      {isLoadingDiscovery && (
        <div className="py-12 text-center space-y-3 font-mono text-xs text-zinc-400 animate-pulse">
          <div className="inline-block h-6 w-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <p>Discovering adjustable numerical parameters from decision model...</p>
        </div>
      )}

      {/* 3. Discovery Error Handling */}
      {discoveryError && (
        <div
          role="alert"
          className="rounded-xl border border-rose-800/60 bg-rose-950/20 p-5 text-xs text-rose-200 space-y-3 print:bg-zinc-50 print:border-zinc-300 print:text-black"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold text-rose-300 print:text-black">
              <span className="h-2 w-2 rounded-full bg-rose-400" />
              <span>Variable Discovery Failed</span>
              {discoveryErrorStatusCode && (
                <span className="font-mono text-[10px] text-rose-400/80">
                  (HTTP {discoveryErrorStatusCode})
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={reloadDiscovery}
              className="text-[11px] font-mono underline hover:text-white transition-colors cursor-pointer"
            >
              Retry
            </button>
          </div>
          <p className="leading-relaxed text-zinc-300 print:text-zinc-800">
            {discoveryErrorStatusCode === 409
              ? "The analysis is currently executing. Simulation variables will become available once the pipeline completes."
              : discoveryErrorStatusCode === 404
              ? "Analysis artifact not found. Please verify the analysis identifier."
              : discoveryError}
          </p>
        </div>
      )}

      {/* 4. Active Simulation Runtime Error Handling */}
      {simulationError && (
        <div
          role="alert"
          className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-4 text-xs text-amber-200 space-y-2 print:bg-zinc-50 print:border-zinc-300 print:text-black"
        >
          <div className="flex items-center gap-2 font-semibold text-amber-300 print:text-black">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            <span>Simulation Execution Error</span>
            {simulationErrorStatusCode && (
              <span className="font-mono text-[10px]">
                (HTTP {simulationErrorStatusCode})
              </span>
            )}
          </div>
          <p className="leading-relaxed text-zinc-300 print:text-zinc-800">
            {simulationErrorStatusCode === 409
              ? "Baseline artifact fingerprint mismatch. The baseline artifacts have changed since this session started. Please reload the variables."
              : simulationError}
          </p>
        </div>
      )}

      {/* 5. Variable Controls (Sliders, inputs, run action) */}
      {!isLoadingDiscovery && discovery && (
        <SimulationVariableControls
          variables={discovery.variables}
          adjustments={adjustments}
          rawInputs={rawInputs}
          inputErrors={inputErrors}
          hasChanges={hasChanges}
          isValid={isValid}
          isSimulating={isSimulating}
          onAdjustmentChange={setAdjustment}
          onRunSimulation={runSimulation}
          onResetToBaseline={resetToBaseline}
        />
      )}

      {/* 6. Active Simulation Results: Comparison & Constraint Impacts */}
      {activeResult && discovery && (
        <div className="space-y-6 pt-4 border-t border-zinc-800/80 print:border-zinc-300">
          {/* Baseline vs Simulated Comparison */}
          <SimulationComparisonPanel
            result={activeResult}
            variables={discovery.variables}
          />

          {/* Constraint Impacts and Warnings */}
          <SimulationConstraintImpacts
            result={activeResult}
            variables={discovery.variables}
          />

          {/* Qualitative AI Explanation */}
          <SimulationAIExplanation
            simulationId={activeResult.id}
            explanation={explanation}
            isExplaining={isExplaining}
            explanationError={explanationError}
            onRequestExplanation={requestExplanation}
          />
        </div>
      )}

      {/* 7. Simulation History Panel */}
      {!isLoadingDiscovery && discovery && (
        <div className="pt-4 border-t border-zinc-800/80 print:hidden">
          <SimulationHistory
            history={history}
            isLoading={isLoadingHistory}
            error={historyError}
            selectedSimulationId={selectedSimulationId}
            currentBaselineFingerprint={discovery.baseline_fingerprint}
            onSelectSimulation={selectSavedSimulation}
            onRefreshHistory={loadHistory}
          />
        </div>
      )}
    </section>
  );
}
