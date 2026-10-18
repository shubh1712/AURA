"use client";

import React from "react";

interface ActionUnresolvedQuestionsProps {
  unresolvedQuestions?: string[];
  limitations?: string[];
}

export function ActionUnresolvedQuestions({
  unresolvedQuestions = [],
  limitations = [],
}: ActionUnresolvedQuestionsProps) {
  const hasQuestions = unresolvedQuestions && unresolvedQuestions.length > 0;
  const hasLimitations = limitations && limitations.length > 0;

  if (!hasQuestions && !hasLimitations) {
    return null;
  }

  return (
    <div
      id="action-unresolved-questions-section"
      className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 space-y-4 text-xs text-zinc-300 print:border-zinc-300 print:bg-white print:text-black"
    >
      <div className="space-y-0.5">
        <h4 className="text-sm font-semibold text-white print:text-black tracking-tight">
          Unresolved Strategic Questions &amp; Analytical Boundaries
        </h4>
        <p className="text-xs text-zinc-400 print:text-zinc-600">
          Identified unknowns, telemetry requirements, and operational boundaries requiring human judgment.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Unresolved Questions */}
        {hasQuestions && (
          <div className="space-y-2 rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-3.5 print:border-zinc-300 print:bg-zinc-50">
            <span className="font-mono text-[11px] uppercase tracking-wider font-semibold text-indigo-400 print:text-zinc-800 block">
              Open Strategic Questions:
            </span>
            <ul className="list-disc list-inside space-y-1.5 text-zinc-300 print:text-black pl-1 leading-relaxed">
              {unresolvedQuestions.map((q, idx) => (
                <li key={idx}>{q}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Analytical Boundaries & Limitations */}
        {hasLimitations && (
          <div className="space-y-2 rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-3.5 print:border-zinc-300 print:bg-zinc-50">
            <span className="font-mono text-[11px] uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-800 block">
              Analytical Limitations &amp; Boundaries:
            </span>
            <ul className="list-disc list-inside space-y-1.5 text-zinc-300 print:text-black pl-1 leading-relaxed">
              {limitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
