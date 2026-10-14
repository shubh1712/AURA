"use client";

import React from "react";
import type { ResilienceReport } from "@/types";
import { formatEnumLabel } from "@/lib/formatters";
import { getRatingMetadata, getStressTestMetadata } from "@/lib/resilienceHelpers";

interface ResilienceDriverChartProps {
  report: ResilienceReport;
}

export function ResilienceDriverChart({ report }: ResilienceDriverChartProps) {
  if (!report) return null;

  const ratingMeta = getRatingMetadata(report.rating || report.overall_score);
  const stressMeta = getStressTestMetadata(Boolean(report.stress_test_passed));

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-5"
      role="region"
      aria-label="Resilience Score Indicator and Pillar Breakdown"
    >
      {/* Header and Compact Score Indicator */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-indigo-400 font-semibold">
            Deterministic Robustness
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Resilience Score &amp; Driver Breakdown
          </h4>
        </div>

        {/* Compact Indicator */}
        <div className="flex items-center gap-3">
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-bold font-mono text-white">
              {typeof report.overall_score === "number" ? report.overall_score.toFixed(1) : "N/A"}
            </span>
            <span className="text-xs font-mono text-zinc-400">/ 100</span>
          </div>

          <span
            className={`inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-mono font-semibold uppercase tracking-wider ${ratingMeta.colorClass.badgeBg} ${ratingMeta.colorClass.badgeBorder} ${ratingMeta.colorClass.badgeText}`}
          >
            {ratingMeta.label}
          </span>

          <span
            className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-mono font-medium ${
              stressMeta.passed
                ? "border-emerald-800/80 bg-emerald-950/40 text-emerald-300"
                : "border-rose-800/80 bg-rose-950/40 text-rose-300"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full mr-1.5 ${
                stressMeta.passed ? "bg-emerald-400" : "bg-rose-400"
              }`}
            />
            {stressMeta.badgeLabel}
          </span>
        </div>
      </div>

      {/* 4-Pillar Driver Breakdown Bar Chart */}
      <div className="space-y-3.5">
        <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
          Pillar Driver Scores (0–25 each)
        </span>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          {(report.sub_scores || []).map((sub, idx) => {
            const scoreVal = typeof sub.score === "number" ? sub.score : 0;
            const max = sub.max_score || 25;
            const pct = Math.min(Math.max((scoreVal / max) * 100, 0), 100);
            const categoryLabel = formatEnumLabel(sub.category || sub.pillar);
            const isLow = pct < 60;

            return (
              <div
                key={sub.category || idx}
                className="rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3 space-y-1.5"
              >
                <div className="flex items-center justify-between text-xs gap-2">
                  <span className="font-medium text-zinc-200 truncate">
                    {categoryLabel}
                  </span>
                  <span className="font-mono text-xs font-bold text-zinc-100 shrink-0">
                    {scoreVal.toFixed(1)}{" "}
                    <span className="text-[10px] text-zinc-500 font-normal">/ {max}</span>
                  </span>
                </div>

                {/* Accessible Bar Meter */}
                <div className="space-y-1">
                  <svg
                    className="w-full h-2 rounded overflow-hidden bg-zinc-900"
                    role="img"
                    aria-label={`${categoryLabel}: ${sub.score.toFixed(1)} of ${max}`}
                  >
                    <rect width="100%" height="100%" fill="#18181b" />
                    <rect
                      width={`${pct}%`}
                      height="100%"
                      fill={isLow ? "#f59e0b" : "#6366f1"}
                      rx="2"
                    />
                  </svg>
                </div>

                <p className="text-[11px] text-zinc-400 line-clamp-1 font-sans">
                  {sub.rationale}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Top Vulnerabilities / Threshold Breaches Callout */}
      {report.critical_vulnerabilities && report.critical_vulnerabilities.length > 0 && (
        <div className="rounded-lg border border-rose-900/40 bg-rose-950/20 p-3.5 space-y-1.5">
          <span className="text-[11px] font-mono uppercase tracking-wider text-rose-400 font-semibold flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-400" />
            Active Threshold Breaches &amp; Critical Vulnerabilities ({report.critical_vulnerabilities.length})
          </span>
          <ul className="space-y-1 text-xs text-rose-200/90 list-disc list-inside">
            {report.critical_vulnerabilities.slice(0, 3).map((vuln, vIdx) => (
              <li key={vIdx} className="leading-relaxed">
                {vuln}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
