"use client";

import React, { useState } from "react";
import type { ScenarioSet } from "@/types";

interface ScenarioMatrixVisualizerProps {
  scenarioSet: ScenarioSet;
}

export function ScenarioMatrixVisualizer({
  scenarioSet,
}: ScenarioMatrixVisualizerProps) {
  const [activeScenarioId, setActiveScenarioId] = useState<string>(
    scenarioSet.scenarios[1]?.id || scenarioSet.scenarios[0]?.id || ""
  );

  const activeScenario =
    scenarioSet.scenarios.find((s) => s.id === activeScenarioId) ||
    scenarioSet.scenarios[0];

  const getScenarioBadge = (type: string) => {
    switch (type.toLowerCase()) {
      case "optimistic":
        return {
          bg: "bg-emerald-950/60 border-emerald-800 text-emerald-300",
          border: "border-emerald-800/60",
          name: "Optimistic Trajectory",
        };
      case "pessimistic":
        return {
          bg: "bg-rose-950/60 border-rose-800 text-rose-300",
          border: "border-rose-800/60",
          name: "Pessimistic Stress Case",
        };
      case "base_case":
      default:
        return {
          bg: "bg-sky-950/60 border-sky-800 text-sky-300",
          border: "border-sky-800/60",
          name: "Expected Baseline",
        };
    }
  };

  return (
    <div
      role="region"
      id="section-future-explorer"
      aria-label="Multi-Pathway Future Scenarios"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider font-semibold text-purple-400">
            Stage 5: Scenario Engine • Adversarial Simulation
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Future Scenarios &amp; Stress-Testing
          </h2>
          <span className="text-xs text-zinc-400 font-mono hidden sm:inline-block">
            Future Explorer &amp; Trajectory Forecasts • Three-Scenario Comparative Matrix
          </span>
        </div>

        <div className="text-xs text-zinc-400 bg-zinc-800/80 px-3 py-1.5 rounded-lg border border-zinc-700 font-mono">
          3 Distinct Forward Pathways
        </div>
      </div>

      {/* Uncertainty Disclaimer Banner */}
      <div className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-3.5 text-xs text-amber-200/90 flex items-start gap-2.5">
        <svg
          className="h-4 w-4 text-amber-400 shrink-0 mt-0.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <p className="leading-relaxed">
          <strong className="text-amber-300">Epistemic Uncertainty Calibration:</strong> Scenario distribution weights reflect qualitative generative heuristics and must not be interpreted as calibrated actuarial probabilities. Real-world downside risk requires explicit operational hedging.
        </p>
      </div>

      {/* Scenario Selector Tabs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {scenarioSet.scenarios.map((sc) => {
          const badge = getScenarioBadge(sc.scenario_type);
          const isSelected = activeScenario?.id === sc.id;

          return (
            <button
              key={sc.id}
              onClick={() => setActiveScenarioId(sc.id)}
              className={`cursor-pointer text-left p-4 rounded-xl border transition-all ${
                isSelected
                  ? `bg-zinc-800/90 text-white ${badge.border} shadow-md ring-1 ring-zinc-500/30`
                  : "bg-zinc-950/50 text-zinc-400 border-zinc-800 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span
                  className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border ${badge.bg}`}
                >
                  {badge.name}
                </span>
                <span className="text-[10px] font-mono text-zinc-500" title="Model generative weight">
                  Weight: {Math.round(sc.probability * 100)}%
                </span>
              </div>
              <h3 className="text-sm font-semibold text-zinc-200 truncate" title={sc.name}>
                {sc.name}
              </h3>
              <p className="text-xs text-zinc-400 mt-1 line-clamp-2 leading-relaxed">
                {sc.narrative}
              </p>
            </button>
          );
        })}
      </div>

      {/* Detailed View of Active Scenario */}
      {activeScenario && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 sm:p-6 space-y-6">
          <div className="space-y-2">
            <h3 className="text-lg font-bold text-white">
              {activeScenario.name}
            </h3>
            <p className="text-xs text-zinc-300 leading-relaxed max-w-4xl">
              {activeScenario.narrative}
            </p>
          </div>

          {/* Timeline and Events */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Key Events */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
              <span className="text-[11px] font-mono uppercase text-zinc-400 font-semibold block">
                Pivotal Events &amp; Impact
              </span>
              <div className="space-y-2">
                {(activeScenario.key_events || []).map((ke) => (
                  <div key={ke.id} className="text-xs space-y-0.5 border-l-2 border-zinc-700 pl-3 py-0.5">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-zinc-200">{ke.title}</span>
                      <span className="text-[10px] font-mono text-zinc-500">{ke.timeframe}</span>
                    </div>
                    <p className="text-zinc-400 text-[11px] leading-relaxed">{ke.description}</p>
                    <div className="text-[10px] text-zinc-500 font-mono">
                      Impact: {ke.impact_on_decision}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Timeline Milestones */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
              <span className="text-[11px] font-mono uppercase text-zinc-400 font-semibold block">
                Verification Milestones
              </span>
              <div className="space-y-2">
                {(activeScenario.timeline || []).map((ms) => (
                  <div key={ms.id} className="text-xs space-y-0.5 border-l-2 border-purple-800/80 pl-3 py-0.5">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-zinc-200">{ms.title}</span>
                      <span className="text-[10px] font-mono text-purple-400">{ms.time_horizon}</span>
                    </div>
                    <p className="text-zinc-400 text-[11px] leading-relaxed">{ms.description}</p>
                    <div className="text-[10px] text-zinc-400">
                      Expected: <span className="text-zinc-300">{ms.expected_outcome}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Risks & Opportunities */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            <div className="bg-rose-950/10 rounded-xl p-4 border border-rose-900/30 space-y-2">
              <span className="text-[11px] font-mono uppercase text-rose-400 font-semibold flex items-center gap-1.5">
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                Identified Downside Risks
              </span>
              <ul className="text-xs text-zinc-300 space-y-1">
                {(activeScenario.risks || []).map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-rose-500 font-bold">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-emerald-950/10 rounded-xl p-4 border border-emerald-900/30 space-y-2">
              <span className="text-[11px] font-mono uppercase text-emerald-400 font-semibold flex items-center gap-1.5">
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                Strategic Opportunities
              </span>
              <ul className="text-xs text-zinc-300 space-y-1">
                {(activeScenario.opportunities || []).map((o, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-emerald-500 font-bold">•</span>
                    <span>{o}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
