"use client";

import React, { useState } from "react";
import type { OptionComparisonReport } from "@/types";

interface OptionComparisonMatrixProps {
  report: OptionComparisonReport;
}

export function OptionComparisonMatrix({ report }: OptionComparisonMatrixProps) {
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(
    report.options[0]?.option_id || null
  );

  const selectedOption =
    report.options.find((opt) => opt.option_id === selectedOptionId) ||
    report.options[0];

  return (
    <div
      role="region"
      aria-label="Alternative Strategic Options Comparison"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider font-semibold text-sky-400">
            Multi-Alternative Analysis
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Strategic Options Comparison Matrix
          </h2>
        </div>

        <div className="text-xs text-zinc-400 bg-zinc-800/80 px-3 py-1.5 rounded-lg border border-zinc-700 font-mono">
          {report.options.length} Viable Strategic Pathways Evaluated
        </div>
      </div>

      {/* Epistemic Calibration Banner */}
      <div className="rounded-xl border border-sky-900/40 bg-sky-950/20 p-3.5 text-xs text-sky-200/90 flex items-start gap-2.5">
        <svg
          className="h-4 w-4 text-sky-400 shrink-0 mt-0.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4m0-4h.01" />
        </svg>
        <p className="leading-relaxed">
          {report.comparison_matrix_note}
        </p>
      </div>

      {/* Option Selector Pills */}
      <div className="flex flex-wrap gap-2 pt-1" role="tablist" aria-label="Select Alternative">
        {report.options.map((opt) => (
          <button
            key={opt.option_id}
            role="tab"
            aria-selected={selectedOption?.option_id === opt.option_id}
            onClick={() => setSelectedOptionId(opt.option_id)}
            className={`cursor-pointer px-4 py-2 rounded-xl text-xs font-medium transition-all border ${
              selectedOption?.option_id === opt.option_id
                ? "bg-zinc-800 text-white border-zinc-600 shadow-md ring-1 ring-zinc-500/30"
                : "bg-zinc-950/60 text-zinc-400 border-zinc-800 hover:text-zinc-200 hover:bg-zinc-900"
            }`}
          >
            <div className="flex items-center gap-2">
              {opt.is_recommended && (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              )}
              <span>{opt.title}</span>
            </div>
          </button>
        ))}
      </div>

      {/* Selected Option Detail Card */}
      {selectedOption && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 sm:p-6 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-white">
                  {selectedOption.title}
                </h3>
                {selectedOption.is_recommended && (
                  <span className="inline-flex items-center rounded-md border border-emerald-800/80 bg-emerald-950/60 px-2.5 py-0.5 text-[11px] font-mono text-emerald-300">
                    AI Consensus Recommendation
                  </span>
                )}
              </div>
              <p className="text-xs text-zinc-400 mt-1 max-w-3xl leading-relaxed">
                {selectedOption.description}
              </p>
            </div>

            <div className="shrink-0">
              <span className="inline-flex items-center rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-mono text-zinc-300">
                {selectedOption.feasibility_status.toUpperCase()}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Strengths */}
            <div className="rounded-xl border border-emerald-900/30 bg-emerald-950/10 p-4 space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400 uppercase tracking-wider font-mono">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                <span>Strategic Strengths</span>
              </div>
              <ul className="space-y-1.5 text-xs text-zinc-300">
                {selectedOption.strengths.map((s, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-emerald-500 font-bold">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Weaknesses */}
            <div className="rounded-xl border border-rose-900/30 bg-rose-950/10 p-4 space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-rose-400 uppercase tracking-wider font-mono">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span>Downsides &amp; Vulnerabilities</span>
              </div>
              <ul className="space-y-1.5 text-xs text-zinc-300">
                {selectedOption.weaknesses.map((w, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-rose-500 font-bold">•</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Trade-offs & Evidence */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            <div className="bg-zinc-900/70 rounded-xl p-4 border border-zinc-800 space-y-1.5">
              <span className="text-[11px] font-mono text-zinc-400 uppercase">
                Constraint Compatibility
              </span>
              <p className="text-xs text-zinc-200 leading-relaxed font-medium">
                {selectedOption.constraint_compatibility}
              </p>
            </div>

            <div className="bg-zinc-900/70 rounded-xl p-4 border border-zinc-800 space-y-1.5">
              <span className="text-[11px] font-mono text-zinc-400 uppercase">
                Supporting Evidence
              </span>
              <div className="text-xs text-zinc-200 font-medium">
                {selectedOption.supporting_evidence_count > 0 ? (
                  <span>{selectedOption.supporting_evidence_count} direct citations evaluated</span>
                ) : (
                  <span className="text-amber-400">Zero dedicated citations (evaluated as conceptual counterfactual)</span>
                )}
              </div>
            </div>

            <div className="bg-zinc-900/70 rounded-xl p-4 border border-zinc-800 space-y-1.5">
              <span className="text-[11px] font-mono text-zinc-400 uppercase">
                Primary Trade-Off
              </span>
              <div className="text-xs text-zinc-200 font-medium">
                {selectedOption.key_tradeoffs[0] || "Investment speed vs operational disruption risk"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary Table View */}
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-zinc-950/80 text-zinc-400 font-mono uppercase text-[10px] border-b border-zinc-800">
            <tr>
              <th className="p-3">Strategic Pathway</th>
              <th className="p-3">Feasibility Status</th>
              <th className="p-3">Constraint Fit</th>
              <th className="p-3">Evidence Sources</th>
              <th className="p-3">Core Disadvantage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/80">
            {report.options.map((opt) => (
              <tr
                key={opt.option_id}
                onClick={() => setSelectedOptionId(opt.option_id)}
                className={`cursor-pointer transition-colors ${
                  selectedOption?.option_id === opt.option_id
                    ? "bg-zinc-800/60 text-white font-medium"
                    : "hover:bg-zinc-900/50 text-zinc-300"
                }`}
              >
                <td className="p-3 font-semibold flex items-center gap-2">
                  {opt.is_recommended && (
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                  )}
                  <span>{opt.title}</span>
                </td>
                <td className="p-3 font-mono text-[11px]">
                  <span
                    className={`inline-flex px-2 py-0.5 rounded ${
                      opt.feasibility_status === "feasible"
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                        : "bg-zinc-800 text-zinc-300 border border-zinc-700"
                    }`}
                  >
                    {opt.feasibility_status}
                  </span>
                </td>
                <td className="p-3 text-zinc-300 truncate max-w-[200px]" title={opt.constraint_compatibility}>
                  {opt.constraint_compatibility}
                </td>
                <td className="p-3 font-mono">{opt.supporting_evidence_count}</td>
                <td className="p-3 text-zinc-400 truncate max-w-[220px]" title={opt.weaknesses[0] || ""}>
                  {opt.weaknesses[0] || "None specified"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
