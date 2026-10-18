"use client";

import React, { useState } from "react";

interface RiskUncertaintyMatrixProps {
  missingInputs: string[];
  changingConditions: string[];
}

export function RiskUncertaintyMatrix({
  missingInputs,
  changingConditions,
}: RiskUncertaintyMatrixProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const hasMissing = missingInputs && missingInputs.length > 0;
  const hasConditions = changingConditions && changingConditions.length > 0;

  if (!hasMissing && !hasConditions) return null;

  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 gap-5"
      role="region"
      aria-label="Risk and Uncertainty Matrix"
    >
      {/* 1. Epistemic Risks / Critical Missing Information */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-5 space-y-3.5 text-xs">
        <div className="flex items-center justify-between pb-2.5 border-b border-zinc-800/80">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-sky-400 font-bold">
              Epistemic Boundary Risks
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
          </div>
          <span className="font-mono text-[10px] text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
            {missingInputs.length} Ranked Gaps
          </span>
        </div>

        <h4 className="text-sm font-semibold text-white tracking-tight">
          Top Missing Inputs That Could Shift Decision
        </h4>

        {hasMissing ? (
          <div className="space-y-2 pt-0.5">
            {missingInputs.map((input, idx) => {
              const isFirst = idx === 0;

              return (
                <div
                  key={idx}
                  className={`rounded-lg border p-3 space-y-1.5 transition-all ${
                    isFirst
                      ? "border-sky-800/80 bg-sky-950/30"
                      : "border-zinc-800/80 bg-zinc-900/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 font-mono text-[11px] font-bold">
                      <span
                        className={`flex h-5 w-5 items-center justify-center rounded text-[10px] ${
                          isFirst
                            ? "bg-sky-500 text-zinc-950"
                            : "bg-zinc-800 text-zinc-300"
                        }`}
                      >
                        #{idx + 1}
                      </span>
                      <span className={isFirst ? "text-sky-300" : "text-zinc-300"}>
                        {isFirst ? "Highest Decision Sensitivity" : `Sensitivity Rank ${idx + 1}`}
                      </span>
                    </span>
                    <span className="text-[10px] font-mono text-zinc-400">
                      Impact: High
                    </span>
                  </div>

                  <p className="text-xs text-zinc-200 font-sans leading-relaxed pl-7">
                    {input}
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-zinc-500 italic py-2">
            Baseline information package sufficient; no critical missing inputs identified.
          </p>
        )}
      </div>

      {/* 2. Reversal Conditions / Pivot Triggers */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-5 space-y-3.5 text-xs">
        <div className="flex items-center justify-between pb-2.5 border-b border-zinc-800/80">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-amber-400 font-bold">
              Dynamic Pivot Triggers
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
          </div>
          <span className="font-mono text-[10px] text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
            {changingConditions.length} Pivot Boundaries
          </span>
        </div>

        <h4 className="text-sm font-semibold text-white tracking-tight">
          Conditions That Would Reverse Recommendation
        </h4>

        {hasConditions ? (
          <div className="space-y-2 pt-0.5">
            {changingConditions.map((cond, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-amber-900/60 bg-amber-950/25 p-3 space-y-1.5 transition-all hover:border-amber-700/80"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 font-mono text-[11px] font-bold text-amber-300">
                    <span className="flex h-5 w-5 items-center justify-center rounded bg-amber-900/60 text-amber-300 text-[10px] border border-amber-700/60">
                      ⚡
                    </span>
                    <span>Reversal Trigger #{idx + 1}</span>
                  </span>
                  <span className="text-[10px] font-mono text-amber-400 bg-amber-950/60 px-1.5 py-0.5 rounded border border-amber-800/60">
                    Pivot Required
                  </span>
                </div>

                <p className="text-xs text-amber-100/90 font-sans leading-relaxed pl-7">
                  {cond}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-zinc-500 italic py-2">
            Recommendation remains mathematically robust under all baseline modeled conditions.
          </p>
        )}
      </div>
    </div>
  );
}
