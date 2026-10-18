"use client";

import React, { useState } from "react";
import type { AnalysisResponse } from "@/types";
import { DecisionModelSummary } from "../DecisionModelSummary";
import { EvidenceOverview } from "../evidence/EvidenceOverview";
import { RequirementList } from "../evidence/RequirementList";
import { EvidenceGapsSection } from "../evidence/EvidenceGapsSection";
import { SourceList } from "../evidence/SourceList";
import { ReasoningBoardSection } from "../boardroom/ReasoningBoardSection";
import { RecommendationDashboard } from "../recommendation/RecommendationDashboard";
import { FutureExplorerDashboard } from "../scenario/FutureExplorerDashboard";
import { ResilienceDashboard } from "../resilience/ResilienceDashboard";
import { EvidenceQualityDistribution } from "../charts/EvidenceQualityDistribution";
import { StageProgressionTracker } from "../charts/StageProgressionTracker";
import { deriveStageProgression } from "@/lib/visualIntelligence";
import { formatEnumLabel, formatProvenance } from "@/lib/formatters";

interface DetailsViewProps {
  result: AnalysisResponse;
}

export function DetailsView({ result }: DetailsViewProps) {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    stage1: false,
    stage2: false,
    stage3: false,
    stage4: false,
    stage5: false,
    stage6: false,
    assumptions: true,
    diagnostics: false,
  });

  const toggleSection = (key: string) => {
    setOpenSections((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const expandAll = () => {
    setOpenSections({
      stage1: true,
      stage2: true,
      stage3: true,
      stage4: true,
      stage5: true,
      stage6: true,
      assumptions: true,
      diagnostics: true,
    });
  };

  const collapseAll = () => {
    setOpenSections({
      stage1: false,
      stage2: false,
      stage3: false,
      stage4: false,
      stage5: false,
      stage6: false,
      assumptions: false,
      diagnostics: false,
    });
  };

  const { decision_model, evidence_package, reasoning_board, recommendation, scenarios, resilience } = result;

  const assumptions = decision_model?.assumptions || [];
  const stages = deriveStageProgression(result);

  // Confidence distribution of assumptions
  const confCounts = assumptions.reduce(
    (acc, a) => {
      const c = (a.confidence || "medium").toLowerCase();
      if (c === "high") acc.high++;
      else if (c === "low") acc.low++;
      else acc.medium++;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );
  const totalAssumptions = assumptions.length;

  return (
    <div className="space-y-6" aria-label="Analytical Deep-Dive and Stage Artifacts">
      {/* Header and Controls */}
      <div className="rounded-2xl border border-zinc-800 bg-gradient-to-r from-zinc-950 via-zinc-900/40 to-zinc-950 p-6 space-y-3 text-zinc-100 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-zinc-800/80 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono uppercase tracking-wider text-purple-400 font-semibold">
                Epistemic Depth
              </span>
              <span className="h-1.5 w-1.5 rounded-full bg-purple-400" />
            </div>
            <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-0.5">
              Full Six-Stage Analytical Artifacts &amp; Diagnostics
            </h3>
          </div>

          <div className="flex items-center gap-2 print:hidden">
            <button
              type="button"
              onClick={expandAll}
              className="rounded px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors duration-200 motion-reduce:transition-none border border-zinc-700 cursor-pointer"
            >
              Expand All
            </button>
            <button
              type="button"
              onClick={collapseAll}
              className="rounded px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-colors duration-200 motion-reduce:transition-none border border-zinc-700 cursor-pointer"
            >
              Collapse All
            </button>
          </div>
        </div>

        <p className="text-xs text-zinc-400 max-w-3xl font-sans leading-relaxed break-words [overflow-wrap:anywhere]">
          Complete, unsummarized audit trails across all six decision engine stages.
          Inspect structured models, boardroom deliberations, evidence citations, assumption registries, and technical runtime metadata.
        </p>
      </div>

      {/* Visual Six-Stage Progression Pipeline */}
      <StageProgressionTracker
        stages={stages}
        openSections={openSections}
        onSelectStage={toggleSection}
      />

      {/* Assumption Registry (Prominently featured) */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4 min-w-0 overflow-hidden">
        <div
          className="flex items-center justify-between cursor-pointer hover:text-zinc-200 transition-colors duration-200 motion-reduce:transition-none"
          onClick={() => toggleSection("assumptions")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              toggleSection("assumptions");
            }
          }}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-amber-400 font-bold font-mono text-sm shrink-0">¶</span>
            <h4 className="text-sm font-semibold text-white tracking-tight break-words [overflow-wrap:anywhere] min-w-0">
              Assumption Registry ({assumptions.length} Modeled Assumptions)
            </h4>
          </div>
          <span className="text-xs font-mono text-zinc-400 shrink-0">
            {openSections.assumptions ? "▲ Collapse" : "▼ Expand"}
          </span>
        </div>

        <div
          className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
            openSections.assumptions ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
          }`}
        >
          <div className="overflow-hidden">
            <div className="pt-2 border-t border-zinc-800/80 space-y-3 min-w-0">
              {/* Epistemic Confidence Distribution Bar */}
              {totalAssumptions > 0 && (
                <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
                    <span>Epistemic Confidence Distribution:</span>
                    <div className="flex items-center gap-2 text-[10px]">
                      <span className="text-emerald-400">● {confCounts.high} High</span>
                      <span className="text-amber-400">● {confCounts.medium} Medium</span>
                      <span className="text-rose-400">● {confCounts.low} Low</span>
                    </div>
                  </div>
                  <div
                    className="h-2 w-full bg-zinc-900 rounded-full overflow-hidden flex border border-zinc-800"
                    role="progressbar"
                    aria-label="Assumption confidence distribution"
                  >
                    {confCounts.high > 0 && (
                      <div
                        style={{ width: `${(confCounts.high / totalAssumptions) * 100}%` }}
                        className="bg-emerald-500 h-full"
                        title={`${confCounts.high} High Confidence`}
                      />
                    )}
                    {confCounts.medium > 0 && (
                      <div
                        style={{ width: `${(confCounts.medium / totalAssumptions) * 100}%` }}
                        className="bg-amber-500 h-full"
                        title={`${confCounts.medium} Medium Confidence`}
                      />
                    )}
                    {confCounts.low > 0 && (
                      <div
                        style={{ width: `${(confCounts.low / totalAssumptions) * 100}%` }}
                        className="bg-rose-500 h-full"
                        title={`${confCounts.low} Low Confidence`}
                      />
                    )}
                  </div>
                </div>
              )}
              {assumptions.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No explicit assumptions registered in the decision model.</p>
              ) : (
                <div className="overflow-x-auto min-w-0">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-zinc-800 text-[10px] font-mono text-zinc-400 uppercase tracking-wider">
                        <th className="py-2 px-3">Assumption Statement</th>
                        <th className="py-2 px-3">Confidence</th>
                        <th className="py-2 px-3">Provenance</th>
                        <th className="py-2 px-3">Falsification Condition</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/60 font-sans text-zinc-300">
                      {assumptions.map((a) => (
                        <tr key={a.id} className="hover:bg-zinc-900/40 transition-colors duration-150 motion-reduce:transition-none">
                          <td className="py-2.5 px-3 font-medium text-zinc-100 max-w-sm break-words [overflow-wrap:anywhere]">
                            {a.statement}
                          </td>
                          <td className="py-2.5 px-3 whitespace-nowrap">
                            <span className="inline-flex rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-300 border border-zinc-700">
                              {formatEnumLabel(a.confidence)}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 whitespace-nowrap text-[11px] font-mono text-zinc-400">
                            {formatProvenance(a.provenance)}
                          </td>
                          <td className="py-2.5 px-3 text-[11px] text-zinc-400 italic break-words [overflow-wrap:anywhere]">
                            {a.falsification_condition || "Not explicitly specified"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Stage 1: Structured Decision Model */}
      {decision_model && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 overflow-hidden">
          <div
            className="p-4 bg-zinc-900/50 hover:bg-zinc-900/70 transition-colors duration-200 motion-reduce:transition-none flex items-center justify-between cursor-pointer border-b border-zinc-800/80"
            onClick={() => toggleSection("stage1")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSection("stage1");
              }
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-indigo-400 font-semibold shrink-0">Stage 1</span>
              <h4 className="text-sm font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0">
                Decision Framer &amp; Deconstruction Model
              </h4>
            </div>
            <span className="text-xs font-mono text-zinc-400 shrink-0">
              {openSections.stage1 ? "▲ Collapse" : "▼ Expand"}
            </span>
          </div>

          <div
            className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
              openSections.stage1 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
            }`}
          >
            <div className="overflow-hidden">
              <div id="section-decision-model" className="p-5">
                <DecisionModelSummary model={decision_model} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stage 2: Evidence Package */}
      {evidence_package && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 overflow-hidden">
          <div
            className="p-4 bg-zinc-900/50 hover:bg-zinc-900/70 transition-colors duration-200 motion-reduce:transition-none flex items-center justify-between cursor-pointer border-b border-zinc-800/80"
            onClick={() => toggleSection("stage2")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSection("stage2");
              }
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-sky-400 font-semibold shrink-0">Stage 2</span>
              <h4 className="text-sm font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0">
                Evidence Package &amp; Source Citations
              </h4>
            </div>
            <span className="text-xs font-mono text-zinc-400 shrink-0">
              {openSections.stage2 ? "▲ Collapse" : "▼ Expand"}
            </span>
          </div>

          <div
            className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
              openSections.stage2 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
            }`}
          >
            <div className="overflow-hidden">
              <div id="section-evidence-engine" className="p-5 space-y-6">
                <EvidenceQualityDistribution pkg={evidence_package} />
                <EvidenceOverview pkg={evidence_package} />
                <div id="section-evidence-requirements">
                  <RequirementList pkg={evidence_package} />
                </div>
                {evidence_package.gaps && evidence_package.gaps.length > 0 && (
                  <div id="section-evidence-gaps">
                    <EvidenceGapsSection
                      gaps={evidence_package.gaps}
                      items={evidence_package.items}
                    />
                  </div>
                )}
                {evidence_package.sources && evidence_package.sources.length > 0 && (
                  <div id="section-source-directory">
                    <SourceList sources={evidence_package.sources} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stage 3: AI Boardroom Deliberation */}
      {reasoning_board && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 overflow-hidden">
          <div
            className="p-4 bg-zinc-900/50 hover:bg-zinc-900/70 transition-colors duration-200 motion-reduce:transition-none flex items-center justify-between cursor-pointer border-b border-zinc-800/80"
            onClick={() => toggleSection("stage3")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSection("stage3");
              }
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-purple-400 font-semibold shrink-0">Stage 3</span>
              <h4 className="text-sm font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0">
                AI Boardroom Reasoning &amp; Transcripts
              </h4>
            </div>
            <span className="text-xs font-mono text-zinc-400 shrink-0">
              {openSections.stage3 ? "▲ Collapse" : "▼ Expand"}
            </span>
          </div>

          <div
            className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
              openSections.stage3 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
            }`}
          >
            <div className="overflow-hidden">
              <div id="section-ai-boardroom" className="p-5">
                <ReasoningBoardSection
                  board={reasoning_board}
                  evidencePackage={evidence_package}
                  decisionModel={decision_model}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stage 4: Recommendation Dashboard */}
      {recommendation && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 overflow-hidden">
          <div
            className="p-4 bg-zinc-900/50 hover:bg-zinc-900/70 transition-colors duration-200 motion-reduce:transition-none flex items-center justify-between cursor-pointer border-b border-zinc-800/80"
            onClick={() => toggleSection("stage4")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSection("stage4");
              }
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-emerald-400 font-semibold shrink-0">Stage 4</span>
              <h4 className="text-sm font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0">
                Executive Recommendation Deep Dive
              </h4>
            </div>
            <span className="text-xs font-mono text-zinc-400 shrink-0">
              {openSections.stage4 ? "▲ Collapse" : "▼ Expand"}
            </span>
          </div>

          <div
            className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
              openSections.stage4 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
            }`}
          >
            <div className="overflow-hidden">
              <div className="p-5">
                <RecommendationDashboard
                  recommendation={recommendation}
                  decisionModel={decision_model}
                  evidencePackage={evidence_package}
                  reasoningBoard={reasoning_board}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stage 5: Future Explorer Dashboard */}
      {scenarios && scenarios.scenarios && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 overflow-hidden">
          <div
            className="p-4 bg-zinc-900/50 hover:bg-zinc-900/70 transition-colors duration-200 motion-reduce:transition-none flex items-center justify-between cursor-pointer border-b border-zinc-800/80"
            onClick={() => toggleSection("stage5")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSection("stage5");
              }
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-sky-400 font-semibold shrink-0">Stage 5</span>
              <h4 className="text-sm font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0">
                Future Explorer &amp; Trajectory Details
              </h4>
            </div>
            <span className="text-xs font-mono text-zinc-400 shrink-0">
              {openSections.stage5 ? "▲ Collapse" : "▼ Expand"}
            </span>
          </div>

          <div
            className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
              openSections.stage5 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
            }`}
          >
            <div className="overflow-hidden">
              <div className="p-5">
                <FutureExplorerDashboard
                  scenarioSet={scenarios}
                  decisionModel={decision_model}
                  evidencePackage={evidence_package}
                  decisionTitle={decision_model?.decision?.summary || result.question}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stage 6: Resilience Dashboard */}
      {resilience && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 overflow-hidden">
          <div
            className="p-4 bg-zinc-900/50 hover:bg-zinc-900/70 transition-colors duration-200 motion-reduce:transition-none flex items-center justify-between cursor-pointer border-b border-zinc-800/80"
            onClick={() => toggleSection("stage6")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleSection("stage6");
              }
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-indigo-400 font-semibold shrink-0">Stage 6</span>
              <h4 className="text-sm font-semibold text-white break-words [overflow-wrap:anywhere] min-w-0">
                Decision Resilience &amp; Stress Testing
              </h4>
            </div>
            <span className="text-xs font-mono text-zinc-400 shrink-0">
              {openSections.stage6 ? "▲ Collapse" : "▼ Expand"}
            </span>
          </div>

          <div
            className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
              openSections.stage6 ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
            }`}
          >
            <div className="overflow-hidden">
              <div className="p-5">
                <ResilienceDashboard
                  report={resilience}
                  decisionModel={decision_model}
                  recommendation={recommendation}
                  scenarioSet={scenarios}
                  decisionTitle={decision_model?.decision?.summary || result.question}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Technical Diagnostics (Isolated here, hidden from default executive view) */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4 min-w-0 overflow-hidden">
        <div
          className="flex items-center justify-between cursor-pointer hover:text-zinc-200 transition-colors duration-200 motion-reduce:transition-none"
          onClick={() => toggleSection("diagnostics")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              toggleSection("diagnostics");
            }
          }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-zinc-500 font-mono text-sm shrink-0">#</span>
            <h4 className="text-sm font-semibold text-zinc-200 break-words [overflow-wrap:anywhere] min-w-0">
              Technical Diagnostics &amp; Provenance Identifiers
            </h4>
          </div>
          <span className="text-xs font-mono text-zinc-400 shrink-0">
            {openSections.diagnostics ? "▲ Collapse" : "▼ Expand"}
          </span>
        </div>

        <div
          className={`grid transition-all duration-200 ease-in-out motion-reduce:transition-none ${
            openSections.diagnostics ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0 print:grid-rows-[1fr] print:opacity-100"
          }`}
        >
          <div className="overflow-hidden">
            <div className="pt-3 border-t border-zinc-800/80 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono min-w-0">
              <div className="p-2.5 rounded bg-zinc-900/60 border border-zinc-800 space-y-1 min-w-0">
                <span className="text-[10px] uppercase text-zinc-500 block">Analysis Run ID:</span>
                <span className="text-zinc-300 break-all select-all">{result.analysis_id}</span>
              </div>
              {recommendation && (
                <div className="p-2.5 rounded bg-zinc-900/60 border border-zinc-800 space-y-1 min-w-0">
                  <span className="text-[10px] uppercase text-zinc-500 block">Recommendation ID:</span>
                  <span className="text-zinc-300 break-all select-all">{recommendation.id}</span>
                </div>
              )}
              {decision_model && (
                <div className="p-2.5 rounded bg-zinc-900/60 border border-zinc-800 space-y-1 min-w-0">
                  <span className="text-[10px] uppercase text-zinc-500 block">Decision Model ID:</span>
                  <span className="text-zinc-300 break-all select-all">{decision_model.id}</span>
                </div>
              )}
              {resilience?.calculation_version && (
                <div className="p-2.5 rounded bg-zinc-900/60 border border-zinc-800 space-y-1 min-w-0">
                  <span className="text-[10px] uppercase text-zinc-500 block">Resilience Engine Version:</span>
                  <span className="text-zinc-300">{resilience.calculation_version}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
