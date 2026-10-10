"use client";

import React from "react";
import type { AlternativeOption } from "@/types";

interface AlternativeOptionsSectionProps {
  alternatives: AlternativeOption[];
  primaryRecommendedAction: string;
}

export function AlternativeOptionsSection({
  alternatives,
  primaryRecommendedAction,
}: AlternativeOptionsSectionProps) {
  if (!alternatives || alternatives.length === 0) {
    return null;
  }

  return (
    <section
      id="section-alternative-options"
      aria-labelledby="alternative-options-heading"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:break-inside-avoid print:bg-white print:text-black print:border-zinc-300"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-purple-400 font-semibold print:text-zinc-700">
            Counterfactual &amp; Dialectical Analysis
          </span>
          <h3
            id="alternative-options-heading"
            className="text-xl font-bold text-white print:text-black tracking-tight mt-0.5"
          >
            Alternative Courses of Action Evaluated ({alternatives.length})
          </h3>
          <p className="text-xs sm:text-sm text-zinc-400 print:text-zinc-600 mt-1 max-w-2xl font-sans">
            Explicitly compared strategic paths that were considered during boardroom deliberation but deprioritized or rejected.
          </p>
        </div>

        <span className="text-[11px] font-mono text-zinc-400 print:text-zinc-600 bg-zinc-950/60 px-2.5 py-1 rounded border border-zinc-800 print:border-zinc-300">
          Unchosen Alternatives
        </span>
      </div>

      {/* Primary Chosen Path Callout for Contextual Contrast */}
      <div className="rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 space-y-1 text-xs print:bg-zinc-50 print:border-zinc-300">
        <span className="font-mono text-[10px] uppercase tracking-wider text-emerald-400 font-semibold block">
          Primary Chosen Course (Baseline Recommendation):
        </span>
        <p className="text-zinc-200 print:text-zinc-900 font-medium font-sans">
          &ldquo;{primaryRecommendedAction}&rdquo;
        </p>
      </div>

      {/* Alternatives Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {alternatives.map((alt, idx) => (
          <article
            key={alt.id}
            className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-5 space-y-4 text-xs flex flex-col justify-between shadow-sm print:bg-white print:border-zinc-300 print:text-black"
            aria-label={`Alternative Option ${idx + 1}: ${alt.name}`}
          >
            <div className="space-y-3.5">
              {/* Alternative Name & Badge */}
              <div className="flex items-start justify-between gap-2 pb-2.5 border-b border-zinc-800/70 print:border-zinc-300">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                      Option #{idx + 1}
                    </span>
                    <span className="rounded bg-zinc-900 px-2 py-0.5 text-[10px] font-mono text-zinc-400 border border-zinc-800 print:bg-zinc-100 print:text-zinc-800 print:border-zinc-300">
                      Not Recommended
                    </span>
                  </div>
                  <h4 className="text-base font-semibold text-white print:text-black tracking-tight mt-1">
                    {alt.name}
                  </h4>
                </div>

                <span className="font-mono text-[10px] text-zinc-600 shrink-0">
                  {alt.id}
                </span>
              </div>

              {/* Description */}
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold block">
                  Alternative Scope
                </span>
                <p className="text-zinc-300 print:text-zinc-800 leading-relaxed font-sans">
                  {alt.description}
                </p>
              </div>

              {/* Trade-offs */}
              {alt.tradeoffs && alt.tradeoffs.length > 0 && (
                <div className="space-y-1.5 bg-zinc-900/40 p-3 rounded-lg border border-zinc-800/60 print:bg-zinc-50 print:border-zinc-300">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-amber-400 font-semibold block">
                    Key Trade-Offs &amp; Frictions ({alt.tradeoffs.length})
                  </span>
                  <ul className="space-y-1 pt-0.5 list-none text-zinc-300 print:text-zinc-800">
                    {alt.tradeoffs.map((to, toIdx) => (
                      <li key={toIdx} className="flex items-start gap-2">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                        <span className="font-sans leading-relaxed">{to}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Why Not Recommended (Crucial Epistemic Justification) */}
            <div className="space-y-1 bg-rose-950/20 p-3.5 rounded-lg border border-rose-900/40 pt-3 mt-2 print:bg-zinc-50 print:border-zinc-300">
              <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold flex items-center gap-1">
                <svg
                  className="h-3 w-3 text-rose-400"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
                Why Deprioritized / Not Recommended
              </span>
              <p className="text-zinc-200 print:text-zinc-900 leading-relaxed font-sans text-xs">
                {alt.why_not_recommended}
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
