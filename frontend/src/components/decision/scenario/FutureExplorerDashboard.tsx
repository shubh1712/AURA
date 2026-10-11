"use client";

import React, { useState } from "react";
import type {
  ScenarioSet,
  ScenarioType,
  DecisionModel,
  EvidencePackage,
} from "@/types";
import { FutureExplorerTree } from "./FutureExplorerTree";
import { ScenarioDetailPanel } from "./ScenarioDetailPanel";
import {
  getScenarioConfig,
  formatScenarioProbability,
  sortScenariosCanonical,
} from "@/lib/scenarioHelpers";

interface FutureExplorerDashboardProps {
  scenarioSet: ScenarioSet;
  decisionModel?: DecisionModel | null;
  evidencePackage?: EvidencePackage | null;
  decisionTitle?: string;
}

export function FutureExplorerDashboard({
  scenarioSet,
  decisionModel,
  evidencePackage,
  decisionTitle = "Strategic Decision",
}: FutureExplorerDashboardProps) {
  const [selectedType, setSelectedType] = useState<ScenarioType>("base_case");
  const [viewMode, setViewMode] = useState<"tree" | "matrix">("tree");

  const canonicalScenarios = sortScenariosCanonical(scenarioSet.scenarios);
  const activeScenario =
    canonicalScenarios.find((s) => s.scenario_type === selectedType) ||
    canonicalScenarios[0];

  return (
    <section
      aria-label="Future Explorer and Scenario Engine"
      id="section-future-explorer"
      className="space-y-6"
    >
      {/* 1. Header Card with Executive Synthesis */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-7 space-y-5 text-zinc-100 shadow-sm print:bg-white print:border-zinc-300 print:text-black">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 pb-4 border-b border-zinc-800/80 print:border-zinc-300">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-wider font-semibold text-sky-400 print:text-zinc-700">
                Stage 5: Scenario Engine
              </span>
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
            </div>
            <h2 className="text-xl font-semibold text-white print:text-black tracking-tight mt-0.5">
              Future Explorer &amp; Trajectory Forecasts
            </h2>
          </div>

          <div className="flex items-center gap-2 print:hidden">
            {/* View Mode Switcher */}
            <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950/70 p-1 text-xs">
              <button
                type="button"
                onClick={() => setViewMode("tree")}
                className={`px-3 py-1 rounded-md font-medium transition-colors cursor-pointer ${
                  viewMode === "tree"
                    ? "bg-zinc-800 text-white shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
                aria-pressed={viewMode === "tree"}
              >
                Tree View
              </button>
              <button
                type="button"
                onClick={() => setViewMode("matrix")}
                className={`px-3 py-1 rounded-md font-medium transition-colors cursor-pointer ${
                  viewMode === "matrix"
                    ? "bg-zinc-800 text-white shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
                aria-pressed={viewMode === "matrix"}
              >
                Comparison Matrix
              </button>
            </div>
          </div>
        </div>

        {/* Executive Synthesis Summary */}
        <div className="space-y-2">
          <label className="block text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-semibold">
            Scenario Portfolio Synthesis
          </label>
          <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/50 p-4 text-sm sm:text-base text-zinc-200 print:text-black print:bg-zinc-50 print:border-zinc-300 leading-relaxed font-sans">
            {scenarioSet.summary}
          </div>
        </div>

        {/* Modeled Estimate Epistemic Notice */}
        <div className="flex items-start gap-2.5 rounded-lg border border-sky-900/40 bg-sky-950/20 p-3 text-xs text-sky-200 print:bg-zinc-50 print:border-zinc-300 print:text-black">
          <span className="text-sky-400 font-bold text-sm shrink-0">ℹ</span>
          <p className="leading-relaxed">
            <span className="font-semibold text-white print:text-black">
              Modeled Scenario Estimates:
            </span>{" "}
            Probabilities, trigger conditions, and projected milestones are derived from epistemic evidence and boardroom deliberation. They represent bounded stress-tests and planning horizons, not statistical guarantees.
          </p>
        </div>
      </div>

      {/* 2. Interactive Future Tree Canvas (Visible when viewMode === 'tree') */}
      {viewMode === "tree" && (
        <div className="space-y-6">
          <FutureExplorerTree
            decisionTitle={decisionTitle}
            scenarios={canonicalScenarios}
            selectedScenarioType={selectedType}
            onSelectScenario={setSelectedType}
          />

          {/* Drilldown detail panel for selected scenario */}
          <ScenarioDetailPanel
            scenario={activeScenario}
            evidencePackage={evidencePackage}
            decisionModel={decisionModel}
          />
        </div>
      )}

      {/* 3. Comparison Matrix View (Visible when viewMode === 'matrix' or during print) */}
      <div
        className={`${
          viewMode === "matrix" ? "block" : "hidden print:block"
        } space-y-6`}
      >
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-4 text-zinc-100 print:bg-white print:border-zinc-300 print:text-black">
          <div className="flex items-center justify-between pb-3 border-b border-zinc-800 print:border-zinc-200">
            <h3 className="text-base font-bold text-white print:text-black">
              Three-Scenario Comparative Matrix
            </h3>
            <span className="text-xs font-mono text-zinc-400 print:text-zinc-600">
              Canonical Trajectories
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {canonicalScenarios.map((scen) => {
              const cfg = getScenarioConfig(scen.scenario_type);
              const isSelected = selectedType === scen.scenario_type;
              const prob = formatScenarioProbability(scen.probability);

              return (
                <div
                  key={scen.scenario_type}
                  className={`rounded-xl border p-4 space-y-3 transition-all ${
                    isSelected
                      ? `${cfg.activeBorderClass} ${cfg.activeBgClass}`
                      : `${cfg.borderClass} ${cfg.bgClass}`
                  } print:bg-zinc-50 print:border-zinc-300`}
                >
                  <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 print:border-zinc-200">
                    <span
                      className={`text-xs font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded ${cfg.badgeClass} print:bg-zinc-100 print:text-black`}
                    >
                      {cfg.label}
                    </span>
                    <span
                      className={`text-lg font-mono font-extrabold ${cfg.textClass} print:text-black`}
                    >
                      {prob}
                    </span>
                  </div>

                  <h4 className="text-sm font-bold text-white print:text-black">
                    {scen.name}
                  </h4>

                  <p className="text-xs text-zinc-300 print:text-zinc-800 line-clamp-4 leading-relaxed">
                    {scen.narrative}
                  </p>

                  <div className="pt-2 border-t border-zinc-800/60 print:border-zinc-200 space-y-2 text-xs">
                    <div>
                      <span className="font-mono text-emerald-400 font-semibold">
                        Opportunities:{" "}
                      </span>
                      <span className="text-zinc-300 print:text-zinc-800">
                        {scen.opportunities?.length ?? 0}
                      </span>
                    </div>
                    <div>
                      <span className="font-mono text-rose-400 font-semibold">
                        Risks:{" "}
                      </span>
                      <span className="text-zinc-300 print:text-zinc-800">
                        {scen.risks?.length ?? 0}
                      </span>
                    </div>
                    <div>
                      <span className="font-mono text-sky-400 font-semibold">
                        Milestones:{" "}
                      </span>
                      <span className="text-zinc-300 print:text-zinc-800">
                        {scen.timeline?.length ?? 0}
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setSelectedType(scen.scenario_type);
                      setViewMode("tree");
                    }}
                    className="w-full mt-2 rounded-lg border border-zinc-700 bg-zinc-800/80 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer print:hidden"
                  >
                    Drill Down Trajectory &rarr;
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* In matrix mode, show detail panel for currently selected scenario */}
        <ScenarioDetailPanel
          scenario={activeScenario}
          evidencePackage={evidencePackage}
          decisionModel={decisionModel}
        />
      </div>
    </section>
  );
}
