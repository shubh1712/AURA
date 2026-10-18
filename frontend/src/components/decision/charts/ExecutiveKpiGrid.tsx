"use client";

import React from "react";
import type { ExecutiveKPI } from "@/lib/visualIntelligence";

interface ExecutiveKpiGridProps {
  kpis: ExecutiveKPI[];
}

export function ExecutiveKpiGrid({ kpis }: ExecutiveKpiGridProps) {
  if (!kpis || kpis.length === 0) return null;

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3"
      role="region"
      aria-label="Executive Decision Key Indicators"
    >
      {kpis.map((kpi) => (
        <div
          key={kpi.id}
          className={`rounded-xl border p-3.5 flex flex-col justify-between transition-all hover:border-zinc-700 shadow-sm ${kpi.statusClass}`}
        >
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
              <span className="truncate">{kpi.label}</span>
              <span className="text-xs font-bold shrink-0">{kpi.icon}</span>
            </div>
            <div className="text-base sm:text-lg font-bold text-white tracking-tight leading-tight">
              {kpi.value}
            </div>
          </div>

          {kpi.subtext && (
            <div className="text-[10px] text-zinc-300 font-sans leading-snug pt-2 border-t border-white/10 mt-2 line-clamp-2">
              {kpi.subtext}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
