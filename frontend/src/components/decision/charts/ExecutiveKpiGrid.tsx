"use client";

import React from "react";
import type { ExecutiveKPI } from "@/lib/visualIntelligence";

interface ExecutiveKpiGridProps {
  kpis: ExecutiveKPI[];
}

function getKpiValueFontSize(val: string): string {
  const len = val ? val.length : 0;
  if (len > 30) return "text-xs sm:text-xs leading-snug";
  if (len > 18) return "text-xs sm:text-sm leading-snug";
  if (len > 10) return "text-sm sm:text-base leading-tight";
  return "text-base sm:text-lg leading-tight";
}

export function ExecutiveKpiGrid({ kpis }: ExecutiveKpiGridProps) {
  if (!kpis || kpis.length === 0) return null;

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 min-w-0"
      role="region"
      aria-label="Executive Decision Key Indicators"
    >
      {kpis.map((kpi) => (
        <div
          key={kpi.id}
          className={`rounded-xl border p-3.5 flex flex-col justify-between transition-all duration-200 hover:border-zinc-600 hover:shadow-md min-w-0 overflow-hidden motion-reduce:transition-none ${kpi.statusClass}`}
        >
          <div className="space-y-1 min-w-0">
            <div className="flex items-center justify-between gap-1.5 text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold min-w-0">
              <span className="truncate min-w-0" title={kpi.label}>
                {kpi.label}
              </span>
              <span className="text-xs font-bold shrink-0">{kpi.icon}</span>
            </div>
            <div
              className={`font-bold text-white tracking-tight break-words [overflow-wrap:anywhere] min-w-0 ${getKpiValueFontSize(
                kpi.value
              )}`}
              title={kpi.value}
            >
              {kpi.value}
            </div>
          </div>

          {kpi.subtext && (
            <div
              className="text-[10px] text-zinc-300 font-sans leading-snug pt-2 border-t border-white/10 mt-2 break-words [overflow-wrap:anywhere] min-w-0"
              title={kpi.subtext}
            >
              {kpi.subtext}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

