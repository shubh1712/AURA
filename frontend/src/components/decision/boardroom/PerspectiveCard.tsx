"use client";

import React, { useState } from "react";
import type {
  ReasoningPerspective,
  ReasoningArgument,
  PerspectiveType,
  EvidencePackage,
  DecisionModel,
} from "@/types";

interface PerspectiveCardProps {
  perspective: ReasoningPerspective;
  evidencePackage?: EvidencePackage | null;
  decisionModel?: DecisionModel | null;
}

const PERSPECTIVE_CONFIG: Record<
  PerspectiveType,
  {
    name: string;
    role: string;
    accentBorder: string;
    accentBg: string;
    accentText: string;
    badgeBorder: string;
    badgeBg: string;
    badgeText: string;
    icon: string;
  }
> = {
  growth: {
    name: "Growth Perspective",
    role: "Strategic upside, TAM expansion, top-line potential",
    accentBorder: "border-emerald-800/70",
    accentBg: "bg-emerald-950/20",
    accentText: "text-emerald-300",
    badgeBorder: "border-emerald-700/60",
    badgeBg: "bg-emerald-900/30",
    badgeText: "text-emerald-300",
    icon: "📈",
  },
  finance: {
    name: "Finance Perspective",
    role: "Capital efficiency, unit economics, cash runway, margins",
    accentBorder: "border-amber-800/70",
    accentBg: "bg-amber-950/20",
    accentText: "text-amber-300",
    badgeBorder: "border-amber-700/60",
    badgeBg: "bg-amber-900/30",
    badgeText: "text-amber-300",
    icon: "💰",
  },
  customer: {
    name: "Customer Perspective",
    role: "User value, adoption friction, retention, churn risk",
    accentBorder: "border-sky-800/70",
    accentBg: "bg-sky-950/20",
    accentText: "text-sky-300",
    badgeBorder: "border-sky-700/60",
    badgeBg: "bg-sky-900/30",
    badgeText: "text-sky-300",
    icon: "👥",
  },
  risk: {
    name: "Risk Perspective",
    role: "Downside exposures, operational failure modes, reversibility",
    accentBorder: "border-rose-800/70",
    accentBg: "bg-rose-950/20",
    accentText: "text-rose-300",
    badgeBorder: "border-rose-700/60",
    badgeBg: "bg-rose-900/30",
    badgeText: "text-rose-300",
    icon: "🛡️",
  },
};

const DIRECTION_BADGES: Record<string, { label: string; cls: string }> = {
  favorable: {
    label: "Favorable",
    cls: "border-emerald-800/80 bg-emerald-950/40 text-emerald-300",
  },
  unfavorable: {
    label: "Unfavorable",
    cls: "border-rose-800/80 bg-rose-950/40 text-rose-300",
  },
  neutral: {
    label: "Neutral",
    cls: "border-zinc-700 bg-zinc-900 text-zinc-300",
  },
  mixed: {
    label: "Mixed",
    cls: "border-amber-800/80 bg-amber-950/40 text-amber-300",
  },
};

const BASIS_BADGES: Record<string, { label: string; cls: string }> = {
  evidence: {
    label: "Empirically Grounded",
    cls: "border-teal-800/80 bg-teal-950/40 text-teal-300",
  },
  inference: {
    label: "Logical Deduction",
    cls: "border-indigo-800/80 bg-indigo-950/40 text-indigo-300",
  },
  assumption: {
    label: "Assumption-Based",
    cls: "border-yellow-800/80 bg-yellow-950/40 text-yellow-300",
  },
  unresolved: {
    label: "Unresolved Dependency",
    cls: "border-orange-800/80 bg-orange-950/40 text-orange-300",
  },
  mixed: {
    label: "Multi-Source Basis",
    cls: "border-purple-800/80 bg-purple-950/40 text-purple-300",
  },
};

export function PerspectiveCard({
  perspective,
  evidencePackage,
  decisionModel,
}: PerspectiveCardProps) {
  const [expanded, setExpanded] = useState<boolean>(true);
  const cfg = PERSPECTIVE_CONFIG[perspective.perspective_type] ?? {
    name: perspective.perspective_type,
    role: "Boardroom Perspective",
    accentBorder: "border-zinc-800",
    accentBg: "bg-zinc-900/20",
    accentText: "text-zinc-200",
    badgeBorder: "border-zinc-700",
    badgeBg: "bg-zinc-800",
    badgeText: "text-zinc-300",
    icon: "⚖️",
  };

  // Helper maps for provenance resolution
  const evidenceItemsById = React.useMemo(() => {
    const map = new Map<string, string>();
    if (evidencePackage?.items) {
      for (const item of evidencePackage.items) {
        map.set(item.id, item.content || item.summary || item.id);
      }
    }
    return map;
  }, [evidencePackage]);

  const assumptionsById = React.useMemo(() => {
    const map = new Map<string, string>();
    if (decisionModel?.assumptions) {
      for (const asm of decisionModel.assumptions) {
        map.set(asm.id, asm.statement || asm.id);
      }
    }
    return map;
  }, [decisionModel]);

  return (
    <article
      aria-labelledby={`perspective-title-${perspective.id}`}
      className={`rounded-2xl border ${cfg.accentBorder} ${cfg.accentBg} p-5 sm:p-6 text-zinc-100 shadow-sm space-y-5 backdrop-blur-sm transition-all`}
    >
      {/* Perspective Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80">
        <div className="flex items-center gap-3">
          <span className="text-2xl" role="img" aria-hidden="true">
            {cfg.icon}
          </span>
          <div>
            <h3
              id={`perspective-title-${perspective.id}`}
              className="text-base sm:text-lg font-semibold text-white tracking-tight"
            >
              {cfg.name}
            </h3>
            <p className="text-xs text-zinc-400 font-sans mt-0.5">{cfg.role}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center rounded-md border ${cfg.badgeBorder} ${cfg.badgeBg} px-2.5 py-1 text-xs font-mono font-medium ${cfg.badgeText}`}
          >
            {perspective.perspective_type.toUpperCase()}
          </span>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-zinc-400 hover:text-zinc-200 px-2 py-1 rounded border border-zinc-800 hover:bg-zinc-800/60 cursor-pointer font-sans"
            aria-expanded={expanded}
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>

      {/* Executive Summary */}
      <div className="space-y-1.5">
        <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
          Executive Vantage Point
        </span>
        <p className="text-sm text-zinc-200 leading-relaxed font-sans bg-zinc-950/60 p-4 rounded-xl border border-zinc-800/80">
          {perspective.summary}
        </p>
      </div>

      {expanded && (
        <div className="space-y-6 pt-2">
          {/* Arguments Portfolio */}
          {perspective.arguments && perspective.arguments.length > 0 && (
            <div className="space-y-3">
              <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
                Reasoning Arguments ({perspective.arguments.length})
              </span>
              <div className="space-y-3">
                {perspective.arguments.map((arg: ReasoningArgument) => {
                  const dirBadge = DIRECTION_BADGES[arg.direction] ?? {
                    label: arg.direction,
                    cls: "border-zinc-700 bg-zinc-900 text-zinc-300",
                  };
                  const basisBadge = BASIS_BADGES[arg.basis] ?? {
                    label: arg.basis,
                    cls: "border-zinc-700 bg-zinc-900 text-zinc-300",
                  };

                  return (
                    <div
                      key={arg.id}
                      className="rounded-xl border border-zinc-800/90 bg-zinc-950/70 p-4 space-y-2.5 text-xs shadow-sm"
                    >
                      {/* Claim and Badges */}
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                        <h4 className="font-semibold text-zinc-100 text-sm leading-snug">
                          {arg.claim}
                        </h4>
                        <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium border ${dirBadge.cls}`}
                          >
                            {dirBadge.label}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium border ${basisBadge.cls}`}
                          >
                            {basisBadge.label}
                          </span>
                        </div>
                      </div>

                      {/* Reasoning Body */}
                      <p className="text-zinc-300 leading-relaxed font-sans text-xs sm:text-[13px]">
                        {arg.reasoning}
                      </p>

                      {/* Caveat */}
                      {arg.caveat && (
                        <div className="rounded border border-amber-900/40 bg-amber-950/20 px-3 py-1.5 text-[11px] text-amber-300 font-sans">
                          <span className="font-semibold">Caveat:</span> {arg.caveat}
                        </div>
                      )}

                      {/* Provenance References */}
                      <div className="pt-2 border-t border-zinc-900 flex flex-wrap gap-2 text-[11px] font-mono text-zinc-400">
                        {arg.evidence_item_ids && arg.evidence_item_ids.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="text-zinc-500">Evidence:</span>
                            {arg.evidence_item_ids.map((eid) => (
                              <span
                                key={eid}
                                className="bg-teal-950/50 text-teal-300 border border-teal-800/60 px-1.5 py-0.2 rounded"
                                title={evidenceItemsById.get(eid) || eid}
                              >
                                {eid}
                              </span>
                            ))}
                          </div>
                        )}

                        {arg.assumption_ids && arg.assumption_ids.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="text-zinc-500">Assumptions:</span>
                            {arg.assumption_ids.map((aid) => (
                              <span
                                key={aid}
                                className="bg-yellow-950/50 text-yellow-300 border border-yellow-800/60 px-1.5 py-0.2 rounded"
                                title={assumptionsById.get(aid) || aid}
                              >
                                {aid}
                              </span>
                            ))}
                          </div>
                        )}

                        {arg.evidence_gap_ids && arg.evidence_gap_ids.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="text-zinc-500">Gaps:</span>
                            {arg.evidence_gap_ids.map((gid) => (
                              <span
                                key={gid}
                                className="bg-orange-950/50 text-orange-300 border border-orange-800/60 px-1.5 py-0.2 rounded"
                              >
                                {gid}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Opportunities and Concerns Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Opportunities */}
            {perspective.opportunities && perspective.opportunities.length > 0 && (
              <div className="rounded-xl border border-emerald-900/40 bg-emerald-950/10 p-3.5 space-y-2">
                <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-semibold flex items-center gap-1.5">
                  <span>✨</span> Strategic Upside &amp; Opportunities
                </span>
                <ul className="space-y-1.5 text-xs text-zinc-300 list-disc list-inside font-sans">
                  {perspective.opportunities.map((opp, i) => (
                    <li key={i} className="leading-relaxed">
                      {opp}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Concerns */}
            {perspective.concerns && perspective.concerns.length > 0 && (
              <div className="rounded-xl border border-rose-900/40 bg-rose-950/10 p-3.5 space-y-2">
                <span className="text-[11px] font-mono uppercase tracking-wider text-rose-400 font-semibold flex items-center gap-1.5">
                  <span>⚠️</span> Downside Vulnerabilities &amp; Friction
                </span>
                <ul className="space-y-1.5 text-xs text-zinc-300 list-disc list-inside font-sans">
                  {perspective.concerns.map((con, i) => (
                    <li key={i} className="leading-relaxed">
                      {con}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Unresolved Questions & Limitations */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {perspective.unresolved_questions &&
              perspective.unresolved_questions.length > 0 && (
                <div className="rounded-xl border border-zinc-800/90 bg-zinc-950/40 p-3.5 space-y-2">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
                    Open Strategic Questions
                  </span>
                  <ul className="space-y-1 text-xs text-zinc-300 list-disc list-inside font-sans">
                    {perspective.unresolved_questions.map((uq, i) => (
                      <li key={i} className="leading-relaxed">
                        {uq}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

            {perspective.limitations && perspective.limitations.length > 0 && (
              <div className="rounded-xl border border-zinc-800/90 bg-zinc-950/40 p-3.5 space-y-2">
                <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
                  Analytical Boundaries &amp; Blind Spots
                </span>
                <ul className="space-y-1 text-xs text-zinc-400 list-disc list-inside font-sans">
                  {perspective.limitations.map((lim, i) => (
                    <li key={i} className="leading-relaxed">
                      {lim}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
