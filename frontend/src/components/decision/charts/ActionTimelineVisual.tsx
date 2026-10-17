"use client";

import React, { useState } from "react";
import type { IntelligentActionItem, ActionItem } from "@/types";
import { formatEnumLabel } from "@/lib/formatters";

type UnifiedAction = IntelligentActionItem | ActionItem;

interface ActionTimelineVisualProps {
  actions: UnifiedAction[];
}

function isIntelligentAction(act: UnifiedAction): act is IntelligentActionItem {
  return "owner_role" in act || "success_criteria" in act;
}

export function ActionTimelineVisual({ actions }: ActionTimelineVisualProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!actions || actions.length === 0) {
    return null;
  }

  // Create lookup map for action titles
  const actionMap = new Map<string, UnifiedAction>();
  actions.forEach((a) => {
    const id = isIntelligentAction(a) ? a.action_id : a.id;
    actionMap.set(id, a);
  });

  // Calculate priority & dependency breakdown for visual strip
  const priorityCounts = actions.reduce(
    (acc, a) => {
      const p = (a.priority || "medium").toLowerCase();
      if (p === "critical") acc.critical++;
      else if (p === "high") acc.high++;
      else if (p === "medium") acc.medium++;
      else acc.low++;
      return acc;
    },
    { critical: 0, high: 0, medium: 0, low: 0 }
  );

  const totalActions = actions.length;
  const criticalHighCount = priorityCounts.critical + priorityCounts.high;
  const totalDepsCount = actions.reduce((acc, a) => acc + (a.dependencies?.length || 0), 0);

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4"
      role="region"
      aria-label="Action Execution Timeline and Dependency Visualization"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
            Operational Roadmap
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Sequential Timeline &amp; Dependency Flow
          </h4>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-zinc-300 bg-zinc-900 px-2.5 py-0.5 rounded border border-zinc-800">
            {actions.length} Sequenced Actions
          </span>
          {totalDepsCount > 0 && (
            <span className="text-[11px] font-mono text-sky-300 bg-sky-950/40 px-2 py-0.5 rounded border border-sky-800/60">
              {totalDepsCount} Dependencies Mapped
            </span>
          )}
        </div>
      </div>

      {/* Execution Priority Distribution Strip */}
      <div className="rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3 space-y-2 text-xs">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 text-[11px] font-mono">
          <span className="text-zinc-400">
            Execution Priority Load:{" "}
            <strong className={criticalHighCount > 0 ? "text-amber-300" : "text-emerald-300"}>
              {criticalHighCount} High/Critical
            </strong>{" "}
            of {totalActions} actions
          </span>
          <div className="flex items-center gap-2 text-[10px]">
            {priorityCounts.critical > 0 && (
              <span className="text-rose-400">● {priorityCounts.critical} Critical</span>
            )}
            {priorityCounts.high > 0 && (
              <span className="text-orange-400">● {priorityCounts.high} High</span>
            )}
            {priorityCounts.medium > 0 && (
              <span className="text-amber-400">● {priorityCounts.medium} Medium</span>
            )}
            {priorityCounts.low > 0 && (
              <span className="text-emerald-400">● {priorityCounts.low} Low</span>
            )}
          </div>
        </div>

        {/* Stacked Priority Bar */}
        <div
          className="h-2 w-full bg-zinc-900 rounded-full overflow-hidden flex border border-zinc-800"
          role="progressbar"
          aria-label="Action priority distribution"
        >
          {priorityCounts.critical > 0 && (
            <div
              style={{ width: `${(priorityCounts.critical / totalActions) * 100}%` }}
              className="bg-rose-500 h-full"
              title={`${priorityCounts.critical} Critical Actions`}
            />
          )}
          {priorityCounts.high > 0 && (
            <div
              style={{ width: `${(priorityCounts.high / totalActions) * 100}%` }}
              className="bg-orange-500 h-full"
              title={`${priorityCounts.high} High Priority Actions`}
            />
          )}
          {priorityCounts.medium > 0 && (
            <div
              style={{ width: `${(priorityCounts.medium / totalActions) * 100}%` }}
              className="bg-amber-500 h-full"
              title={`${priorityCounts.medium} Medium Priority Actions`}
            />
          )}
          {priorityCounts.low > 0 && (
            <div
              style={{ width: `${(priorityCounts.low / totalActions) * 100}%` }}
              className="bg-emerald-500 h-full"
              title={`${priorityCounts.low} Low Priority Actions`}
            />
          )}
        </div>
      </div>

      {/* Visual Timeline Sequence */}
      <div className="space-y-3 relative before:absolute before:inset-0 before:left-5 before:w-0.5 before:bg-zinc-800/80 before:z-0">
        {actions.map((act, idx) => {
          const actId = isIntelligentAction(act) ? act.action_id : act.id;
          const seq = isIntelligentAction(act) ? act.sequence : idx + 1;
          const role = isIntelligentAction(act) ? act.owner_role : act.responsible_role;
          const horizon = isIntelligentAction(act) ? act.timing : act.time_horizon;
          const deps = act.dependencies || [];
          const isExpanded = expandedId === actId;
          const execSteps = isIntelligentAction(act)
            ? act.execution_steps?.filter((s) => s && s.trim().length > 0 && !s.toLowerCase().includes("primary execution procedure defined in description"))
            : [];

          return (
            <div
              key={actId || idx}
              className="relative z-10 flex items-start gap-3.5 group"
            >
              {/* Sequence Node Circle */}
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-xs font-mono font-bold text-white shadow-sm group-hover:border-emerald-500 transition-colors">
                #{seq}
              </div>

              {/* Action Card */}
              <div className="flex-1 rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3.5 space-y-2 text-xs transition-colors hover:border-zinc-700">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
                  <h5 className="font-semibold text-white text-xs sm:text-sm">
                    {act.title}
                  </h5>

                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                        act.priority === "high" || act.priority === "critical"
                          ? "bg-rose-950/60 text-rose-300 border border-rose-800/60"
                          : act.priority === "medium"
                          ? "bg-amber-950/60 text-amber-300 border border-amber-800/60"
                          : "bg-emerald-950/60 text-emerald-300 border border-emerald-800/60"
                      }`}
                    >
                      {act.priority}
                    </span>

                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : actId)}
                      className="text-[10px] text-zinc-400 hover:text-zinc-200 underline font-mono"
                    >
                      {isExpanded ? "Collapse" : "Details"}
                    </button>
                  </div>
                </div>

                {/* Metadata Row: Role & Timing */}
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                  <span>
                    Role: <strong className="text-zinc-200 font-medium">{role || "Unassigned"}</strong>
                  </span>
                  <span>&bull;</span>
                  <span>
                    Phase: <strong className="text-zinc-200 font-medium">{formatEnumLabel(horizon) || "Not specified"}</strong>
                  </span>
                </div>

                {/* Dependencies Linkages */}
                {deps.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span className="text-[10px] font-mono uppercase text-zinc-500">Requires:</span>
                    {deps.map((depId) => {
                      const depAction = actionMap.get(depId);
                      const depSeq = depAction ? (isIntelligentAction(depAction) ? depAction.sequence : null) : null;
                      return (
                        <span
                          key={depId}
                          className="rounded bg-indigo-950/50 border border-indigo-800/50 px-1.5 py-0.2 text-[10px] font-mono text-indigo-300"
                        >
                          {depSeq ? `Action #${depSeq}` : depId}
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Expanded Concrete Execution Steps (ONLY when real steps exist, NO placeholders!) */}
                {isExpanded && (
                  <div className="pt-2 border-t border-zinc-800/60 space-y-2">
                    <p className="text-zinc-300 leading-relaxed font-sans">
                      {act.description}
                    </p>

                    {execSteps && execSteps.length > 0 && (
                      <div className="space-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
                          Concrete Execution Steps:
                        </span>
                        <ol className="list-decimal list-inside space-y-1 text-zinc-200 pl-1">
                          {execSteps.map((step, sIdx) => (
                            <li key={sIdx} className="leading-snug">
                              {step}
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
