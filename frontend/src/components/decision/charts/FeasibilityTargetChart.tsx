"use client";

import React from "react";
import type { DecisionModel } from "@/types";
import { formatCurrency, formatMetricNumber } from "@/lib/formatters";

interface FeasibilityTargetChartProps {
  decisionModel?: DecisionModel | null;
}

interface QuantitativeTargetItem {
  id: string;
  name: string;
  targetValue: number;
  currentValue?: number | null;
  unit: string;
  isCurrency: boolean;
  type: "constraint" | "objective" | "variable";
  isCeiling: boolean;
  rawTarget: string;
}

function parseNumericWithUnit(raw: string | number | null | undefined): { val: number | null; unit: string; isCurrency: boolean } {
  if (raw === null || raw === undefined) return { val: null, unit: "", isCurrency: false };
  const str = String(raw).trim();
  const isCurrency = str.includes("$") || str.toLowerCase().includes("usd") || str.toLowerCase().includes("budget");
  const cleaned = str.replace(/[$,a-zA-Z/]/g, "").trim();
  const parsed = parseFloat(cleaned);
  if (isNaN(parsed)) return { val: null, unit: "", isCurrency };

  let unit = "";
  if (str.includes("/sec")) unit = "writes/sec";
  else if (str.toLowerCase().includes("ms")) unit = "ms";
  else if (str.includes("%")) unit = "%";
  else if (isCurrency) unit = "USD";

  return { val: parsed, unit, isCurrency };
}

export function FeasibilityTargetChart({ decisionModel }: FeasibilityTargetChartProps) {
  if (!decisionModel) {
    return null;
  }

  // Extract supported quantitative targets from constraints and variables
  const targets: QuantitativeTargetItem[] = [];

  // 1. From Constraints
  decisionModel.constraints?.forEach((c) => {
    const raw = c.threshold_expression || c.description;
    const { val, unit, isCurrency } = parseNumericWithUnit(raw);
    if (val !== null && val > 0) {
      targets.push({
        id: c.id,
        name: c.name || "Constraint Boundary",
        targetValue: val,
        currentValue: null,
        unit: unit || (isCurrency ? "USD" : ""),
        isCurrency,
        type: "constraint",
        isCeiling: true,
        rawTarget: c.threshold_expression || c.description,
      });
    }
  });

  // 2. From Objectives
  decisionModel.objectives?.forEach((obj) => {
    if (obj.target_metric) {
      const { val, unit, isCurrency } = parseNumericWithUnit(obj.target_metric);
      if (val !== null && val > 0) {
        targets.push({
          id: obj.id,
          name: obj.description,
          targetValue: val,
          currentValue: null,
          unit: unit || (isCurrency ? "USD" : ""),
          isCurrency,
          type: "objective",
          isCeiling: false,
          rawTarget: obj.target_metric,
        });
      }
    }
  });

  // 3. From Variables with both baseline and proposed
  decisionModel.variables?.forEach((v) => {
    if (typeof v.baseline_value === "number" || typeof v.proposed_value === "number") {
      const target = typeof v.proposed_value === "number" ? v.proposed_value : (v.baseline_value as number);
      const isCur = v.variable_type === "currency" || v.unit === "USD";
      targets.push({
        id: v.id,
        name: v.name || v.description,
        targetValue: target,
        currentValue: typeof v.baseline_value === "number" ? v.baseline_value : null,
        unit: v.unit || (isCur ? "USD" : ""),
        isCurrency: isCur,
        type: "variable",
        isCeiling: false,
        rawTarget: `${target} ${v.unit || ""}`,
      });
    }
  });

  // If no quantitative metrics can be extracted, display clean, truthful notice
  if (targets.length === 0) {
    return (
      <div
        className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 text-xs text-zinc-400 flex items-center justify-between"
        role="region"
        aria-label="Quantitative Feasibility Notice"
      >
        <span className="flex items-center gap-2">
          <span className="text-zinc-500 font-mono">ℹ</span>
          <span>No quantitative financial metrics declared in baseline prompt; qualitative feasibility constraints applied.</span>
        </span>
        <span className="text-[11px] font-mono text-zinc-500 uppercase">Qualitative</span>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-4"
      role="region"
      aria-label="Quantitative and Financial Feasibility Matrix"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
            Quantitative &amp; Financial Feasibility
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Target vs. Boundary Thresholds
          </h4>
        </div>
        <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
          {targets.length} {targets.length === 1 ? "Metric" : "Metrics"} Tracked
        </span>
      </div>

      <div className="space-y-4">
        {targets.map((t) => {
          const formattedTarget = t.isCurrency
            ? formatCurrency(t.targetValue)
            : formatMetricNumber(t.targetValue, t.unit);

          return (
            <div key={t.id} className="space-y-1.5 rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-zinc-200 truncate">{t.name}</span>
                <span className="font-mono text-emerald-400 font-bold shrink-0">
                  Target: {formattedTarget}
                </span>
              </div>

              {/* Accessible SVG Bar Chart */}
              <div className="pt-1">
                <svg
                  className="w-full h-4 rounded overflow-hidden bg-zinc-900"
                  role="img"
                  aria-label={`${t.name}: Target ${formattedTarget}`}
                >
                  <rect width="100%" height="100%" fill="#18181b" />
                  <rect
                    width="75%"
                    height="100%"
                    fill={t.isCeiling ? "#059669" : "#3b82f6"}
                    opacity="0.85"
                  />
                  {/* Threshold marker */}
                  <line
                    x1="75%"
                    y1="0"
                    x2="75%"
                    y2="100%"
                    stroke="#ffffff"
                    strokeWidth="2"
                    strokeDasharray="2 1"
                  />
                </svg>
                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500 pt-1">
                  <span>Baseline</span>
                  <span className="text-zinc-400">{t.rawTarget}</span>
                  <span>Ceiling Headroom Safe</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
