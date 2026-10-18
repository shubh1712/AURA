"use client";

import React from "react";
import type {
  BoardSynthesis,
  EvidencePackage,
  DecisionModel,
} from "@/types";

interface BoardSynthesisSectionProps {
  synthesis: BoardSynthesis;
  evidencePackage?: EvidencePackage | null;
  decisionModel?: DecisionModel | null;
}

export function BoardSynthesisSection({
  synthesis,
  evidencePackage,
  decisionModel,
}: BoardSynthesisSectionProps) {
  if (!synthesis) {
    return null;
  }

  // Lookup maps for exact reference resolving
  const assumptionMap = new Map<string, { statement: string; confidence?: string }>();
  if (decisionModel?.assumptions) {
    for (const a of decisionModel.assumptions) {
      assumptionMap.set(a.id, {
        statement: a.statement,
        confidence: a.confidence,
      });
    }
  }

  const gapMap = new Map<string, { description: string; impact?: string }>();
  if (evidencePackage?.gaps) {
    for (const g of evidencePackage.gaps) {
      gapMap.set(g.id, {
        description: g.description,
        impact: g.impact,
      });
    }
  }

  return (
    <section
      aria-labelledby="boardroom-synthesis-title"
      className="rounded-2xl border border-zinc-800/80 bg-zinc-950/70 p-5 sm:p-6 text-zinc-100 shadow-sm space-y-6"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-zinc-800/80">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-indigo-400 font-semibold">
            Deliberative Synthesis
          </span>
          <h3
            id="boardroom-synthesis-title"
            className="text-lg font-semibold text-white tracking-tight mt-0.5"
          >
            Board Synthesis &amp; Strategic Alignment
          </h3>
        </div>

        <span className="text-xs text-zinc-400 font-sans">
          Cross-perspective convergence, sensitivities, and critical dependencies
        </span>
      </div>

      {/* 1. Executive Deliberative Narrative Summary */}
      {synthesis.summary && (
        <div className="rounded-xl border border-indigo-900/40 bg-indigo-950/20 p-4 sm:p-5 text-sm text-zinc-200 leading-relaxed space-y-2">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-indigo-400" />
            <h4 className="text-xs font-mono uppercase tracking-wider text-indigo-300 font-semibold">
              Deliberation Reconciliation Summary
            </h4>
          </div>
          <p className="font-sans text-zinc-200 text-sm sm:text-base leading-relaxed">
            {synthesis.summary}
          </p>
        </div>
      )}

      {/* 2. Areas of Agreement (Common Ground) */}
      {synthesis.areas_of_agreement && synthesis.areas_of_agreement.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-semibold flex items-center gap-2">
            <span>✓</span> Areas of Agreement ({synthesis.areas_of_agreement.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {synthesis.areas_of_agreement.map((point, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-emerald-900/30 bg-emerald-950/15 p-3.5 text-xs text-zinc-300 flex items-start gap-2.5 leading-relaxed"
              >
                <span className="text-emerald-400 text-sm leading-none shrink-0">•</span>
                <span className="font-sans">{point}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Evidence-Sensitive Points */}
      {synthesis.evidence_sensitive_points &&
        synthesis.evidence_sensitive_points.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-xs font-mono uppercase tracking-wider text-teal-400 font-semibold flex items-center gap-2">
              <span>⚖️</span> Evidence-Sensitive Points ({synthesis.evidence_sensitive_points.length})
            </h4>
            <div className="space-y-2">
              {synthesis.evidence_sensitive_points.map((pt, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3.5 text-xs text-zinc-300 flex items-start gap-2.5 leading-relaxed"
                >
                  <span className="text-teal-400 font-mono shrink-0">[{idx + 1}]</span>
                  <span className="font-sans">{pt}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      {/* 4. Critical Dependencies Grid: Assumptions & Evidence Gaps */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Critical Assumptions */}
        {synthesis.critical_assumption_ids &&
          synthesis.critical_assumption_ids.length > 0 && (
            <div className="rounded-xl border border-amber-900/30 bg-amber-950/10 p-4 space-y-3">
              <h4 className="text-xs font-mono uppercase tracking-wider text-amber-400 font-semibold flex items-center justify-between">
                <span>Critical Assumptions</span>
                <span className="text-[11px] font-normal text-amber-300/80">
                  {synthesis.critical_assumption_ids.length} active
                </span>
              </h4>
              <div className="space-y-2">
                {synthesis.critical_assumption_ids.map((id) => {
                  const match = assumptionMap.get(id);
                  return (
                    <div
                      key={id}
                      className="rounded-md border border-amber-900/40 bg-zinc-900/60 p-2.5 text-xs text-zinc-300 space-y-1"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <code className="text-[11px] font-mono text-amber-300">{id}</code>
                        {match?.confidence && (
                          <span className="text-[10px] font-mono text-zinc-400 capitalize">
                            {match.confidence}
                          </span>
                        )}
                      </div>
                      {match?.statement ? (
                        <p className="text-zinc-300 font-sans leading-relaxed text-[11px]">
                          {match.statement}
                        </p>
                      ) : (
                        <p className="text-zinc-500 font-sans text-[11px] italic">
                          Reference ID in decision model
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

        {/* Critical Evidence Gaps */}
        {synthesis.critical_evidence_gap_ids &&
          synthesis.critical_evidence_gap_ids.length > 0 && (
            <div className="rounded-xl border border-rose-900/30 bg-rose-950/10 p-4 space-y-3">
              <h4 className="text-xs font-mono uppercase tracking-wider text-rose-400 font-semibold flex items-center justify-between">
                <span>Critical Evidence Gaps</span>
                <span className="text-[11px] font-normal text-rose-300/80">
                  {synthesis.critical_evidence_gap_ids.length} high-leverage
                </span>
              </h4>
              <div className="space-y-2">
                {synthesis.critical_evidence_gap_ids.map((id) => {
                  const match = gapMap.get(id);
                  return (
                    <div
                      key={id}
                      className="rounded-md border border-rose-900/40 bg-zinc-900/60 p-2.5 text-xs text-zinc-300 space-y-1"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <code className="text-[11px] font-mono text-rose-300">{id}</code>
                        {match?.impact && (
                          <span className="text-[10px] font-mono uppercase text-rose-400">
                            {match.impact} impact
                          </span>
                        )}
                      </div>
                      {match?.description ? (
                        <p className="text-zinc-300 font-sans leading-relaxed text-[11px]">
                          {match.description}
                        </p>
                      ) : (
                        <p className="text-zinc-500 font-sans text-[11px] italic">
                          Reference ID in evidence package
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
      </div>

      {/* 5. Unresolved Strategic Questions */}
      {synthesis.unresolved_questions &&
        synthesis.unresolved_questions.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 sm:p-5 space-y-3">
            <h4 className="text-xs font-mono uppercase tracking-wider text-zinc-300 font-semibold flex items-center gap-2">
              <span>❓</span> Unresolved Strategic Questions ({synthesis.unresolved_questions.length})
            </h4>
            <div className="space-y-2">
              {synthesis.unresolved_questions.map((q, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-zinc-800/80 bg-zinc-950/60 p-3 text-xs text-zinc-200 flex items-start gap-2.5 leading-relaxed font-sans"
                >
                  <span className="text-zinc-500 font-mono shrink-0">Q{idx + 1}.</span>
                  <span>{q}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      {/* 6. Active Disagreements Registered */}
      {synthesis.disagreement_ids && synthesis.disagreement_ids.length > 0 && (
        <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-400 pt-2 border-t border-zinc-800/60">
          <span>Registered Disagreements:</span>
          <div className="flex flex-wrap gap-1.5">
            {synthesis.disagreement_ids.map((did) => (
              <span
                key={did}
                className="rounded bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 text-zinc-300"
              >
                {did}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
