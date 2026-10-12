"use client";

import React from "react";
import type { EvidenceQualityReport, SourceCategory } from "@/types";

interface EvidenceQualityCardProps {
  report: EvidenceQualityReport;
}

export function EvidenceQualityCard({ report }: EvidenceQualityCardProps) {
  const getCategoryLabel = (cat: SourceCategory) => {
    switch (cat) {
      case "primary_empirical":
        return { label: "Primary Empirical", color: "text-emerald-400 bg-emerald-950/60 border-emerald-800" };
      case "official_standard":
        return { label: "Official Standards / Gov", color: "text-blue-400 bg-blue-950/60 border-blue-800" };
      case "independent_secondary":
        return { label: "Independent Secondary", color: "text-sky-400 bg-sky-950/60 border-sky-800" };
      case "vendor_produced":
        return { label: "Vendor-Produced Material", color: "text-amber-400 bg-amber-950/60 border-amber-800" };
      case "opinion_commentary":
        return { label: "Opinion / Commentary", color: "text-purple-400 bg-purple-950/60 border-purple-800" };
      case "unknown":
      default:
        return { label: "Unknown Classification", color: "text-zinc-400 bg-zinc-800 border-zinc-700" };
    }
  };

  const independencePct = Math.round(report.independence_ratio * 100);

  return (
    <div
      role="region"
      aria-label="Evidence Quality & Epistemic Calibration"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider font-semibold text-blue-400">
            Epistemic Integrity
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Evidence Quality &amp; Source Provenance
          </h2>
        </div>

        <div className="flex items-center gap-3">
          {report.duplicate_sources_detected > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono bg-amber-950/60 border border-amber-800/80 text-amber-300">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              {report.duplicate_sources_detected} Duplicate Citation{report.duplicate_sources_detected === 1 ? "" : "s"}
            </span>
          )}

          <div className="text-xs text-zinc-300 bg-zinc-800/80 px-3 py-1.5 rounded-lg border border-zinc-700 font-mono">
            {report.total_sources} Total Source{report.total_sources === 1 ? "" : "s"}
          </div>
        </div>
      </div>

      {/* Independence Gauge Banner */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <span className="text-xs font-semibold text-white block">
            Empirical Independence Ratio
          </span>
          <p className="text-xs text-zinc-400 max-w-xl leading-relaxed">
            Measures the proportion of evidence originating from independent third parties, academic research, or regulatory standards rather than vendor-published marketing material.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="text-right">
            <div className="text-2xl font-bold font-mono text-blue-400">
              {independencePct}%
            </div>
            <span className="text-[10px] font-mono text-zinc-500 uppercase">
              Independent Sources
            </span>
          </div>
          <div className="w-16 bg-zinc-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-blue-500 h-2 rounded-full"
              style={{ width: `${independencePct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Category Breakdown Badges */}
      <div className="space-y-2">
        <span className="text-xs font-mono uppercase text-zinc-400 font-semibold block">
          Source Category Distribution
        </span>
        <div className="flex flex-wrap gap-2">
          {Object.entries(report.category_breakdown).map(([catKey, count]) => {
            const cat = getCategoryLabel(catKey as SourceCategory);
            return (
              <div
                key={catKey}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-mono ${cat.color}`}
              >
                <span>{cat.label}</span>
                <span className="font-bold bg-black/30 px-1.5 py-0.5 rounded text-[11px]">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sources Directory Table */}
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-zinc-950/80 text-zinc-400 font-mono uppercase text-[10px] border-b border-zinc-800">
            <tr>
              <th className="p-3">Source Title</th>
              <th className="p-3">Category</th>
              <th className="p-3">Independence</th>
              <th className="p-3">Limitations &amp; Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/80">
            {report.classifications.map((s) => {
              const cat = getCategoryLabel(s.category);
              return (
                <tr key={s.source_id} className="hover:bg-zinc-900/50 text-zinc-300">
                  <td className="p-3">
                    <div className="font-medium text-white truncate max-w-[280px]" title={s.title}>
                      {s.title}
                    </div>
                    {s.url && (
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[11px] font-mono text-sky-400 hover:underline truncate block max-w-[280px]"
                        title={s.url}
                      >
                        {s.url}
                      </a>
                    )}
                  </td>
                  <td className="p-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border ${cat.color}`}>
                      {cat.label}
                    </span>
                  </td>
                  <td className="p-3 font-mono text-[11px]">
                    {s.is_duplicate ? (
                      <span className="text-amber-400 font-semibold">[Duplicate Citation]</span>
                    ) : s.is_independent ? (
                      <span className="text-emerald-400">Independent</span>
                    ) : (
                      <span className="text-amber-400">Vendor Primary</span>
                    )}
                  </td>
                  <td className="p-3 text-zinc-400 text-[11px]">
                    {s.credibility_notes}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
