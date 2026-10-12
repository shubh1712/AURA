"use client";

import React from "react";
import type { CalculationResult } from "@/types";

interface FinancialFeasibilityCardProps {
  calculations: CalculationResult[];
}

export function FinancialFeasibilityCard({
  calculations,
}: FinancialFeasibilityCardProps) {
  const formatCurrency = (val: number | null, curr: string | null = "USD") => {
    if (val === null || val === undefined) return "Unresolved";
    const validCurrency = curr && curr.length === 3 ? curr.toUpperCase() : "USD";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: validCurrency,
      maximumFractionDigits: 0,
    }).format(val);
  };

  const getStatusBadge = (status: CalculationResult["status"]) => {
    switch (status) {
      case "feasible":
        return {
          bg: "bg-emerald-950/60 border-emerald-800 text-emerald-300",
          label: "Feasible",
        };
      case "infeasible":
        return {
          bg: "bg-rose-950/60 border-rose-800 text-rose-300",
          label: "Infeasible Deficit",
        };
      case "unresolved":
      default:
        return {
          bg: "bg-amber-950/60 border-amber-800 text-amber-300",
          label: "Unresolved / Missing Data",
        };
    }
  };

  return (
    <div
      role="region"
      aria-label="Deterministic Financial & Quantitative Feasibility"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider font-semibold text-emerald-400">
            Deterministic Precision Engine
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Financial &amp; Quantitative Feasibility
          </h2>
        </div>

        <div className="text-xs text-zinc-400 bg-zinc-800/80 px-3 py-1.5 rounded-lg border border-zinc-700 font-mono">
          Precision-Safe Arithmetic (Decimal)
        </div>
      </div>

      <p className="text-xs text-zinc-400 leading-relaxed max-w-3xl">
        All financial feasibility results are evaluated deterministically using explicit mathematical formulas.
        Missing inputs remain unresolved rather than interpolated or fabricated with artificial estimates.
      </p>

      {/* Grid of Calculations */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {calculations.map((calc, idx) => {
          const badge = getStatusBadge(calc.status);
          const isUnresolved = calc.status === "unresolved";
          const isInfeasible = calc.status === "infeasible";

          return (
            <div
              key={calc.calculation_id || (calc as unknown as { id?: string }).id || idx}
              className={`rounded-xl border p-5 flex flex-col justify-between space-y-4 transition-all ${
                isInfeasible
                  ? "border-rose-900/50 bg-rose-950/20"
                  : isUnresolved
                  ? "border-amber-900/40 bg-amber-950/10"
                  : "border-zinc-800 bg-zinc-950/60"
              }`}
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-mono text-zinc-400 uppercase tracking-wider">
                    {(calc.category || "Financial Metric").replace("_", " ")}
                  </span>
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border ${badge.bg}`}
                  >
                    {badge.label}
                  </span>
                </div>

                <h3 className="text-sm font-bold text-white leading-snug">
                  {calc.title}
                </h3>

                {/* Formatted Number Display */}
                <div className="pt-2">
                  {calc.value !== null ? (
                    <div
                      className={`text-2xl font-bold font-mono ${
                        isInfeasible
                          ? "text-rose-400"
                          : "text-emerald-400"
                      }`}
                    >
                      {formatCurrency(calc.value, calc.currency)}
                    </div>
                  ) : (
                    <div className="text-lg font-mono text-amber-400 italic font-medium">
                      Unresolved
                    </div>
                  )}
                </div>

                {/* Explanation */}
                <p className="text-xs text-zinc-300 leading-relaxed pt-1">
                  {calc.explanation}
                </p>
              </div>

              {/* Formula & Provenance Details */}
              <div className="pt-3 border-t border-zinc-800/80 space-y-2">
                <div
                  className="text-[10px] font-mono text-zinc-500 bg-zinc-900 p-2 rounded border border-zinc-800/80 truncate"
                  title={calc.formula || calc.formula_expression || "Formula not specified"}
                >
                  Formula: {calc.formula || calc.formula_expression || "Formula not specified"}
                </div>

                {calc.missing_inputs.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-mono text-amber-400 font-semibold block">
                      Missing Required Inputs:
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {calc.missing_inputs.map((inp) => (
                        <span
                          key={inp}
                          className="text-[10px] font-mono bg-amber-950/60 border border-amber-800/60 text-amber-300 px-1.5 py-0.5 rounded"
                        >
                          {inp}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {(calc.explicit_assumptions || calc.assumptions) && (calc.explicit_assumptions || calc.assumptions)!.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-mono text-zinc-400 font-semibold block">
                      Explicit Assumptions:
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {(calc.explicit_assumptions || calc.assumptions)!.map((assump: string, idx: number) => (
                        <span
                          key={idx}
                          className="text-[10px] font-mono bg-zinc-900 border border-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded"
                        >
                          {assump}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
