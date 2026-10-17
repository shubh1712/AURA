"use client";

import React, { useState } from "react";
import type { AnalysisResponse, ScenarioType } from "@/types";
import { FutureExplorerTree } from "../scenario/FutureExplorerTree";
import { ScenarioComparisonChart } from "../charts/ScenarioComparisonChart";
import { ScenarioProbabilitySpectrum } from "../charts/ScenarioProbabilitySpectrum";
import { ResilienceDriverChart } from "../charts/ResilienceDriverChart";
import { WhatIfDashboard } from "../simulation/WhatIfDashboard";
import { SimulationUnavailableBanner } from "../simulation/SimulationUnavailableBanner";
import { ScenarioUnavailableBanner } from "../scenario/ScenarioUnavailableBanner";
import { ResilienceUnavailableBanner } from "../resilience/ResilienceUnavailableBanner";
import { sortScenariosCanonical } from "@/lib/scenarioHelpers";
import { truncateOnWordBoundary } from "@/lib/formatters";

interface ExploreViewProps {
  result: AnalysisResponse;
  ownerId?: string | null;
}

export function ExploreView({ result, ownerId }: ExploreViewProps) {
  const [selectedScenarioType, setSelectedScenarioType] = useState<ScenarioType>("base_case");

  const hasValidScenarios = Boolean(
    result.scenarios &&
    result.scenarios.scenarios &&
    result.scenarios.scenarios.length === 3
  );

  const hasValidResilience = Boolean(result.resilience);
  const hasDecisionModel = Boolean(result.decision_model);
  const hasValidRecommendation = Boolean(result.recommendation);

  const canonicalScenarios = hasValidScenarios && result.scenarios
    ? sortScenariosCanonical(result.scenarios.scenarios)
    : [];

  const hasSimulationPrerequisites =
    hasDecisionModel && hasValidRecommendation && hasValidScenarios;

  const isScenarioUnavailable =
    !hasValidScenarios &&
    (result.scenario_status === "unavailable" ||
      (result.status === "partial_success" && Boolean(result.scenario_error)));

  const isResilienceUnavailable =
    !hasValidResilience &&
    (result.resilience_status === "unavailable" ||
      (result.status === "partial_success" && Boolean(result.resilience_error)));

  return (
    <div className="space-y-7" aria-label="Explore Scenarios, Simulation, and Resilience">
      {/* 1. Header Banner */}
      <div className="rounded-2xl border border-zinc-800 bg-gradient-to-r from-zinc-950 via-zinc-900/40 to-zinc-950 p-6 sm:p-7 space-y-2 text-zinc-100 shadow-sm print:bg-white print:border-zinc-300 print:text-black">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono uppercase tracking-wider text-sky-400 font-semibold print:text-zinc-700">
            Trajectory &amp; Sensitivity Explorer
          </span>
          <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
        </div>
        <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight print:text-black">
          Future Explorer &amp; Trajectory Forecasts
        </h3>
        <p className="text-xs sm:text-sm text-zinc-400 max-w-3xl font-sans leading-relaxed print:text-zinc-700">
          Stress-test the decision across optimistic, base-case, and pessimistic trajectories.
          Tune controllable parameters in the simulation engine to evaluate mathematical resilience under changing conditions.
        </p>
      </div>

      {/* 2. Stage 5: Scenario Comparison Chart & Concise Cards */}
      {hasValidScenarios && (
        <section
          id="section-future-explorer"
          aria-label="Future Explorer and Scenario Engine"
          className="space-y-6"
        >
          {/* Promoted Interactive Future Explorer Tree Canvas */}
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-5 sm:p-6 space-y-4 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 pb-3 border-b border-zinc-800/80">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400 font-semibold">
                    Interactive Projection Canvas
                  </span>
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                </div>
                <h4 className="text-base sm:text-lg font-bold text-white tracking-tight mt-0.5">
                  Interactive Future Scenario Tree
                </h4>
                <p className="text-xs text-zinc-400 mt-1 max-w-2xl font-sans leading-relaxed">
                  Explore cascading downstream implications and branch probabilities deterministically derived by AURA.
                  Select any trajectory node or tab below to inspect milestones, causal events, and vulnerabilities.
                </p>
              </div>
              <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2.5 py-1 rounded border border-zinc-800 shrink-0">
                Pan &amp; Zoom Enabled
              </span>
            </div>

            <FutureExplorerTree
              decisionTitle={result.decision_model?.decision?.summary || result.question}
              scenarios={canonicalScenarios}
              selectedScenarioType={selectedScenarioType}
              onSelectScenario={setSelectedScenarioType}
            />
          </div>

          {/* Proportional Likelihood Spectrum Visualization */}
          <ScenarioProbabilitySpectrum
            scenarios={canonicalScenarios}
            selectedScenarioType={selectedScenarioType}
            onSelectScenario={setSelectedScenarioType}
          />

          <ScenarioComparisonChart
            scenarios={canonicalScenarios}
            selectedScenarioType={selectedScenarioType}
            onSelectScenario={setSelectedScenarioType}
          />

          {/* Three Scenario Cards with full vulnerability details and visual balance */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-stretch">
            {canonicalScenarios.map((scen) => {
              const isSelected = selectedScenarioType === scen.scenario_type;
              const conciseSummary = scen.narrative;
              const oppsCount = (scen.opportunities || []).length;
              const risksCount = (scen.risks || []).length;
              const totalDrivers = oppsCount + risksCount;
              const oppPct = totalDrivers > 0 ? Math.round((oppsCount / totalDrivers) * 100) : 50;

              return (
                <div
                  key={scen.scenario_type}
                  onClick={() => setSelectedScenarioType(scen.scenario_type)}
                  className={`rounded-xl border p-4 sm:p-5 space-y-3.5 cursor-pointer transition-all flex flex-col justify-between h-full ${
                    isSelected
                      ? "border-sky-500 bg-zinc-900/80 shadow-md ring-1 ring-sky-500/30"
                      : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700"
                  } print:border-zinc-300 print:bg-zinc-50`}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedScenarioType(scen.scenario_type);
                    }
                  }}
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs uppercase tracking-wider font-bold text-zinc-200 print:text-black">
                        {scen.name}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-400 bg-zinc-900 px-1.5 py-0.5 rounded border border-zinc-800 print:bg-white print:border-zinc-300 shrink-0">
                        {Math.round((scen.probability || 0) * 100)}% Prob
                      </span>
                    </div>

                    <p className="text-xs text-zinc-300 font-sans leading-relaxed print:text-zinc-800 break-words">
                      {conciseSummary}
                    </p>

                    {/* Opportunity vs Risk Drivers Ratio Bar */}
                    {totalDrivers > 0 && (
                      <div className="pt-2 border-t border-zinc-800/60 space-y-1 text-[10px] font-mono">
                        <div className="flex items-center justify-between text-zinc-400">
                          <span className="text-emerald-400 font-medium">
                            {oppsCount} Upside {oppsCount === 1 ? "Driver" : "Drivers"}
                          </span>
                          <span className="text-rose-400 font-medium">
                            {risksCount} {risksCount === 1 ? "Vulnerability" : "Vulnerabilities"}
                          </span>
                        </div>
                        <div
                          className="h-1.5 w-full bg-zinc-900 rounded-full overflow-hidden flex border border-zinc-800"
                          role="meter"
                          aria-label="Upside vs Risk balance"
                          aria-valuenow={oppPct}
                          aria-valuemin={0}
                          aria-valuemax={100}
                        >
                          <div
                            style={{ width: `${oppPct}%` }}
                            className="bg-emerald-500 h-full transition-all"
                            title={`${oppsCount} Upside Drivers (${oppPct}%)`}
                          />
                          <div
                            style={{ width: `${100 - oppPct}%` }}
                            className="bg-rose-500 h-full transition-all"
                            title={`${risksCount} Vulnerabilities (${100 - oppPct}%)`}
                          />
                        </div>
                      </div>
                    )}

                    {/* Top Vulnerabilities with natural wrapping and complete text */}
                    {scen.risks && scen.risks.length > 0 && (
                      <div className="pt-2.5 border-t border-zinc-800/60 space-y-1.5 text-[11px] print:border-zinc-300">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold block print:text-zinc-800">
                          Top Vulnerabilities:
                        </span>
                        <ul className="space-y-1.5 list-disc list-inside text-zinc-300 print:text-zinc-700">
                          {scen.risks.map((r, rIdx) => (
                            <li key={rIdx} className="leading-relaxed break-words">
                              {r}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  <div className="pt-2 mt-auto border-t border-zinc-800/40 text-[10px] font-mono text-zinc-500 print:text-zinc-600">
                    Epistemic Caveat: Subject to baseline input stability.
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {isScenarioUnavailable && (
        <section aria-label="Scenario Unavailable Notice">
          <ScenarioUnavailableBanner scenarioError={result.scenario_error} />
        </section>
      )}

      {/* 3. Stage 6: Decision Resilience & Stress-Test Analysis */}
      {hasValidResilience && result.resilience && (
        <section
          id="section-resilience-dashboard"
          aria-label="Decision Resilience &amp; Stress-Test Analysis"
          className="space-y-5"
        >
          <div className="pb-1">
            <h3 className="text-lg font-semibold text-white tracking-tight print:text-black">
              Decision Resilience &amp; Stress-Test Analysis
            </h3>
          </div>
          <ResilienceDriverChart report={result.resilience} />
        </section>
      )}

      {isResilienceUnavailable && (
        <section aria-label="Resilience Evaluation Notice">
          <ResilienceUnavailableBanner resilienceError={result.resilience_error} />
        </section>
      )}

      {/* 4. What-if Simulation Engine (Interactive Parameter Testing) */}
      <section aria-label="What-if Simulation" className="space-y-4 pt-2">
        <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 print:border-zinc-300">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-purple-400 font-semibold print:text-zinc-700">
              Interactive Parameter Testing
            </span>
            <h4 className="text-sm sm:text-base font-semibold text-white tracking-tight mt-0.5 print:text-black">
              Deterministic What-If Simulation
            </h4>
          </div>
          <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800 print:bg-white print:border-zinc-300">
            Causal Sensitivity
          </span>
        </div>

        {hasSimulationPrerequisites ? (
          <WhatIfDashboard
            analysisId={result.analysis_id}
            ownerId={ownerId || null}
          />
        ) : (
          <SimulationUnavailableBanner
            historical={!hasValidScenarios && !result.scenario_status}
            reason={
              !hasDecisionModel
                ? "Decision Model (Stage 1) is required for what-if simulation."
                : !hasValidRecommendation
                ? (result.recommendation_error || "Decision Recommendation (Stage 4) is required.")
                : !hasValidScenarios
                ? (result.scenario_error || "Future Scenarios (Stage 5) are required.")
                : null
            }
          />
        )}
      </section>
    </div>
  );
}
