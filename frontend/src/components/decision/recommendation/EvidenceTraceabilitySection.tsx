"use client";

import React from "react";
import type {
  DecisionRecommendation,
  EvidencePackage,
  DecisionModel,
  ReasoningBoard,
} from "@/types";
import {
  resolveEvidenceItem,
  resolveAssumption,
  resolveEvidenceGap,
  resolveDisagreement,
} from "@/lib/recommendationHelpers";

interface EvidenceTraceabilitySectionProps {
  recommendation: DecisionRecommendation;
  evidencePackage?: EvidencePackage | null;
  decisionModel?: DecisionModel | null;
  reasoningBoard?: ReasoningBoard | null;
}

export function EvidenceTraceabilitySection({
  recommendation,
  evidencePackage,
  decisionModel,
  reasoningBoard,
}: EvidenceTraceabilitySectionProps) {
  const {
    supporting_evidence_item_ids = [],
    relevant_assumption_ids = [],
    relevant_evidence_gap_ids = [],
    unresolved_disagreement_ids = [],
  } = recommendation;

  return (
    <section
      id="section-evidence-traceability"
      aria-labelledby="evidence-traceability-heading"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:break-inside-avoid print:bg-white print:text-black print:border-zinc-300"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-teal-400 font-semibold print:text-zinc-700">
            Audit Trail &amp; Epistemic Grounding
          </span>
          <h3
            id="evidence-traceability-heading"
            className="text-xl font-bold text-white print:text-black tracking-tight mt-0.5"
          >
            Evidence Traceability &amp; Deliberative Linkages
          </h3>
          <p className="text-xs sm:text-sm text-zinc-400 print:text-zinc-600 mt-1 max-w-2xl font-sans">
            Directly maps this recommendation back to empirical evidence items, model assumptions, evidence gaps, and cross-perspective boardroom disagreements.
          </p>
        </div>

        <span className="text-[11px] font-mono text-zinc-400 print:text-zinc-600 bg-zinc-950/60 px-2.5 py-1 rounded border border-zinc-800 print:border-zinc-300">
          Strict Reference Audit
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* 1. Supporting Evidence Items */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3.5 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-zinc-800/60">
            <span className="text-xs font-mono uppercase tracking-wider text-teal-400 font-semibold">
              Supporting Evidence ({supporting_evidence_item_ids.length})
            </span>
            {evidencePackage && (
              <a
                href="#section-evidence-requirements"
                className="text-[11px] font-mono text-zinc-400 hover:text-teal-300 hover:underline print:hidden"
              >
                Inspect in Evidence Engine &rarr;
              </a>
            )}
          </div>

          {supporting_evidence_item_ids.length > 0 ? (
            <div className="space-y-2.5">
              {supporting_evidence_item_ids.map((id) => {
                const item = resolveEvidenceItem(id, evidencePackage);
                return (
                  <div
                    key={id}
                    className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-900/40 text-xs space-y-1.5 print:bg-white print:border-zinc-300"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-teal-300 font-semibold">
                        {id}
                      </span>
                      {item.confidence && (
                        <span className="text-[10px] font-mono text-zinc-400 bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                          Confidence: {item.confidence}
                        </span>
                      )}
                    </div>
                    <p className="text-zinc-200 print:text-zinc-900 font-sans leading-relaxed text-xs">
                      {item.content}
                    </p>
                    {item.sourceTitle && (
                      <p className="text-[10px] text-zinc-500 font-mono">
                        Source: {item.sourceTitle}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">
              No specific evidence items linked as primary support.
            </p>
          )}
        </div>

        {/* 2. Unresolved Boardroom Disagreements */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3.5 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-zinc-800/60">
            <span className="text-xs font-mono uppercase tracking-wider text-rose-400 font-semibold">
              Unresolved Disagreements ({unresolved_disagreement_ids.length})
            </span>
            {reasoningBoard && (
              <a
                href="#section-ai-boardroom"
                className="text-[11px] font-mono text-zinc-400 hover:text-rose-300 hover:underline print:hidden"
              >
                Inspect in Boardroom &rarr;
              </a>
            )}
          </div>

          {unresolved_disagreement_ids.length > 0 ? (
            <div className="space-y-2.5">
              {unresolved_disagreement_ids.map((id) => {
                const dis = resolveDisagreement(id, reasoningBoard);
                return (
                  <div
                    key={id}
                    className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-900/40 text-xs space-y-1.5 print:bg-white print:border-zinc-300"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-rose-300 font-semibold">
                        {id}
                      </span>
                      {dis.nature && (
                        <span className="text-[10px] font-mono text-rose-300 bg-rose-950/40 px-1.5 py-0.5 rounded border border-rose-800/40">
                          {dis.nature}
                        </span>
                      )}
                    </div>
                    <p className="text-zinc-200 print:text-zinc-900 font-medium font-sans">
                      {dis.topic}
                    </p>
                    {dis.positions && Object.keys(dis.positions).length > 0 && (
                      <div className="text-[11px] text-zinc-400 font-sans space-y-0.5 pt-1">
                        {Object.entries(dis.positions).map(([persp, stance]) => (
                          <div key={persp} className="truncate">
                            <span className="text-zinc-500 font-mono capitalize">
                              {persp.replace(/^persp_/, "")}:
                            </span>{" "}
                            {stance}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">
              All boardroom tensions reconciled; no unresolved dialectical friction linked.
            </p>
          )}
        </div>

        {/* 3. Relevant Assumptions */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3.5 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-zinc-800/60">
            <span className="text-xs font-mono uppercase tracking-wider text-amber-400 font-semibold">
              Key Assumptions ({relevant_assumption_ids.length})
            </span>
            {decisionModel && (
              <a
                href="#section-decision-model"
                className="text-[11px] font-mono text-zinc-400 hover:text-amber-300 hover:underline print:hidden"
              >
                Inspect in Model &rarr;
              </a>
            )}
          </div>

          {relevant_assumption_ids.length > 0 ? (
            <div className="space-y-2.5">
              {relevant_assumption_ids.map((id) => {
                const assump = resolveAssumption(id, decisionModel);
                return (
                  <div
                    key={id}
                    className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-900/40 text-xs space-y-1.5 print:bg-white print:border-zinc-300"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-amber-300 font-semibold">
                        {id}
                      </span>
                      {assump.confidence && (
                        <span className="text-[10px] font-mono text-zinc-400 bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                          Confidence: {assump.confidence}
                        </span>
                      )}
                    </div>
                    <p className="text-zinc-200 print:text-zinc-900 font-sans leading-relaxed text-xs">
                      {assump.statement}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">
              No specific assumptions referenced.
            </p>
          )}
        </div>

        {/* 4. Relevant Evidence Gaps */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3.5 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-zinc-800/60">
            <span className="text-xs font-mono uppercase tracking-wider text-orange-400 font-semibold">
              Relevant Evidence Gaps ({relevant_evidence_gap_ids.length})
            </span>
            {evidencePackage && (
              <a
                href="#section-evidence-gaps"
                className="text-[11px] font-mono text-zinc-400 hover:text-orange-300 hover:underline print:hidden"
              >
                Inspect Gaps &rarr;
              </a>
            )}
          </div>

          {relevant_evidence_gap_ids.length > 0 ? (
            <div className="space-y-2.5">
              {relevant_evidence_gap_ids.map((id) => {
                const gap = resolveEvidenceGap(id, evidencePackage);
                return (
                  <div
                    key={id}
                    className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-900/40 text-xs space-y-1.5 print:bg-white print:border-zinc-300"
                  >
                    <span className="font-mono text-[10px] text-orange-300 font-semibold block">
                      {id}
                    </span>
                    <p className="text-zinc-200 print:text-zinc-900 font-sans leading-relaxed text-xs">
                      {gap.description}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">
              No specific evidence gaps referenced.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
