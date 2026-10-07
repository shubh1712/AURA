"use client";

import React from "react";
import type { EvidenceGap, EvidenceGapType, EvidenceItem } from "@/types";

interface EvidenceGapsSectionProps {
  gaps: EvidenceGap[];
  items?: EvidenceItem[];
}

function getGapTypeBadge(gapType: EvidenceGapType) {
  switch (gapType) {
    case "conflicting_evidence":
      return {
        label: "Conflicting Evidence",
        className: "bg-rose-950/60 text-rose-300 border-rose-800/70",
      };
    case "unsupported_claim":
      return {
        label: "Unsupported Claim",
        className: "bg-amber-950/60 text-amber-300 border-amber-800/70",
      };
    case "unresolved_unknown":
      return {
        label: "Unresolved Unknown",
        className: "bg-purple-950/60 text-purple-300 border-purple-800/70",
      };
    case "insufficient_evidence":
      return {
        label: "Insufficient Evidence",
        className: "bg-zinc-800 text-zinc-300 border-zinc-700",
      };
  }
}

export function EvidenceGapsSection({ gaps, items = [] }: EvidenceGapsSectionProps) {
  const itemsMap = new Map(items.map((i) => [i.id, i]));

  if (gaps.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 sm:p-6 space-y-5 text-zinc-100 shadow-sm">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-zinc-800/80">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-amber-400">
            Empirical Deficiencies
          </span>
          <h3 className="text-lg font-semibold text-white tracking-tight mt-0.5">
            Identified Evidence Gaps ({gaps.length})
          </h3>
        </div>
        <span className="text-xs text-zinc-400">
          Unvalidated premises, crucial unknowns, and contradictory findings
        </span>
      </div>

      {/* Gaps List */}
      <div className="space-y-4">
        {gaps.map((gap) => {
          const badge = getGapTypeBadge(gap.gap_type);

          return (
            <div
              key={gap.id}
              className="rounded-lg border border-zinc-800/90 bg-zinc-950/60 p-4 space-y-3 text-xs"
            >
              {/* Gap Header: Type Badge, Impact, Target Entity */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium border ${badge.className}`}
                  >
                    {badge.label}
                  </span>

                  <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                    Impact: {gap.impact}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-500">
                  <span>Target: {gap.target_entity_type} ({gap.target_entity_id})</span>
                  <span>&bull;</span>
                  <span>{gap.id}</span>
                </div>
              </div>

              {/* Gap Description */}
              <p className="text-sm text-zinc-200 leading-relaxed font-sans font-medium">
                {gap.description}
              </p>

              {/* Conflicting Evidence references (if present) */}
              {gap.conflicting_evidence_ids && gap.conflicting_evidence_ids.length > 0 && (
                <div className="space-y-1.5 bg-rose-950/20 border border-rose-900/30 p-2.5 rounded">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-rose-300 block">
                    Conflicting Evidence Items ({gap.conflicting_evidence_ids.length})
                  </span>
                  <div className="flex flex-wrap gap-2 text-[11px] font-mono text-zinc-300">
                    {gap.conflicting_evidence_ids.map((id) => {
                      const item = itemsMap.get(id);
                      return (
                        <div
                          key={id}
                          className="rounded bg-zinc-900/80 px-2 py-1 border border-zinc-800 text-zinc-300 flex items-center gap-1.5"
                        >
                          <span className="text-zinc-500">{id}</span>
                          {item && (
                            <span className="text-zinc-300 max-w-xs truncate font-sans">
                              &ldquo;{item.content}&rdquo;
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Actionable Resolution Guidance */}
              {gap.resolution_guidance && (
                <div className="space-y-1 rounded bg-zinc-900/40 border border-zinc-800/50 p-2.5 text-zinc-300">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
                    Resolution Guidance
                  </span>
                  <p className="leading-relaxed font-sans text-xs">{gap.resolution_guidance}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
