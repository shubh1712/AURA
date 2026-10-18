"use client";

import React, { useState } from "react";
import {
  formatScore,
  normalizeSubScores,
  type NormalizedPillarScore,
} from "@/lib/resilienceHelpers";

interface ResiliencePillarBreakdownProps {
  subScores: unknown;
}

export function ResiliencePillarBreakdown({
  subScores,
}: ResiliencePillarBreakdownProps) {
  const pillars: NormalizedPillarScore[] = normalizeSubScores(subScores);
  const [expandedPillars, setExpandedPillars] = useState<Record<string, boolean>>({
    constraint_boundary_tolerance: true,
    pessimistic_scenario_survivability: true,
    contingency_and_fallback_coverage: true,
    information_robustness: true,
  });

  const togglePillar = (key: string) => {
    setExpandedPillars((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const getPillarColor = (score: number, max: number) => {
    const ratio = score / max;
    if (ratio >= 0.8) return { bar: "bg-emerald-500", text: "text-emerald-400", badge: "bg-emerald-950/40 text-emerald-300 border-emerald-700/60" };
    if (ratio >= 0.6) return { bar: "bg-cyan-500", text: "text-cyan-400", badge: "bg-cyan-950/40 text-cyan-300 border-cyan-700/60" };
    if (ratio >= 0.4) return { bar: "bg-amber-500", text: "text-amber-400", badge: "bg-amber-950/40 text-amber-300 border-amber-700/60" };
    return { bar: "bg-rose-500", text: "text-rose-400", badge: "bg-rose-950/40 text-rose-300 border-rose-700/60" };
  };

  return (
    <div
      aria-label="Four-Pillar Resilience Breakdown"
      className="rounded-2xl border border-zinc-800/90 bg-zinc-950/70 p-6 sm:p-7 text-zinc-100 shadow-md space-y-6 print:bg-white print:border-zinc-300 print:text-black"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-indigo-400 print:text-zinc-700 font-semibold">
            Pillar Decomposition (25 Points Each)
          </span>
          <h3 className="text-lg font-semibold text-white print:text-black tracking-tight mt-0.5">
            Four Canonical Resilience Pillars
          </h3>
        </div>

        <span className="text-xs font-mono text-zinc-400 print:text-zinc-600">
          Max Total: 100.0 Pts
        </span>
      </div>

      {/* Pillars Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {pillars.map((pillar, idx) => {
          const isExpanded = expandedPillars[pillar.pillarKey] ?? true;
          const color = getPillarColor(pillar.score, pillar.maxScore);

          return (
            <article
              key={pillar.pillarKey}
              aria-labelledby={`pillar-title-${pillar.pillarKey}`}
              className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-4 print:bg-zinc-50 print:border-zinc-300 print:text-black hover:border-zinc-700 transition-colors"
            >
              {/* Pillar Title & Score Header */}
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono font-semibold uppercase px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 print:bg-zinc-200 print:text-black">
                      Pillar {idx + 1}
                    </span>
                    <span className="text-[11px] font-mono text-zinc-400 print:text-zinc-600">
                      {pillar.category}
                    </span>
                  </div>
                  <h4
                    id={`pillar-title-${pillar.pillarKey}`}
                    className="text-sm font-semibold text-white print:text-black tracking-tight"
                  >
                    {pillar.title}
                  </h4>
                </div>

                {/* Score Badge */}
                <div className="text-right shrink-0">
                  <span
                    className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-mono font-bold ${color.badge} print:bg-zinc-100 print:text-black print:border-zinc-300`}
                  >
                    {formatScore(pillar.score)} / {formatScore(pillar.maxScore)} pts
                  </span>
                </div>
              </div>

              {/* Progress Visualization */}
              <div className="space-y-1.5">
                <div
                  role="progressbar"
                  aria-valuenow={pillar.score}
                  aria-valuemin={0}
                  aria-valuemax={pillar.maxScore}
                  aria-label={`${pillar.title}: ${formatScore(pillar.score)} of ${formatScore(pillar.maxScore)} points`}
                  className="h-2 w-full rounded-full bg-zinc-800 print:bg-zinc-200 overflow-hidden"
                >
                  <div
                    style={{ width: `${pillar.percentage}%` }}
                    className={`h-full rounded-full transition-all duration-500 ${color.bar} print:bg-zinc-800`}
                  />
                </div>
                <div className="flex justify-between items-center text-[10px] font-mono text-zinc-400 print:text-zinc-600">
                  <span>0 pts</span>
                  <span>{pillar.percentage}% of ceiling</span>
                  <span>{formatScore(pillar.maxScore)} pts</span>
                </div>
              </div>

              {/* Pillar Core Description */}
              <p className="text-xs text-zinc-400 print:text-zinc-600 leading-relaxed font-sans">
                {pillar.description}
              </p>

              {/* Expand/Collapse Rationale & Vulnerabilities */}
              <div className="pt-2 border-t border-zinc-800/80 print:border-zinc-200 space-y-3">
                <button
                  type="button"
                  onClick={() => togglePillar(pillar.pillarKey)}
                  aria-expanded={isExpanded}
                  className="flex items-center justify-between w-full text-left text-xs font-medium text-zinc-300 hover:text-white print:text-black cursor-pointer py-1"
                >
                  <span className="flex items-center gap-1.5">
                    <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600">
                      Detailed Rationale &amp; Findings
                    </span>
                    {pillar.vulnerabilities.length > 0 && (
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-rose-950/60 text-rose-300 border border-rose-800/60">
                        {pillar.vulnerabilities.length} vuln
                      </span>
                    )}
                  </span>
                  <span className="text-zinc-400 font-mono text-xs print:hidden">
                    {isExpanded ? "▲ Hide" : "▼ Show"}
                  </span>
                </button>

                {isExpanded && (
                  <div className="space-y-3 text-xs leading-relaxed pt-1">
                    {/* Explainable Rationale */}
                    <div className="rounded-lg bg-zinc-950/60 border border-zinc-800/80 p-3 text-zinc-300 print:bg-white print:border-zinc-200 print:text-black">
                      <p className="font-sans leading-relaxed">
                        {pillar.rationale}
                      </p>
                    </div>

                    {/* Detected Vulnerabilities in this Pillar */}
                    <div className="space-y-1.5">
                      <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600">
                        Pillar Vulnerabilities:
                      </span>
                      {pillar.vulnerabilities.length > 0 ? (
                        <ul className="space-y-1.5">
                          {pillar.vulnerabilities.map((vuln, vIdx) => (
                            <li
                              key={vIdx}
                              className="flex items-start gap-2 rounded-md bg-rose-950/20 border border-rose-900/40 p-2 text-rose-200 print:bg-zinc-100 print:border-zinc-300 print:text-black text-[11px]"
                            >
                              <span className="text-rose-400 print:text-black shrink-0 font-bold">
                                &bull;
                              </span>
                              <span className="leading-snug">{vuln}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-[11px] text-zinc-500 print:text-zinc-600 italic">
                          No structural vulnerabilities identified in this pillar.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
