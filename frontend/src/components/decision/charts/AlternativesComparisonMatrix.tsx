"use client";

import React from "react";
import type { AlternativeOption } from "@/types";

interface AlternativesComparisonMatrixProps {
  primaryAction: string;
  alternatives: AlternativeOption[];
}

export function AlternativesComparisonMatrix({
  primaryAction,
  alternatives,
}: AlternativesComparisonMatrixProps) {
  if (!alternatives || alternatives.length === 0) {
    return null;
  }

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4"
      role="region"
      aria-label="Alternatives Comparison Matrix"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-purple-400 font-semibold">
            Comparative Matrix
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Strategic Alternatives vs. Chosen Path
          </h4>
        </div>
        <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
          {alternatives.length + 1} Options Evaluated
        </span>
      </div>

      {/* Accessible Table for Desktop & Tablet */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 text-[11px] font-mono text-zinc-400 uppercase tracking-wider">
              <th className="py-2.5 px-3 font-semibold">Strategic Option</th>
              <th className="py-2.5 px-3 font-semibold">Status</th>
              <th className="py-2.5 px-3 font-semibold">Trade-Offs &amp; Frictions</th>
              <th className="py-2.5 px-3 font-semibold">Epistemic Determination</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 font-sans">
            {/* Primary Recommended Row */}
            <tr className="bg-emerald-950/20 text-zinc-100">
              <td className="py-3 px-3 align-top font-semibold text-white">
                <div className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 shrink-0" />
                  <span>Baseline Recommendation</span>
                </div>
                <div className="text-[11px] text-zinc-300 font-normal mt-1 leading-snug">
                  {primaryAction}
                </div>
              </td>
              <td className="py-3 px-3 align-top whitespace-nowrap">
                <span className="inline-flex items-center rounded-md border border-emerald-800/60 bg-emerald-950/50 px-2 py-0.5 text-[10px] font-mono font-semibold text-emerald-300">
                  Recommended
                </span>
              </td>
              <td className="py-3 px-3 align-top text-zinc-300 text-[11px] leading-relaxed">
                Acceptable operational complexity for proven scaling and transactional guarantees.
              </td>
              <td className="py-3 px-3 align-top text-emerald-300/90 text-[11px] leading-relaxed font-medium">
                Highest alignment with primary objectives under validated constraint boundaries.
              </td>
            </tr>

            {/* Alternatives Rows */}
            {alternatives.map((alt, idx) => (
              <tr key={alt.id || idx} className="hover:bg-zinc-900/40 text-zinc-300">
                <td className="py-3 px-3 align-top">
                  <div className="font-semibold text-zinc-200">
                    {alt.name}
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-0.5 leading-snug">
                    {alt.description}
                  </p>
                </td>
                <td className="py-3 px-3 align-top whitespace-nowrap">
                  <span className="inline-flex items-center rounded-md border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] font-mono font-medium text-zinc-400">
                    Deprioritized
                  </span>
                </td>
                <td className="py-3 px-3 align-top text-[11px]">
                  {alt.tradeoffs && alt.tradeoffs.length > 0 ? (
                    <ul className="space-y-1 list-disc list-inside text-zinc-400">
                      {alt.tradeoffs.slice(0, 2).map((to, toIdx) => (
                        <li key={toIdx}>{to}</li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-zinc-500 italic">None documented</span>
                  )}
                </td>
                <td className="py-3 px-3 align-top text-[11px] text-rose-300/90 leading-relaxed">
                  {alt.why_not_recommended}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
