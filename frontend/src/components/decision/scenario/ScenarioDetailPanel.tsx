"use client";

import React, { useState } from "react";
import type {
  FutureScenario,
  EvidencePackage,
  DecisionModel,
} from "@/types";
import {
  getScenarioConfig,
  formatScenarioProbability,
  resolveScenarioEvidenceItem,
  resolveScenarioAssumption,
  resolveScenarioConstraint,
  resolveScenarioGap,
} from "@/lib/scenarioHelpers";

interface ScenarioDetailPanelProps {
  scenario: FutureScenario;
  evidencePackage?: EvidencePackage | null;
  decisionModel?: DecisionModel | null;
}

type DetailTab = "narrative" | "events" | "timeline" | "traceability";

export function ScenarioDetailPanel({
  scenario,
  evidencePackage,
  decisionModel,
}: ScenarioDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>("narrative");
  const config = getScenarioConfig(scenario.scenario_type);
  const formattedProb = formatScenarioProbability(scenario.probability);

  const hasKeyEvents = scenario.key_events && scenario.key_events.length > 0;
  const hasTimeline = scenario.timeline && scenario.timeline.length > 0;
  const hasRisks = scenario.risks && scenario.risks.length > 0;
  const hasOpportunities = scenario.opportunities && scenario.opportunities.length > 0;

  const hasEvidence =
    scenario.supporting_evidence_item_ids &&
    scenario.supporting_evidence_item_ids.length > 0;
  const hasAssumptions =
    scenario.relevant_assumption_ids &&
    scenario.relevant_assumption_ids.length > 0;
  const hasConstraints =
    scenario.relevant_constraint_ids &&
    scenario.relevant_constraint_ids.length > 0;
  const hasGaps =
    scenario.relevant_gap_ids && scenario.relevant_gap_ids.length > 0;
  const hasTraceability =
    hasEvidence || hasAssumptions || hasConstraints || hasGaps;

  return (
    <article
      aria-label={`${config.label} Scenario Details`}
      className={`rounded-xl border ${config.borderClass} bg-zinc-950/70 p-6 sm:p-7 space-y-6 text-zinc-100 shadow-md print:bg-white print:border-zinc-300 print:text-black`}
    >
      {/* 1. Scenario Header & Probability Estimate */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div className="space-y-1.5 max-w-3xl">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span
              className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-0.5 text-xs font-mono font-medium ${config.badgeClass} print:bg-zinc-100 print:text-black print:border-zinc-300`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${config.dotClass}`} />
              {config.label.toUpperCase()} TRAJECTORY
            </span>
            <span className="text-xs font-mono text-zinc-500 print:text-zinc-600">
              ID: {scenario.id}
            </span>
          </div>

          <h3 className="text-xl sm:text-2xl font-bold tracking-tight text-white print:text-black">
            {scenario.name}
          </h3>

          <p className="text-xs text-zinc-400 print:text-zinc-600 italic">
            {config.tagline}
          </p>
        </div>

        {/* Probability Card with Modeled Estimate Disclaimer */}
        <div className="sm:text-right shrink-0 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 sm:min-w-[190px] print:bg-zinc-50 print:border-zinc-300">
          <span className="block text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600">
            Modeled Probability
          </span>
          <div className="flex sm:justify-end items-baseline gap-1 mt-0.5">
            <span
              className={`text-2xl sm:text-3xl font-extrabold font-mono ${config.textClass} print:text-black`}
            >
              {formattedProb}
            </span>
          </div>
          <span className="block text-[10px] text-zinc-500 print:text-zinc-600 mt-1 leading-tight">
            *Modeled scenario estimate, not a statistical guarantee.
          </span>
        </div>
      </div>

      {/* 2. Accessible Tab Navigation (Desktop / Mobile) - Always visible on print as expanded sections */}
      <div className="flex items-center gap-2 border-b border-zinc-800/70 pb-2 print:hidden overflow-x-auto">
        <button
          type="button"
          onClick={() => setActiveTab("narrative")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer whitespace-nowrap ${
            activeTab === "narrative"
              ? "bg-zinc-800 text-white border border-zinc-700 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
          }`}
          aria-pressed={activeTab === "narrative"}
        >
          Narrative &amp; Dynamics
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("events")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer whitespace-nowrap ${
            activeTab === "events"
              ? "bg-zinc-800 text-white border border-zinc-700 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
          }`}
          aria-pressed={activeTab === "events"}
        >
          Key Events ({scenario.key_events?.length ?? 0})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("timeline")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer whitespace-nowrap ${
            activeTab === "timeline"
              ? "bg-zinc-800 text-white border border-zinc-700 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
          }`}
          aria-pressed={activeTab === "timeline"}
        >
          Timeline Roadmaps ({scenario.timeline?.length ?? 0})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("traceability")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer whitespace-nowrap ${
            activeTab === "traceability"
              ? "bg-zinc-800 text-white border border-zinc-700 shadow-sm"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
          }`}
          aria-pressed={activeTab === "traceability"}
        >
          Evidence Grounding
        </button>
      </div>

      {/* 3. Tab Contents: Narrative & Opportunities / Risks */}
      <div className={`${activeTab === "narrative" ? "block" : "hidden print:block"} space-y-6`}>
        {/* Scenario Narrative */}
        <section aria-label="Scenario Narrative" className="space-y-2">
          <h4 className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-semibold">
            Trajectory Narrative
          </h4>
          <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-4 text-sm sm:text-base leading-relaxed text-zinc-200 print:text-black print:bg-zinc-50 print:border-zinc-300 font-sans">
            {scenario.narrative}
          </div>
        </section>

        {/* Opportunities and Risks Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Strategic Opportunities */}
          <section
            aria-label="Scenario Opportunities"
            className="rounded-lg border border-emerald-900/50 bg-emerald-950/15 p-4 sm:p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300"
          >
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <h4 className="text-xs font-mono uppercase tracking-wider text-emerald-300 print:text-black font-semibold">
                Strategic Opportunities ({scenario.opportunities?.length ?? 0})
              </h4>
            </div>
            {hasOpportunities ? (
              <ul className="space-y-2 text-xs sm:text-sm text-zinc-300 print:text-black">
                {scenario.opportunities.map((opp, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold shrink-0 mt-0.5">
                      ✓
                    </span>
                    <span className="leading-snug">{opp}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-zinc-500 italic">
                No specific upside opportunities projected for this trajectory.
              </p>
            )}
          </section>

          {/* Operational Risks */}
          <section
            aria-label="Scenario Risks"
            className="rounded-lg border border-rose-900/50 bg-rose-950/15 p-4 sm:p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300"
          >
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-rose-400" />
              <h4 className="text-xs font-mono uppercase tracking-wider text-rose-300 print:text-black font-semibold">
                Operational &amp; Strategic Risks ({scenario.risks?.length ?? 0})
              </h4>
            </div>
            {hasRisks ? (
              <ul className="space-y-2 text-xs sm:text-sm text-zinc-300 print:text-black">
                {scenario.risks.map((risk, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-rose-400 font-bold shrink-0 mt-0.5">
                      ⚠
                    </span>
                    <span className="leading-snug">{risk}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-zinc-500 italic">
                No specific acute risks projected for this trajectory.
              </p>
            )}
          </section>
        </div>
      </div>

      {/* 4. Tab Contents: Key Trigger Events */}
      <div className={`${activeTab === "events" ? "block" : "hidden print:block"} space-y-4`}>
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-semibold">
            Key Events &amp; Decision Triggers
          </h4>
          <span className="text-xs font-mono text-zinc-500">
            {scenario.key_events?.length ?? 0} Critical Milestones
          </span>
        </div>

        {hasKeyEvents ? (
          <div className="space-y-3">
            {scenario.key_events.map((evt) => (
              <div
                key={evt.id}
                className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-2 print:bg-zinc-50 print:border-zinc-300 text-xs sm:text-sm"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                      {evt.id}
                    </span>
                    <h5 className="font-semibold text-white print:text-black">
                      {evt.title}
                    </h5>
                  </div>
                  <span className="font-mono text-xs text-zinc-400 print:text-zinc-600">
                    Window: {evt.timeframe}
                  </span>
                </div>

                <p className="text-zinc-300 print:text-black leading-relaxed">
                  {evt.description}
                </p>

                {(evt.trigger_condition || evt.impact_on_decision) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-zinc-800/60 print:border-zinc-300 text-xs">
                    {evt.trigger_condition && (
                      <div>
                        <span className="font-mono text-zinc-400 font-semibold">
                          Trigger Condition:{" "}
                        </span>
                        <span className="text-zinc-300 print:text-zinc-800">
                          {evt.trigger_condition}
                        </span>
                      </div>
                    )}
                    {evt.impact_on_decision && (
                      <div>
                        <span className="font-mono text-zinc-400 font-semibold">
                          Decision Impact:{" "}
                        </span>
                        <span className="text-zinc-300 print:text-zinc-800">
                          {evt.impact_on_decision}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-800 p-4 text-center text-xs text-zinc-500">
            No key trigger events registered for this scenario.
          </div>
        )}
      </div>

      {/* 5. Tab Contents: Timeline Milestones */}
      <div className={`${activeTab === "timeline" ? "block" : "hidden print:block"} space-y-4`}>
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-semibold">
            Projected Timeline &amp; Expected Outcomes
          </h4>
          <span className="text-xs font-mono text-zinc-500">
            {scenario.timeline?.length ?? 0} Milestones
          </span>
        </div>

        {hasTimeline ? (
          <div className="relative pl-6 sm:pl-8 space-y-4 before:absolute before:left-2.5 sm:before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-zinc-800 print:before:bg-zinc-300">
            {scenario.timeline.map((ms) => (
              <div
                key={ms.id}
                className="relative rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-2 print:bg-zinc-50 print:border-zinc-300 text-xs sm:text-sm"
              >
                {/* Timeline node marker */}
                <div
                  className={`absolute -left-[27px] sm:-left-[35px] top-4 h-3.5 w-3.5 rounded-full border-2 border-zinc-950 ${config.dotClass} shadow`}
                />

                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                      {ms.id}
                    </span>
                    <h5 className="font-semibold text-white print:text-black">
                      {ms.title}
                    </h5>
                  </div>
                  <span className="font-mono text-xs text-sky-400 print:text-zinc-700 capitalize">
                    {ms.time_horizon.replace("_", " ")}
                  </span>
                </div>

                <p className="text-zinc-300 print:text-black leading-relaxed">
                  {ms.description}
                </p>

                <div className="pt-2 border-t border-zinc-800/60 print:border-zinc-300 text-xs">
                  <span className="font-mono text-emerald-400 print:text-black font-semibold">
                    Expected Outcome:{" "}
                  </span>
                  <span className="text-zinc-200 print:text-zinc-900 font-medium">
                    {ms.expected_outcome}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-800 p-4 text-center text-xs text-zinc-500">
            No timeline milestones registered for this scenario.
          </div>
        )}
      </div>

      {/* 6. Tab Contents: Epistemic Evidence Grounding */}
      <div className={`${activeTab === "traceability" ? "block" : "hidden print:block"} space-y-5`}>
        <div className="space-y-1">
          <h4 className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 font-semibold">
            Epistemic Evidence &amp; Model Grounding
          </h4>
          <p className="text-xs text-zinc-400 print:text-zinc-600">
            Authoritative links to upstream evidence items, assumptions, constraints, and identified gaps.
          </p>
        </div>

        {hasTraceability ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Supporting Evidence Items */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-2.5 print:bg-zinc-50 print:border-zinc-300">
              <span className="text-xs font-mono font-semibold text-zinc-300 print:text-black">
                Supporting Evidence Items ({scenario.supporting_evidence_item_ids?.length ?? 0})
              </span>
              {hasEvidence ? (
                <div className="space-y-1.5">
                  {scenario.supporting_evidence_item_ids.map((id) => {
                    const resolved = resolveScenarioEvidenceItem(evidencePackage, id);
                    return (
                      <div
                        key={id}
                        className="rounded border border-zinc-800/80 bg-zinc-950/60 p-2 text-xs text-zinc-300 print:bg-white print:border-zinc-200"
                      >
                        <span className="font-mono text-sky-400 font-semibold mr-1.5">
                          {id}
                        </span>
                        {resolved ? (
                          <span className="text-zinc-200">{resolved.summary || resolved.content}</span>
                        ) : (
                          <span className="text-zinc-500 italic">Authoritative Evidence Reference</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 italic">None referenced.</p>
              )}
            </div>

            {/* Relevant Tested Assumptions */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-2.5 print:bg-zinc-50 print:border-zinc-300">
              <span className="text-xs font-mono font-semibold text-zinc-300 print:text-black">
                Tested Assumptions ({scenario.relevant_assumption_ids?.length ?? 0})
              </span>
              {hasAssumptions ? (
                <div className="space-y-1.5">
                  {scenario.relevant_assumption_ids.map((id) => {
                    const resolved = resolveScenarioAssumption(decisionModel, id);
                    return (
                      <div
                        key={id}
                        className="rounded border border-zinc-800/80 bg-zinc-950/60 p-2 text-xs text-zinc-300 print:bg-white print:border-zinc-200"
                      >
                        <span className="font-mono text-amber-400 font-semibold mr-1.5">
                          {id}
                        </span>
                        {resolved ? (
                          <span className="text-zinc-200">{resolved.statement}</span>
                        ) : (
                          <span className="text-zinc-500 italic">Decision Model Assumption</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 italic">None referenced.</p>
              )}
            </div>

            {/* Relevant Operational Constraints */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-2.5 print:bg-zinc-50 print:border-zinc-300">
              <span className="text-xs font-mono font-semibold text-zinc-300 print:text-black">
                Operational Constraints ({scenario.relevant_constraint_ids?.length ?? 0})
              </span>
              {hasConstraints ? (
                <div className="space-y-1.5">
                  {scenario.relevant_constraint_ids.map((id) => {
                    const resolved = resolveScenarioConstraint(decisionModel, id);
                    return (
                      <div
                        key={id}
                        className="rounded border border-zinc-800/80 bg-zinc-950/60 p-2 text-xs text-zinc-300 print:bg-white print:border-zinc-200"
                      >
                        <span className="font-mono text-rose-400 font-semibold mr-1.5">
                          {id}
                        </span>
                        {resolved ? (
                          <span className="text-zinc-200">{resolved.name}: {resolved.description}</span>
                        ) : (
                          <span className="text-zinc-500 italic">Decision Constraint</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 italic">None referenced.</p>
              )}
            </div>

            {/* Relevant Evidence Gaps / Uncertainties */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-2.5 print:bg-zinc-50 print:border-zinc-300">
              <span className="text-xs font-mono font-semibold text-zinc-300 print:text-black">
                Evidence Gaps &amp; Uncertainties ({scenario.relevant_gap_ids?.length ?? 0})
              </span>
              {hasGaps ? (
                <div className="space-y-1.5">
                  {scenario.relevant_gap_ids.map((id) => {
                    const resolved = resolveScenarioGap(evidencePackage, id);
                    return (
                      <div
                        key={id}
                        className="rounded border border-zinc-800/80 bg-zinc-950/60 p-2 text-xs text-zinc-300 print:bg-white print:border-zinc-200"
                      >
                        <span className="font-mono text-purple-400 font-semibold mr-1.5">
                          {id}
                        </span>
                        {resolved ? (
                          <span className="text-zinc-200">{resolved.description}</span>
                        ) : (
                          <span className="text-zinc-500 italic">Evidence Gap</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 italic">None referenced.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-800 p-4 text-center text-xs text-zinc-500">
            No upstream evidence items or model assumptions explicitly linked to this scenario.
          </div>
        )}
      </div>
    </article>
  );
}
