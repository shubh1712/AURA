"use client";

import React, { useState, useMemo } from "react";
import type { IntelligentActionItem, ActionPriority } from "@/types";

interface ActionRoadmapSectionProps {
  actions: IntelligentActionItem[];
}

function getPriorityBadgeClass(priority: ActionPriority): string {
  switch (priority) {
    case "high":
      return "border-rose-800/60 bg-rose-950/40 text-rose-300 print:bg-zinc-100 print:text-black print:border-zinc-400";
    case "medium":
      return "border-amber-800/60 bg-amber-950/40 text-amber-300 print:bg-zinc-100 print:text-black print:border-zinc-400";
    case "low":
      return "border-emerald-800/60 bg-emerald-950/40 text-emerald-300 print:bg-zinc-100 print:text-black print:border-zinc-400";
    default:
      return "border-zinc-700 bg-zinc-800 text-zinc-300";
  }
}

export function ActionIntelligenceRoadmapSection({ actions }: ActionRoadmapSectionProps) {
  const [expandedActionIds, setExpandedActionIds] = useState<Record<string, boolean>>({});

  // Sort actions sequentially
  const sortedActions = useMemo(() => {
    return [...actions].sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  }, [actions]);

  // Lookup map to resolve dependency titles
  const actionMap = useMemo(() => {
    const map = new Map<string, IntelligentActionItem>();
    actions.forEach((act) => {
      map.set(act.action_id, act);
    });
    return map;
  }, [actions]);

  const toggleExpand = (actionId: string) => {
    setExpandedActionIds((prev) => ({
      ...prev,
      [actionId]: !prev[actionId],
    }));
  };

  const expandAll = () => {
    const next: Record<string, boolean> = {};
    actions.forEach((a) => {
      next[a.action_id] = true;
    });
    setExpandedActionIds(next);
  };

  const collapseAll = () => {
    setExpandedActionIds({});
  };

  return (
    <div id="action-roadmap-section" className="space-y-4">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-1">
        <div>
          <h3 className="text-base font-semibold text-white print:text-black tracking-tight">
            Prioritized Execution Roadmap
          </h3>
          <p className="text-xs text-zinc-400 print:text-zinc-600">
            Sequenced action items grounded in authoritative Stage 4 recommendations.
          </p>
        </div>

        <div className="flex items-center gap-2 print:hidden">
          <button
            type="button"
            onClick={expandAll}
            className="text-xs font-mono text-zinc-400 hover:text-zinc-200 cursor-pointer underline transition-colors"
          >
            Expand All
          </button>
          <span className="text-zinc-600 text-xs">|</span>
          <button
            type="button"
            onClick={collapseAll}
            className="text-xs font-mono text-zinc-400 hover:text-zinc-200 cursor-pointer underline transition-colors"
          >
            Collapse All
          </button>
        </div>
      </div>

      {/* Action Cards List */}
      <div className="space-y-4">
        {sortedActions.map((action) => {
          const isExpanded = Boolean(expandedActionIds[action.action_id]);
          const priorityClass = getPriorityBadgeClass(action.priority);

          return (
            <div
              key={action.action_id}
              id={`action-card-${action.action_id}`}
              className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-4 text-zinc-100 shadow-sm transition-colors hover:border-zinc-700/80 print:border-zinc-300 print:bg-white print:text-black"
            >
              {/* Card Header */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800 text-xs font-mono font-bold text-zinc-200 print:bg-zinc-100 print:border-zinc-400 print:text-black">
                    #{action.sequence}
                  </span>
                  <div>
                    <h4 className="text-sm sm:text-base font-semibold text-white print:text-black tracking-tight">
                      {action.title}
                    </h4>
                    <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-zinc-400 print:text-zinc-600">
                      <span className="font-mono text-zinc-500">[{action.action_id}]</span>
                      <span>&bull;</span>
                      <span>
                        Role: <span className="font-medium text-zinc-300 print:text-black">{action.owner_role || "Not specified"}</span>
                      </span>
                      <span>&bull;</span>
                      <span>
                        Timing: <span className="font-medium text-zinc-300 print:text-black">{action.timing || "Not specified"}</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-mono font-medium capitalize ${priorityClass}`}
                  >
                    {action.priority} Priority
                  </span>

                  <button
                    type="button"
                    onClick={() => toggleExpand(action.action_id)}
                    className="inline-flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer print:hidden"
                    aria-expanded={isExpanded}
                    aria-controls={`action-details-${action.action_id}`}
                  >
                    <span>{isExpanded ? "Hide Details" : "View Details"}</span>
                    <svg
                      className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Description */}
              <p className="text-xs sm:text-sm leading-relaxed text-zinc-300 print:text-black">
                {action.description || "Not specified"}
              </p>

              {/* Execution Steps */}
              <div className="space-y-1.5 pt-1">
                <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-700">
                  Execution Steps:
                </span>
                {action.execution_steps && action.execution_steps.length > 0 ? (
                  <ol className="list-decimal list-inside space-y-1 text-xs text-zinc-200 print:text-black pl-1">
                    {action.execution_steps.map((step, idx) => (
                      <li key={idx} className="leading-relaxed">
                        {step}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="text-xs text-zinc-400 italic">
                    Primary execution procedure defined in description above.
                  </div>
                )}
              </div>

              {/* Dependencies Awareness */}
              {action.dependencies && action.dependencies.length > 0 && (
                <div className="pt-2 border-t border-zinc-800/80 space-y-1.5 print:border-zinc-200">
                  <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-700">
                    Dependencies (Must Precede):
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {action.dependencies.map((depId) => {
                      const depAction = actionMap.get(depId);
                      if (depAction) {
                        return (
                          <span
                            key={depId}
                            className="inline-flex items-center gap-1.5 rounded-md border border-indigo-900/60 bg-indigo-950/40 px-2.5 py-1 text-xs font-medium text-indigo-300 print:border-zinc-300 print:bg-zinc-100 print:text-black"
                          >
                            <span className="font-mono text-[11px] text-indigo-400 print:text-zinc-600">
                              #{depAction.sequence}
                            </span>
                            <span>{depAction.title}</span>
                          </span>
                        );
                      } else {
                        return (
                          <span
                            key={depId}
                            className="inline-flex items-center gap-1.5 rounded-md border border-amber-800/60 bg-amber-950/40 px-2.5 py-1 text-xs font-medium text-amber-300 print:border-zinc-300 print:bg-zinc-100 print:text-black"
                            title="Referenced dependency not found in current plan."
                          >
                            <span className="font-mono text-[11px]">[{depId}]</span>
                            <span className="italic">(Unresolved Reference)</span>
                          </span>
                        );
                      }
                    })}
                  </div>
                </div>
              )}

              {/* Expandable Details Container */}
              <div
                id={`action-details-${action.action_id}`}
                className={`space-y-4 pt-3 border-t border-zinc-800/80 print:block ${
                  isExpanded ? "block" : "hidden print:block"
                }`}
              >
                {/* Prerequisites */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-700">
                    Prerequisites:
                  </span>
                  {action.prerequisites && action.prerequisites.length > 0 ? (
                    <ul className="list-disc list-inside space-y-1 text-xs text-zinc-300 print:text-black pl-1">
                      {action.prerequisites.map((prereq, idx) => (
                        <li key={idx} className="leading-relaxed">
                          {prereq}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-xs text-zinc-500">Not specified.</div>
                  )}
                </div>

                {/* Success Criteria */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-700">
                    Verification &amp; Success Criteria:
                  </span>
                  {action.success_criteria && action.success_criteria.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {action.success_criteria.map((crit) => (
                        <div
                          key={crit.criterion_id}
                          className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5 text-xs space-y-1 print:border-zinc-300 print:bg-zinc-50"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold text-zinc-200 print:text-black">
                              {crit.description}
                            </span>
                            {crit.is_hard && (
                              <span className="rounded bg-rose-950/60 border border-rose-800/60 px-1.5 py-0.5 text-[10px] font-mono text-rose-300">
                                HARD FLOOR
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] font-mono text-zinc-400 print:text-zinc-600">
                            Threshold: {crit.operator || ""} {crit.threshold_raw || crit.threshold_value || "Qualitative"} {crit.unit || ""}
                          </div>
                          {crit.source_reference && (
                            <div className="text-[10px] font-mono text-zinc-500">
                              Ref: {crit.source_reference}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-zinc-500">Not specified.</div>
                  )}
                </div>

                {/* Risk Mitigations */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-zinc-400 print:text-zinc-700">
                    Risk Mitigations:
                  </span>
                  {action.risk_mitigations && action.risk_mitigations.length > 0 ? (
                    <ul className="list-disc list-inside space-y-1 text-xs text-zinc-300 print:text-black pl-1">
                      {action.risk_mitigations.map((mit, idx) => (
                        <li key={idx} className="leading-relaxed">
                          {mit}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-xs text-zinc-500">Not specified.</div>
                  )}
                </div>

                {/* Contingency / Rollback Instructions */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-mono uppercase tracking-wider font-semibold text-amber-400 print:text-zinc-800">
                    Contingency &amp; Rollback Protocol:
                  </span>
                  {action.contingency_or_rollback ? (
                    <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs leading-relaxed text-amber-200/90 print:border-zinc-300 print:bg-zinc-50 print:text-zinc-800">
                      {action.contingency_or_rollback}
                    </div>
                  ) : (
                    <div className="text-xs text-zinc-500">Not specified.</div>
                  )}
                </div>

                {/* Rationale & Confidence */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 text-xs text-zinc-400 print:text-zinc-600">
                  <div>
                    <span className="font-semibold text-zinc-300 print:text-black">Rationale:</span>{" "}
                    {action.rationale || "Not specified"}
                  </div>
                  <div>
                    <span className="font-semibold text-zinc-300 print:text-black">Confidence:</span>{" "}
                    <span className="capitalize text-zinc-200 print:text-black">{action.confidence_label}</span>
                    {action.confidence_rationale && ` — ${action.confidence_rationale}`}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
