"use client";

import React from "react";
import type { StageProgressionItem } from "@/lib/visualIntelligence";

interface StageProgressionTrackerProps {
  stages: StageProgressionItem[];
  onSelectStage?: (stageId: string) => void;
  openSections?: Record<string, boolean>;
}

export function StageProgressionTracker({
  stages,
  onSelectStage,
  openSections,
}: StageProgressionTrackerProps) {
  if (!stages || stages.length === 0) return null;

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 space-y-3"
      role="region"
      aria-label="Six-Stage Decision Engine Progression Tracker"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-purple-400 font-bold">
            Audit Pipeline Flow
          </span>
          <span className="h-1.5 w-1.5 rounded-full bg-purple-400" />
        </div>
        <span className="text-[11px] font-mono text-zinc-400">
          Click any stage to expand and inspect its artifacts
        </span>
      </div>

      {/* 6-Stage Horizontal Progress Flow */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 min-w-0">
        {stages.map((st) => {
          const isOpen = openSections ? openSections[st.id] : false;

          return (
            <button
              key={st.stage}
              type="button"
              onClick={() => onSelectStage?.(st.id)}
              className={`rounded-lg p-2.5 text-left border transition-all duration-200 motion-reduce:transition-none cursor-pointer flex flex-col justify-between select-none min-w-0 overflow-hidden ${
                isOpen
                  ? "border-purple-500/80 bg-zinc-900/90 shadow-sm ring-1 ring-purple-500/30"
                  : st.isComplete
                  ? "border-zinc-800 bg-zinc-900/40 hover:bg-zinc-800/50 hover:border-zinc-700"
                  : "border-zinc-850 bg-zinc-950/30 opacity-60"
              }`}
              title={st.title}
            >
              <div className="min-w-0">
                <div className="flex items-center justify-between text-[10px] font-mono mb-1 min-w-0">
                  <span className="text-zinc-400 font-semibold truncate">Stage {st.stage}</span>
                  <span
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      st.isComplete ? "bg-emerald-400" : "bg-zinc-600"
                    }`}
                  />
                </div>
                <div className="text-xs font-bold text-white tracking-tight truncate min-w-0" title={st.title}>
                  {st.shortName.replace(/^\d+\.\s*/, "")}
                </div>
              </div>

              <div className="pt-2 border-t border-zinc-800/60 mt-2 text-[10px] font-mono text-zinc-400 truncate min-w-0" title={st.metricLabel}>
                {st.metricLabel}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
