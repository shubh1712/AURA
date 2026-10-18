"use client";

import React from "react";
import type { IntelligentDecisionGate, IntelligentActionItem } from "@/types";

interface ActionDecisionGatesProps {
  decisionGates: IntelligentDecisionGate[];
  actions?: IntelligentActionItem[];
}

export function ActionDecisionGates({
  decisionGates,
  actions = [],
}: ActionDecisionGatesProps) {
  if (!decisionGates || decisionGates.length === 0) {
    return null;
  }

  // Create action lookup map
  const actionMap = new Map<string, IntelligentActionItem>();
  actions.forEach((a) => actionMap.set(a.action_id, a));

  return (
    <div id="action-decision-gates-section" className="space-y-4">
      <div className="space-y-0.5">
        <h3 className="text-base font-semibold text-white print:text-black tracking-tight">
          Strategic Decision Gates &amp; Verification Checkpoints
        </h3>
        <p className="text-xs text-zinc-400 print:text-zinc-600">
          Enforced governance boundaries requiring criteria verification before downstream commitments.
        </p>
      </div>

      <div className="space-y-4">
        {decisionGates.map((gate, idx) => {
          return (
            <div
              key={gate.gate_id || idx}
              id={`decision-gate-${gate.gate_id}`}
              className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4 text-zinc-100 shadow-sm transition-all duration-200 hover:border-zinc-700/80 motion-reduce:transition-none min-w-0 overflow-hidden print:border-zinc-300 print:bg-white print:text-black"
            >
              {/* Gate Header */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-zinc-800/80 pb-3 print:border-zinc-200 min-w-0">
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-indigo-700/60 bg-indigo-950/40 text-xs font-mono font-bold text-indigo-300 print:border-zinc-300 print:bg-zinc-100 print:text-black">
                    G{idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h4 className="text-sm font-semibold text-white print:text-black tracking-tight break-words [overflow-wrap:anywhere] min-w-0">
                      {gate.title}
                    </h4>
                    <span className="text-[11px] font-mono text-zinc-500">[{gate.gate_id}]</span>
                  </div>
                </div>

                <div className="text-xs font-mono text-zinc-400 print:text-zinc-600 shrink-0">
                  <span className="font-semibold text-zinc-300 print:text-black">Checkpoint:</span>{" "}
                  <span className="break-words [overflow-wrap:anywhere]">{gate.checkpoint}</span>
                </div>
              </div>

              {/* Related Actions Gated */}
              {gate.related_action_ids && gate.related_action_ids.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 text-xs min-w-0">
                  <span className="font-mono text-[11px] uppercase tracking-wider text-zinc-400 font-semibold print:text-zinc-700 shrink-0">
                    Governs Actions:
                  </span>
                  {gate.related_action_ids.map((aid) => {
                    const act = actionMap.get(aid);
                    return (
                      <span
                        key={aid}
                        className="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 border border-zinc-700/60 print:bg-zinc-100 print:border-zinc-300 print:text-black max-w-full"
                      >
                        <span className="font-mono text-[10px] text-zinc-400 shrink-0">
                          {act ? `#${act.sequence}` : aid}
                        </span>
                        <span className="break-words [overflow-wrap:anywhere] min-w-0">{act ? act.title : aid}</span>
                      </span>
                    );
                  })}
                </div>
              )}

              {/* Verification Criteria */}
              <div className="space-y-2 min-w-0">
                <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-700">
                  Verification Criteria for Proceeding:
                </span>
                {gate.criteria && gate.criteria.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 min-w-0">
                    {gate.criteria.map((crit) => (
                      <div
                        key={crit.criterion_id}
                        className="rounded-lg border border-zinc-800/80 bg-zinc-950/30 p-2.5 text-xs space-y-1 min-w-0 print:border-zinc-300 print:bg-zinc-50"
                      >
                        <div className="flex items-center justify-between gap-2 min-w-0">
                          <span className="font-medium text-zinc-200 print:text-black break-words [overflow-wrap:anywhere] min-w-0">
                            {crit.description}
                          </span>
                          {crit.is_hard ? (
                            <span className="rounded bg-rose-950/60 border border-rose-800/60 px-1.5 py-0.2 text-[10px] font-mono font-bold text-rose-300 shrink-0">
                              HARD CONSTRAINT
                            </span>
                          ) : (
                            <span className="rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.2 text-[10px] font-mono text-zinc-400 shrink-0">
                              TARGET
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] font-mono text-zinc-400 print:text-zinc-600 break-words [overflow-wrap:anywhere]">
                          Threshold: {crit.operator || ""} {crit.threshold_raw || crit.threshold_value || "Qualitative"} {crit.unit || ""}
                        </div>
                        {crit.source_reference && (
                          <div className="text-[10px] font-mono text-zinc-500 break-words [overflow-wrap:anywhere]">
                            Source: {crit.source_reference}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-500 italic">
                    Procedural checkpoint verification without quantitative criteria.
                  </div>
                )}
              </div>

              {/* Failure / Rollback Procedure */}
              <div className="space-y-1.5 rounded-lg border border-rose-950/60 bg-rose-950/15 p-3 text-xs text-rose-200/90 print:border-zinc-300 print:bg-zinc-50 print:text-zinc-800 min-w-0">
                <span className="font-mono text-[11px] uppercase tracking-wider font-semibold text-rose-400 print:text-zinc-800 block">
                  Mandatory Failure &amp; Rollback Response:
                </span>
                <p className="leading-relaxed break-words [overflow-wrap:anywhere]">
                  {gate.failure_response || "Halt execution pending formal review."}
                </p>
              </div>

              {/* Unresolved Conflicts */}
              {gate.unresolved_conflicts && gate.unresolved_conflicts.length > 0 && (
                <div className="space-y-1 pt-1 text-xs text-amber-300/80 print:text-zinc-700">
                  <span className="font-semibold text-amber-300 print:text-black">
                    Boardroom Disagreements Evaluated:
                  </span>
                  <ul className="list-disc list-inside space-y-0.5 text-zinc-400 print:text-zinc-600">
                    {gate.unresolved_conflicts.map((conf, cIdx) => (
                      <li key={cIdx}>{conf}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
