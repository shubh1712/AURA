"use client";

import React from "react";
import type { SimulationResult } from "@/types";

interface SimulationHistoryProps {
  history: SimulationResult[];
  isLoading: boolean;
  error: string | null;
  selectedSimulationId: string | null;
  currentBaselineFingerprint?: string;
  onSelectSimulation: (sim: SimulationResult) => void;
  onRefreshHistory: () => void;
}

export function SimulationHistory({
  history,
  isLoading,
  error,
  selectedSimulationId,
  currentBaselineFingerprint,
  onSelectSimulation,
  onRefreshHistory,
}: SimulationHistoryProps) {
  return (
    <div className="space-y-4 print:hidden">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
            Previous Simulation Runs
          </h4>
          <p className="text-[11px] text-zinc-400 mt-0.5">
            Persisted deterministic runs evaluated against this analysis.
          </p>
        </div>

        <button
          type="button"
          onClick={onRefreshHistory}
          disabled={isLoading}
          className="text-[11px] font-mono text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer disabled:opacity-40"
          title="Reload simulation history from database"
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-rose-800/60 bg-rose-950/20 p-3 text-xs text-rose-300"
        >
          {error}
        </div>
      )}

      {/* Loading state */}
      {isLoading && history.length === 0 && (
        <div className="py-6 text-center text-xs text-zinc-500 font-mono animate-pulse">
          Loading persisted simulations...
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && history.length === 0 && (
        <div className="rounded-lg border border-zinc-800/60 bg-zinc-950/30 p-4 text-center text-xs text-zinc-500">
          No previous simulations saved for this analysis. Adjust variables above and run a simulation.
        </div>
      )}

      {/* History list */}
      {history.length > 0 && (
        <div className="space-y-2">
          {history.map((sim) => {
            const isSelected = sim.id === selectedSimulationId;
            const isStale =
              Boolean(currentBaselineFingerprint) &&
              Boolean(sim.baseline_fingerprint) &&
              sim.baseline_fingerprint !== currentBaselineFingerprint;

            // Display human-readable timestamp ONLY if API provided one
            let timestampDisplay: string | null = null;
            if (sim.created_at && typeof sim.created_at === "string") {
              try {
                const date = new Date(sim.created_at);
                if (!isNaN(date.getTime())) {
                  timestampDisplay = date.toLocaleString();
                }
              } catch {
                timestampDisplay = null;
              }
            }

            return (
              <div
                key={sim.id}
                className={`rounded-xl border p-3.5 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  isSelected
                    ? "border-emerald-600/80 bg-emerald-950/20"
                    : "border-zinc-800/80 bg-zinc-950/40 hover:border-zinc-700"
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs font-semibold text-zinc-200">
                      {sim.id}
                    </span>

                    {/* Stale Baseline Fingerprint Warning */}
                    {isStale && (
                      <span
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono border border-amber-800/70 bg-amber-950/50 text-amber-300"
                        title="Saved run baseline fingerprint does not match the active analysis baseline."
                      >
                        Stale Baseline
                      </span>
                    )}

                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono border border-zinc-700 bg-zinc-800/60 text-zinc-300">
                      {sim.status}
                    </span>

                    {timestampDisplay && (
                      <span className="text-[11px] font-mono text-zinc-400">
                        {timestampDisplay}
                      </span>
                    )}
                  </div>

                  {/* Summary of applied adjustments */}
                  <div className="text-[11px] text-zinc-400 font-mono flex flex-wrap gap-2 pt-0.5">
                    {sim.applied_adjustments.map((adj, aIdx) => (
                      <span
                        key={aIdx}
                        className="bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded text-zinc-300"
                      >
                        {adj.variable_id}: {adj.proposed_value} {adj.unit || ""}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="shrink-0">
                  <button
                    type="button"
                    onClick={() => onSelectSimulation(sim)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer border ${
                      isSelected
                        ? "border-emerald-500 bg-emerald-600/30 text-emerald-300 cursor-default"
                        : "border-zinc-700 bg-zinc-800/80 text-zinc-200 hover:bg-zinc-700 hover:text-white"
                    }`}
                  >
                    {isSelected ? "Active View" : "Reopen Run"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
