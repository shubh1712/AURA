"use client";

import React from "react";
import type { FutureScenario, ScenarioType } from "@/types";
import { formatScenarioProbability } from "@/lib/scenarioHelpers";

interface ScenarioComparisonChartProps {
  scenarios: FutureScenario[];
  selectedScenarioType?: ScenarioType;
  onSelectScenario?: (type: ScenarioType) => void;
}

interface ScenarioConfigItem {
  type: ScenarioType;
  label: string;
  colorClass: string;
  barColor: string;
  strokeColor: string;
  badgeBg: string;
}

const SCENARIO_THEMES: Record<ScenarioType, ScenarioConfigItem> = {
  optimistic: {
    type: "optimistic",
    label: "Optimistic",
    colorClass: "text-emerald-400",
    barColor: "#10b981",
    strokeColor: "#059669",
    badgeBg: "bg-emerald-950/60 border-emerald-800/80 text-emerald-300",
  },
  base_case: {
    type: "base_case",
    label: "Base Case",
    colorClass: "text-sky-400",
    barColor: "#38bdf8",
    strokeColor: "#0284c7",
    badgeBg: "bg-sky-950/60 border-sky-800/80 text-sky-300",
  },
  pessimistic: {
    type: "pessimistic",
    label: "Pessimistic",
    colorClass: "text-rose-400",
    barColor: "#f43f5e",
    strokeColor: "#e11d48",
    badgeBg: "bg-rose-950/60 border-rose-800/80 text-rose-300",
  },
};

export function ScenarioComparisonChart({
  scenarios,
  selectedScenarioType = "base_case",
  onSelectScenario,
}: ScenarioComparisonChartProps) {
  if (!scenarios || scenarios.length === 0) {
    return null;
  }

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4"
      role="region"
      aria-label="Scenario Trajectory Range and Risk Comparison Chart"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400 font-semibold">
            Trajectory Dispersion
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Range &amp; Grouped Scenario Comparison
          </h4>
        </div>
        <span className="text-[10px] font-mono text-zinc-400 italic">
          * Modeled estimates — not factual probabilities
        </span>
      </div>

      {/* SVG Grouped Comparison Chart */}
      <div className="space-y-4 pt-1">
        {scenarios.map((scen) => {
          const theme = SCENARIO_THEMES[scen.scenario_type] || SCENARIO_THEMES.base_case;
          const isSelected = selectedScenarioType === scen.scenario_type;
          const pctValue = Math.min(Math.max(scen.probability * 100, 5), 100);
          const probFormatted = formatScenarioProbability(scen.probability);
          const risksCount = scen.risks?.length ?? 0;
          const oppsCount = scen.opportunities?.length ?? 0;

          return (
            <div
              key={scen.scenario_type}
              onClick={() => onSelectScenario?.(scen.scenario_type)}
              className={`rounded-lg border p-3.5 space-y-2 cursor-pointer transition-all ${
                isSelected
                  ? "border-zinc-500 bg-zinc-900/80 shadow-md"
                  : "border-zinc-800/80 bg-zinc-900/30 hover:border-zinc-700"
              }`}
              role="button"
              tabIndex={0}
              aria-pressed={isSelected}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectScenario?.(scen.scenario_type);
                }
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-mono uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${theme.badgeBg}`}
                  >
                    {theme.label}
                  </span>
                  <span className="text-xs font-semibold text-zinc-100">
                    {scen.name}
                  </span>
                </div>

                <div className="flex items-center gap-3 text-xs font-mono">
                  <span className={`font-bold ${theme.colorClass}`}>
                    {probFormatted}
                  </span>
                  <span className="text-[10px] text-zinc-500">modeled likelihood</span>
                </div>
              </div>

              {/* Accessible Range Bar */}
              <div className="space-y-1">
                <svg
                  className="w-full h-3 rounded overflow-hidden bg-zinc-900"
                  role="img"
                  aria-label={`${theme.label}: Modeled likelihood ${probFormatted}`}
                >
                  <rect width="100%" height="100%" fill="#18181b" />
                  <rect
                    width={`${pctValue}%`}
                    height="100%"
                    fill={theme.barColor}
                    rx="3"
                  />
                </svg>

                {/* Sub-metrics breakdown */}
                <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400 pt-0.5">
                  <div className="flex items-center gap-3">
                    <span className="text-emerald-400">
                      +{oppsCount} Opportunities
                    </span>
                    <span className="text-rose-400">
                      &bull; {risksCount} Critical Risks
                    </span>
                  </div>
                  <span className="text-zinc-500">
                    {scen.timeline?.length ?? 0} Timeline Milestones
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
