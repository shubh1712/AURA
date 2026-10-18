"use client";

import React from "react";
import type { SimulationResult, SimulationVariable } from "@/types";

interface SimulationComparisonPanelProps {
  result: SimulationResult;
  variables: SimulationVariable[];
}

export function SimulationComparisonPanel({
  result,
  variables,
}: SimulationComparisonPanelProps) {
  const varMap = new Map<string, SimulationVariable>();
  for (const v of variables) {
    varMap.set(v.variable_id, v);
  }

  // Check if simulated resilience score is legitimately available
  const hasValidScoreDelta =
    result.simulated_resilience_score !== null &&
    result.simulated_resilience_score !== undefined &&
    result.score_delta !== null &&
    result.score_delta !== undefined;

  return (
    <div className="space-y-6 print:space-y-4">
      {/* 1. Resilience Impact Assessment Section */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-4 print:bg-white print:border-zinc-300 print:text-black print:break-inside-avoid">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80 print:border-zinc-300">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 print:text-black">
              Resilience Score Impact
            </h4>
            <p className="text-[11px] text-zinc-400 print:text-zinc-600 mt-0.5">
              Deterministic causal evaluation against baseline resilience formula.
            </p>
          </div>
          <span className="font-mono text-[11px] text-zinc-500 self-start sm:self-auto">
            Run ID: {result.id}
          </span>
        </div>

        {hasValidScoreDelta ? (
          /* Deterministic Score Recalculation Card */
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 print:border-zinc-300 print:bg-zinc-50">
              <span className="text-[11px] uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-mono block mb-1">
                Baseline Resilience
              </span>
              <div className="text-xl font-bold font-mono text-zinc-200 print:text-black">
                {result.baseline_resilience_score?.toFixed(1) ?? "N/A"}{" "}
                <span className="text-xs text-zinc-500">/ 100</span>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 print:border-zinc-300 print:bg-zinc-50">
              <span className="text-[11px] uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-mono block mb-1">
                Simulated Resilience
              </span>
              <div className="text-xl font-bold font-mono text-emerald-400 print:text-black">
                {result.simulated_resilience_score?.toFixed(1)}{" "}
                <span className="text-xs text-zinc-500">/ 100</span>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 print:border-zinc-300 print:bg-zinc-50">
              <span className="text-[11px] uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-mono block mb-1">
                Recalculated Delta
              </span>
              <div
                className={`text-xl font-bold font-mono ${
                  (result.score_delta as number) > 0
                    ? "text-emerald-400"
                    : (result.score_delta as number) < 0
                    ? "text-rose-400"
                    : "text-zinc-300"
                } print:text-black`}
              >
                {(result.score_delta as number) > 0 ? "+" : ""}
                {result.score_delta?.toFixed(1)}
              </div>
              <span className="text-[10px] text-zinc-500 font-mono">
                Deterministic Recalculation
              </span>
            </div>
          </div>
        ) : (
          /* Causal Mapping Unavailable (Truthful, non-fabricated state) */
          <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-4.5 space-y-3 print:bg-zinc-50 print:border-zinc-300">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <span className="text-[11px] uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-mono block mb-1">
                  Baseline Resilience Score
                </span>
                <span className="text-xl font-bold font-mono text-zinc-200 print:text-black">
                  {result.baseline_resilience_score !== null &&
                  result.baseline_resilience_score !== undefined
                    ? `${result.baseline_resilience_score.toFixed(1)} / 100`
                    : "Baseline Available"}
                </span>
              </div>

              <div className="sm:text-right">
                <span className="text-[11px] uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-mono block mb-1">
                  Simulated Resilience Delta
                </span>
                <span className="inline-flex items-center px-2.5 py-1 rounded text-xs font-mono font-medium border border-zinc-700 bg-zinc-800/70 text-zinc-300 print:border-zinc-300 print:text-black print:bg-white">
                  Impact not currently calculable
                </span>
              </div>
            </div>

            <p className="text-xs text-zinc-400 print:text-zinc-700 leading-relaxed pt-2 border-t border-zinc-800/60 print:border-zinc-200">
              AURA evaluated operational constraint boundaries for these adjustments, but lacks a validated mathematical causal mapping from this business variable into the composite resilience scoring formula. To prevent fabricated projections, no synthetic score delta is rendered.
            </p>
          </div>
        )}
      </div>

      {/* 2. Variable Value Comparison Table */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-5 space-y-4 print:bg-white print:border-zinc-300 print:text-black print:break-inside-avoid">
        <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80 print:border-zinc-300">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 print:text-black">
              Baseline vs Simulated Assumptions
            </h4>
            <p className="text-[11px] text-zinc-400 print:text-zinc-600 mt-0.5">
              Exact parameter substitutions and calculated variance.
            </p>
          </div>
          <span className="text-[11px] font-mono text-zinc-500">
            {result.applied_adjustments.length} adjustment
            {result.applied_adjustments.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-zinc-800/80 print:border-zinc-300 text-zinc-400 print:text-zinc-600 font-mono">
                <th className="py-2.5 px-3 font-medium">Variable</th>
                <th className="py-2.5 px-3 font-medium">Baseline Value</th>
                <th className="py-2.5 px-3 font-medium">Adjusted Value</th>
                <th className="py-2.5 px-3 font-medium">Absolute Change</th>
                <th className="py-2.5 px-3 font-medium">Percentage Change</th>
                <th className="py-2.5 px-3 font-medium">Calculation Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50 print:divide-zinc-200">
              {result.applied_adjustments.map((adj) => {
                const varDef = varMap.get(adj.variable_id);
                const impact = result.impacts.find(
                  (imp) => imp.variable_id === adj.variable_id
                );

                const original = impact ? impact.original_value : (varDef?.baseline_value ?? 0);
                const adjusted = adj.proposed_value;
                const unit = adj.unit || varDef?.unit || "";

                const absDiff = adjusted - original;

                // Mathematical percentage change calculation guarded against division by zero
                let pctDisplay = "N/A (zero baseline)";
                if (Math.abs(original) > 1e-9) {
                  const pct = ((adjusted - original) / Math.abs(original)) * 100;
                  pctDisplay = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
                }

                const calcStatus = impact?.calculation_status || result.status;

                return (
                  <tr
                    key={adj.variable_id}
                    className="hover:bg-zinc-900/30 print:hover:bg-transparent transition-colors font-mono"
                  >
                    <td className="py-3 px-3 font-sans font-medium text-zinc-200 print:text-black">
                      {varDef?.label || adj.variable_id}
                    </td>

                    <td className="py-3 px-3 text-zinc-400 print:text-zinc-700">
                      {original.toLocaleString()} {unit}
                    </td>

                    <td className="py-3 px-3 text-emerald-400 print:text-black font-semibold">
                      {adjusted.toLocaleString()} {unit}
                    </td>

                    <td className="py-3 px-3 text-zinc-300 print:text-black">
                      {absDiff >= 0 ? "+" : ""}
                      {absDiff.toLocaleString()} {unit}
                    </td>

                    <td className="py-3 px-3 text-zinc-300 print:text-black">
                      {pctDisplay}
                    </td>

                    <td className="py-3 px-3">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border border-zinc-700/80 bg-zinc-800/50 text-zinc-300 print:bg-zinc-100 print:border-zinc-300 print:text-black">
                        {calcStatus}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
