"use client";

import React from "react";
import type { FutureScenario, ScenarioType } from "@/types";

interface ScenarioProbabilitySpectrumProps {
  scenarios: FutureScenario[];
  selectedScenarioType: ScenarioType;
  onSelectScenario: (type: ScenarioType) => void;
}

const TYPE_CONFIG: Record<
  ScenarioType,
  {
    label: string;
    bgClass: string;
    borderClass: string;
    textClass: string;
    hoverClass: string;
    activeRing: string;
    accentColor: string;
  }
> = {
  optimistic: {
    label: "Optimistic Trajectory",
    bgClass: "bg-emerald-500",
    borderClass: "border-emerald-600",
    textClass: "text-emerald-400",
    hoverClass: "hover:bg-emerald-400",
    activeRing: "ring-2 ring-emerald-400 ring-offset-2 ring-offset-zinc-950",
    accentColor: "#10b981",
  },
  base_case: {
    label: "Base Case (Modeled Reality)",
    bgClass: "bg-sky-500",
    borderClass: "border-sky-600",
    textClass: "text-sky-400",
    hoverClass: "hover:bg-sky-400",
    activeRing: "ring-2 ring-sky-400 ring-offset-2 ring-offset-zinc-950",
    accentColor: "#0ea5e9",
  },
  pessimistic: {
    label: "Pessimistic / Stress Test",
    bgClass: "bg-rose-500",
    borderClass: "border-rose-600",
    textClass: "text-rose-400",
    hoverClass: "hover:bg-rose-400",
    activeRing: "ring-2 ring-rose-400 ring-offset-2 ring-offset-zinc-950",
    accentColor: "#f43f5e",
  },
};

export function ScenarioProbabilitySpectrum({
  scenarios,
  selectedScenarioType,
  onSelectScenario,
}: ScenarioProbabilitySpectrumProps) {
  if (!scenarios || scenarios.length === 0) {
    return null;
  }

  // Calculate percentages strictly based on backend probabilities
  const totalProb = scenarios.reduce((acc, s) => acc + (s.probability || 0), 0);
  const items = scenarios.map((s) => {
    const rawProb = s.probability || 0;
    const pct = totalProb > 0 ? Math.round((rawProb / totalProb) * 100) : 0;
    const cfg = TYPE_CONFIG[s.scenario_type] || {
      label: s.name,
      bgClass: "bg-zinc-500",
      borderClass: "border-zinc-600",
      textClass: "text-zinc-400",
      hoverClass: "hover:bg-zinc-400",
      activeRing: "ring-2 ring-zinc-400",
      accentColor: "#71717a",
    };

    return {
      scenario: s,
      pct,
      cfg,
      isSelected: s.scenario_type === selectedScenarioType,
    };
  });

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 sm:p-5 space-y-3.5 text-zinc-100 shadow-sm"
      role="region"
      aria-label="Scenario Probability Distribution Spectrum"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-2.5 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400 font-semibold">
            Trajectory Likelihood Spectrum
          </span>
          <h4 className="text-xs sm:text-sm font-semibold text-white tracking-tight mt-0.5">
            100% Proportional Probability Distribution
          </h4>
        </div>
        <span className="text-[10px] sm:text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
          Click any segment to switch view
        </span>
      </div>

      {/* Proportional 100% Stacked Spectrum Bar */}
      <div
        className="h-7 w-full bg-zinc-900 rounded-lg overflow-hidden flex p-0.5 gap-0.5 border border-zinc-800 shadow-inner"
        role="tablist"
        aria-label="Scenario selection tabs"
      >
        {items.map(({ scenario, pct, cfg, isSelected }) => (
          <button
            key={scenario.scenario_type}
            type="button"
            role="tab"
            aria-selected={isSelected}
            onClick={() => onSelectScenario(scenario.scenario_type)}
            style={{ width: `${Math.max(pct, 12)}%` }}
            className={`h-full rounded transition-all duration-200 cursor-pointer flex items-center justify-center text-white text-[10px] sm:text-xs font-mono font-bold tracking-tight px-1 overflow-hidden select-none focus:outline-none ${
              cfg.bgClass
            } ${cfg.hoverClass} ${isSelected ? `${cfg.activeRing} shadow-lg z-10` : "opacity-85 hover:opacity-100"}`}
            title={`${cfg.label}: ${pct}% likelihood (${scenario.name})`}
          >
            <span className="truncate">
              {pct}% {scenario.scenario_type === "base_case" ? "• Base" : ""}
            </span>
          </button>
        ))}
      </div>

      {/* Legend & Details Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1">
        {items.map(({ scenario, pct, cfg, isSelected }) => (
          <button
            key={scenario.scenario_type}
            type="button"
            onClick={() => onSelectScenario(scenario.scenario_type)}
            className={`text-left rounded-lg p-2.5 transition-all cursor-pointer border ${
              isSelected
                ? "border-zinc-650 bg-zinc-900/90 shadow-sm ring-1 ring-zinc-700"
                : "border-zinc-800/80 bg-zinc-900/30 hover:bg-zinc-900/60 hover:border-zinc-750"
            }`}
          >
            <div className="flex items-center justify-between gap-1 mb-1">
              <span className={`text-[10px] font-mono uppercase font-bold tracking-wider ${cfg.textClass}`}>
                {cfg.label}
              </span>
              <span className="text-xs font-mono font-bold text-white">
                {pct}%
              </span>
            </div>
            <p className="text-xs font-semibold text-zinc-200 truncate">
              {scenario.name}
            </p>
            <p className="text-[10px] text-zinc-400 font-mono mt-0.5">
              {(scenario.timeline || []).length} Milestones • {(scenario.risks || []).length} Risks
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}
