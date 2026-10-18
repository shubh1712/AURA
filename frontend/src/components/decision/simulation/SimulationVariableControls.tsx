"use client";

import React, { useState } from "react";
import type { SimulationVariable } from "@/types";

interface SimulationVariableControlsProps {
  variables: SimulationVariable[];
  adjustments: Record<string, number>;
  rawInputs: Record<string, string>;
  inputErrors: Record<string, string>;
  hasChanges: boolean;
  isValid: boolean;
  isSimulating: boolean;
  onAdjustmentChange: (variableId: string, value: string | number) => void;
  onRunSimulation: () => void;
  onResetToBaseline: () => void;
}

export function SimulationVariableControls({
  variables,
  adjustments,
  rawInputs,
  inputErrors,
  hasChanges,
  isValid,
  isSimulating,
  onAdjustmentChange,
  onRunSimulation,
  onResetToBaseline,
}: SimulationVariableControlsProps) {
  const [showUnsupported, setShowUnsupported] = useState(false);

  const supportedVars = variables.filter((v) => v.simulation_supported);
  const unsupportedVars = variables.filter((v) => !v.simulation_supported);

  const canSubmit = hasChanges && isValid && !isSimulating;

  return (
    <div className="space-y-6">
      {/* Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-zinc-800/80 print:hidden">
        <div>
          <h3 className="text-sm font-semibold text-white tracking-tight">
            Adjustable Numerical Assumptions
          </h3>
          <p className="text-xs text-zinc-400 mt-0.5">
            Modify supported model variables below to test constraint stress thresholds.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={onResetToBaseline}
            disabled={isSimulating || (!hasChanges && Object.keys(inputErrors).length === 0)}
            className="inline-flex items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800/80 px-3.5 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            title="Revert all adjustments to authoritative baseline values"
          >
            Reset to Baseline
          </button>

          <button
            type="button"
            onClick={onRunSimulation}
            disabled={!canSubmit}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-emerald-600 bg-emerald-600/90 hover:bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-white transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
          >
            {isSimulating ? (
              <>
                <svg
                  className="animate-spin -ml-0.5 mr-1.5 h-3.5 w-3.5 text-white"
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
                <span>Evaluating...</span>
              </>
            ) : (
              <>
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>Run Simulation</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* No Supported Variables Message */}
      {supportedVars.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-5 text-center text-xs text-zinc-400">
          No supported numerical variables were discovered in this decision model.
        </div>
      )}

      {/* Supported Variables Grid / Cards */}
      {supportedVars.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 print:hidden">
          {supportedVars.map((v) => {
            const hasFiniteBounds =
              v.minimum_value !== null &&
              v.minimum_value !== undefined &&
              v.maximum_value !== null &&
              v.maximum_value !== undefined &&
              Number.isFinite(v.minimum_value) &&
              Number.isFinite(v.maximum_value);

            const currentValue = adjustments[v.variable_id] ?? v.baseline_value;
            const currentRaw = rawInputs[v.variable_id] ?? String(v.baseline_value);
            const err = inputErrors[v.variable_id];
            const isModified = Math.abs(currentValue - v.baseline_value) > 1e-9;

            // Calculate step size based on magnitude
            let step = 1;
            if (hasFiniteBounds) {
              const range = (v.maximum_value as number) - (v.minimum_value as number);
              if (range <= 1) step = 0.01;
              else if (range <= 10) step = 0.1;
              else if (range <= 100) step = 1;
              else if (range <= 10000) step = 10;
              else step = 100;
            } else if (v.value_type === "percentage" || v.value_type === "ratio") {
              step = 0.1;
            }

            const inputId = `sim-var-${v.variable_id}`;
            const errorId = `sim-err-${v.variable_id}`;

            return (
              <div
                key={v.variable_id}
                className={`rounded-xl border p-4.5 space-y-3.5 transition-colors ${
                  isModified
                    ? "border-emerald-700/60 bg-emerald-950/15"
                    : "border-zinc-800 bg-zinc-950/40"
                }`}
              >
                {/* Header: Label, Baseline, and Modified Badge */}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <label
                      htmlFor={inputId}
                      className="text-xs font-semibold text-zinc-200 block"
                    >
                      {v.label}
                    </label>
                    <span className="text-[11px] text-zinc-400 font-mono">
                      Baseline: {v.baseline_value.toLocaleString()}{v.unit ? ` ${v.unit}` : ""}
                    </span>
                  </div>

                  {isModified && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border border-emerald-800/80 bg-emerald-950/60 text-emerald-300">
                      Modified
                    </span>
                  )}
                </div>

                {/* Description and Support Reason */}
                <p className="text-[11px] text-zinc-400 leading-relaxed">
                  {v.description}
                </p>

                {/* Input Controls */}
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="relative flex-1">
                      <input
                        id={inputId}
                        type="number"
                        value={currentRaw}
                        step={step}
                        min={v.minimum_value ?? undefined}
                        max={v.maximum_value ?? undefined}
                        aria-invalid={Boolean(err)}
                        aria-describedby={err ? errorId : undefined}
                        onChange={(e) =>
                          onAdjustmentChange(v.variable_id, e.target.value)
                        }
                        className={`w-full rounded-lg border px-3 py-1.5 text-xs font-mono text-white bg-zinc-900/90 focus:outline-none focus:ring-2 transition-colors ${
                          err
                            ? "border-rose-600 focus:ring-rose-500"
                            : "border-zinc-700 focus:ring-emerald-500"
                        }`}
                      />
                    </div>
                    {v.unit && (
                      <span className="text-xs font-mono text-zinc-400 shrink-0">
                        {v.unit}
                      </span>
                    )}
                  </div>

                  {/* Slider: Only rendered when finite bounds exist */}
                  {hasFiniteBounds && (
                    <div className="pt-1.5 space-y-1">
                      <input
                        type="range"
                        min={v.minimum_value as number}
                        max={v.maximum_value as number}
                        step={step}
                        value={Number.isFinite(currentValue) ? currentValue : v.baseline_value}
                        onChange={(e) =>
                          onAdjustmentChange(v.variable_id, parseFloat(e.target.value))
                        }
                        aria-label={`Slider for ${v.label}`}
                        className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                      />
                      <div className="flex justify-between text-[10px] font-mono text-zinc-500">
                        <span>Min: {v.minimum_value}</span>
                        <span>Max: {v.maximum_value}</span>
                      </div>
                    </div>
                  )}

                  {/* Bounds metadata if unbounded */}
                  {!hasFiniteBounds && (
                    <div className="text-[10px] font-mono text-zinc-500">
                      {v.minimum_value !== null && v.minimum_value !== undefined ? (
                        <span>Min: {v.minimum_value} (no upper limit)</span>
                      ) : (
                        <span>Unbounded numerical variable</span>
                      )}
                    </div>
                  )}

                  {/* Validation Error */}
                  {err && (
                    <p
                      id={errorId}
                      role="alert"
                      className="text-[11px] text-rose-400 font-medium"
                    >
                      {err}
                    </p>
                  )}
                </div>

                {/* Source & Causal Mapping Metadata */}
                <div className="pt-2 border-t border-zinc-800/60 flex flex-col gap-1 text-[10px] text-zinc-500 font-mono">
                  <div className="truncate" title={v.source_field_path}>
                    <span className="text-zinc-600">Source:</span> {v.source_field_path}
                  </div>
                  <div className="text-emerald-400/90 leading-tight">
                    &bull; {v.support_reason}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Static Printable Summary of Adjustable Variables */}
      <div className="hidden print:block space-y-2">
        <h4 className="text-xs font-semibold text-black uppercase tracking-wider">
          Simulation Variables and Tested Assumptions
        </h4>
        <table className="w-full text-xs border border-zinc-300 text-left">
          <thead>
            <tr className="bg-zinc-100 border-b border-zinc-300 font-semibold text-zinc-700">
              <th className="p-2">Variable</th>
              <th className="p-2">Baseline</th>
              <th className="p-2">Proposed</th>
              <th className="p-2">Unit</th>
              <th className="p-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {supportedVars.map((v) => {
              const current = adjustments[v.variable_id] ?? v.baseline_value;
              const isMod = Math.abs(current - v.baseline_value) > 1e-9;
              return (
                <tr key={v.variable_id} className="border-b border-zinc-200">
                  <td className="p-2 font-medium">{v.label}</td>
                  <td className="p-2 font-mono">{v.baseline_value}</td>
                  <td className="p-2 font-mono font-bold">
                    {isMod ? current : `${v.baseline_value} (unchanged)`}
                  </td>
                  <td className="p-2">{v.unit || "-"}</td>
                  <td className="p-2">{isMod ? "Adjusted" : "Baseline"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Unsupported Variables Section (Accordion/Callout) */}
      {unsupportedVars.length > 0 && (
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/30 overflow-hidden print:hidden">
          <button
            type="button"
            onClick={() => setShowUnsupported((prev) => !prev)}
            className="w-full px-4 py-3 flex items-center justify-between text-left text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40 transition-colors"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-zinc-500">[{unsupportedVars.length}]</span>
              <span>Discovered Variables Without Validated Causal Mapping</span>
            </div>
            <span className="font-mono text-[11px] text-zinc-500">
              {showUnsupported ? "Hide" : "Show"}
            </span>
          </button>

          {showUnsupported && (
            <div className="p-4 border-t border-zinc-800/80 space-y-3 bg-zinc-950/60">
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                The following variables were discovered in the decision model but are excluded from what-if adjustments to protect mathematical rigor:
              </p>
              <div className="space-y-2">
                {unsupportedVars.map((v) => (
                  <div
                    key={v.variable_id}
                    className="rounded-lg border border-zinc-800/60 bg-zinc-900/40 p-3 space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-zinc-300">{v.label}</span>
                      <span className="font-mono text-[11px] text-zinc-500">
                        {v.baseline_value !== null ? `${v.baseline_value} ${v.unit || ""}` : "Non-numeric"}
                      </span>
                    </div>
                    <p className="text-[11px] text-zinc-400">{v.description}</p>
                    <div className="text-[10px] font-mono text-amber-400/90">
                      Reason: {v.support_reason}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
