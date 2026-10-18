"use client";

import React from "react";
import type { ReasoningDisagreement, DisagreementNature } from "@/types";

interface DisagreementsSectionProps {
  disagreements: ReasoningDisagreement[];
}

const NATURE_CONFIG: Record<
  DisagreementNature,
  { label: string; cls: string; desc: string }
> = {
  evidence_dependent: {
    label: "Evidence-Dependent",
    cls: "border-teal-800/80 bg-teal-950/40 text-teal-300",
    desc: "Tension arises from conflicting empirical findings or incomplete data.",
  },
  assumption_dependent: {
    label: "Assumption-Dependent",
    cls: "border-amber-800/80 bg-amber-950/40 text-amber-300",
    desc: "Tension stems from divergent foundational unverified assumptions.",
  },
  interpretation: {
    label: "Interpretive Lens",
    cls: "border-indigo-800/80 bg-indigo-950/40 text-indigo-300",
    desc: "Agreed empirical facts evaluated differently through distinct strategic mandates.",
  },
  unresolved: {
    label: "Unresolved Unknowns",
    cls: "border-rose-800/80 bg-rose-950/40 text-rose-300",
    desc: "Critical unknowns prevent alignment between perspectives.",
  },
};

export function DisagreementsSection({
  disagreements,
}: DisagreementsSectionProps) {
  if (!disagreements || disagreements.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="boardroom-disagreements-title"
      className="rounded-2xl border border-zinc-800/80 bg-zinc-950/70 p-5 sm:p-6 text-zinc-100 shadow-sm space-y-6"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-zinc-800/80">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-amber-400 font-semibold">
            Cross-Perspective Friction
          </span>
          <h3
            id="boardroom-disagreements-title"
            className="text-lg font-semibold text-white tracking-tight mt-0.5"
          >
            Where the Perspectives Disagree ({disagreements.length})
          </h3>
        </div>

        <span className="text-xs text-zinc-400 font-sans">
          Explicit dialectical tensions across boardroom vantage points
        </span>
      </div>

      {/* Disagreements List */}
      <div className="space-y-4">
        {disagreements.map((dis) => {
          const natureCfg = NATURE_CONFIG[dis.nature] ?? {
            label: dis.nature,
            cls: "border-zinc-700 bg-zinc-900 text-zinc-300",
            desc: "Classified strategic disagreement.",
          };

          return (
            <div
              key={dis.id}
              className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 sm:p-5 space-y-4 text-xs"
            >
              {/* Topic and Nature Badge */}
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2.5">
                <div>
                  <h4 className="text-sm sm:text-base font-semibold text-zinc-100">
                    {dis.topic}
                  </h4>
                  <p className="text-[11px] text-zinc-400 font-sans mt-0.5">
                    {natureCfg.desc}
                  </p>
                </div>

                <span
                  className={`rounded px-2.5 py-1 text-[11px] font-mono font-medium border shrink-0 ${natureCfg.cls}`}
                >
                  {natureCfg.label}
                </span>
              </div>

              {/* Competing Positions */}
              {dis.positions && Object.keys(dis.positions).length > 0 && (
                <div className="space-y-2 pt-2">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
                    Competing Stances:
                  </span>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(dis.positions).map(([perspId, stance]) => (
                      <div
                        key={perspId}
                        className="rounded-lg border border-zinc-800/80 bg-zinc-950/60 p-3 space-y-1"
                      >
                        <span className="font-mono text-[11px] text-zinc-400 font-semibold uppercase">
                          {perspId.replace(/^persp_/, "")}:
                        </span>
                        <p className="text-zinc-200 text-xs leading-relaxed font-sans">
                          {stance}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Underlying References */}
              <div className="pt-2 border-t border-zinc-800/70 flex flex-wrap gap-3 text-[11px] font-mono text-zinc-400">
                {dis.evidence_item_ids && dis.evidence_item_ids.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-zinc-500">Contested Evidence:</span>
                    {dis.evidence_item_ids.map((id) => (
                      <span
                        key={id}
                        className="bg-teal-950/40 text-teal-300 border border-teal-800/50 px-1.5 py-0.5 rounded"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                )}

                {dis.assumption_ids && dis.assumption_ids.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-zinc-500">Conflicting Assumptions:</span>
                    {dis.assumption_ids.map((id) => (
                      <span
                        key={id}
                        className="bg-yellow-950/40 text-yellow-300 border border-yellow-800/50 px-1.5 py-0.5 rounded"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                )}

                {dis.evidence_gap_ids && dis.evidence_gap_ids.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-zinc-500">Evidence Gaps:</span>
                    {dis.evidence_gap_ids.map((id) => (
                      <span
                        key={id}
                        className="bg-orange-950/40 text-orange-300 border border-orange-800/50 px-1.5 py-0.5 rounded"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
