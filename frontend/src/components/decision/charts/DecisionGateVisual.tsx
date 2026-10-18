"use client";

import React from "react";
import type { IntelligentDecisionGate, DecisionGate } from "@/types";

type UnifiedGate = IntelligentDecisionGate | DecisionGate;

interface DecisionGateVisualProps {
  gates: UnifiedGate[];
}

function isIntelligentGate(gate: UnifiedGate): gate is IntelligentDecisionGate {
  return "criteria" in gate || "failure_response" in gate;
}

export function DecisionGateVisual({ gates }: DecisionGateVisualProps) {
  if (!gates || gates.length === 0) {
    return null;
  }

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4"
      role="region"
      aria-label="Decision Gates and Verification Thresholds"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold">
            Governance &amp; Risk Ceilings
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Decision Gates &amp; Rollback Triggers
          </h4>
        </div>
        <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
          {gates.length} Enforced {gates.length === 1 ? "Gate" : "Gates"}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4">
        {gates.map((gate, idx) => {
          const title = isIntelligentGate(gate) ? gate.title : gate.condition;
          const checkpoint = isIntelligentGate(gate) ? gate.checkpoint : gate.target_milestone;
          const criteria = isIntelligentGate(gate) ? gate.criteria : [];
          const rollback = isIntelligentGate(gate) ? gate.failure_response : gate.fallback_action;

          return (
            <div
              key={idx}
              className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 sm:p-5 space-y-3.5 text-xs min-w-0 overflow-hidden flex flex-col justify-between transition-all duration-200 hover:border-zinc-700/80 motion-reduce:transition-none"
            >
              <div className="space-y-3 min-w-0">
                {/* Header: Gate index, naturally wrapping title, and stacked timing badge */}
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2.5 border-b border-zinc-800/60 pb-2.5 min-w-0">
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-indigo-950 text-indigo-300 font-mono font-bold text-xs border border-indigo-800/60 mt-0.5">
                      G{idx + 1}
                    </span>
                    <h5 className="font-semibold text-white text-xs sm:text-sm leading-snug break-words [overflow-wrap:anywhere] min-w-0 flex-1">
                      {title}
                    </h5>
                  </div>
                  {checkpoint && (
                    <div className="shrink-0 self-start sm:self-auto pl-8 sm:pl-0">
                      <span className="inline-flex items-center text-[10px] font-mono text-zinc-400 bg-zinc-950/80 border border-zinc-800 px-2 py-0.5 rounded break-all sm:break-normal">
                        {checkpoint}
                      </span>
                    </div>
                  )}
                </div>

                {/* Thresholds / Verification Criteria */}
                {criteria && criteria.length > 0 ? (
                  <div className="space-y-1.5 min-w-0">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
                      Verification Criteria:
                    </span>
                    <div className="space-y-1.5 min-w-0">
                      {criteria.map((c) => (
                        <div
                          key={c.criterion_id}
                          className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-3 rounded bg-zinc-950/70 border border-zinc-800 px-3 py-2 text-[11px] min-w-0"
                        >
                          <span className="text-zinc-200 leading-snug break-words [overflow-wrap:anywhere] min-w-0 flex-1">
                            {c.description}
                          </span>
                          <span className="font-mono text-amber-300 shrink-0 self-start sm:self-auto text-[10px] sm:text-[11px] font-medium bg-zinc-900/80 px-1.5 py-0.5 rounded border border-zinc-800/80">
                            {c.operator || ""} {c.threshold_raw || c.threshold_value || ""} {c.unit || ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] text-zinc-400 min-w-0 break-words [overflow-wrap:anywhere]">
                    <span className="font-semibold text-zinc-300">Method: </span>
                    {!("criteria" in gate) ? (gate as DecisionGate).verification_method : "Procedural verification"}
                  </div>
                )}
              </div>

              {/* Mandatory Rollback Response */}
              <div className="rounded border border-rose-950/70 bg-rose-950/20 p-3 text-[11px] space-y-1.5 min-w-0 mt-3">
                <span className="font-mono text-[10px] uppercase font-bold text-rose-400 block tracking-wide">
                  Rollback / Fallback Trigger:
                </span>
                <p className="text-rose-200/90 leading-relaxed break-words [overflow-wrap:anywhere] font-sans min-w-0">
                  {rollback || "Halt rollout and revert to preceding baseline state."}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
