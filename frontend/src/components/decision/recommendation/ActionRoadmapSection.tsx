"use client";

import React, { useState } from "react";
import type { ActionPlan, ActionItem, ActionTimeHorizon } from "@/types";
import {
  PRIORITY_CONFIGS,
  TIME_HORIZON_CONFIGS,
} from "@/lib/recommendationHelpers";
import { DecisionGateCard } from "./DecisionGateCard";

interface ActionRoadmapSectionProps {
  actionPlan: ActionPlan;
}

export function ActionRoadmapSection({
  actionPlan,
}: ActionRoadmapSectionProps) {
  const [selectedHorizon, setSelectedHorizon] = useState<
    ActionTimeHorizon | "all"
  >("all");
  const [expandedActionIds, setExpandedActionIds] = useState<
    Record<string, boolean>
  >({});

  const toggleExpand = (id: string) => {
    setExpandedActionIds((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const expandAll = () => {
    const allExpanded: Record<string, boolean> = {};
    for (const a of actionPlan.actions) {
      allExpanded[a.id] = true;
    }
    setExpandedActionIds(allExpanded);
  };

  const collapseAll = () => {
    setExpandedActionIds({});
  };

  const filteredActions =
    selectedHorizon === "all"
      ? actionPlan.actions
      : actionPlan.actions.filter((a) => a.time_horizon === selectedHorizon);

  return (
    <section
      id="section-action-roadmap"
      aria-labelledby="action-roadmap-heading"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:break-inside-avoid print:bg-white print:text-black print:border-zinc-300"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-semibold print:text-zinc-700">
            Execution Strategy &amp; Governance
          </span>
          <h3
            id="action-roadmap-heading"
            className="text-xl font-bold text-white print:text-black tracking-tight mt-0.5"
          >
            Action Roadmap &amp; Execution Plan ({actionPlan.actions.length} Actions)
          </h3>
          <p className="text-xs sm:text-sm text-zinc-400 print:text-zinc-600 mt-1 max-w-2xl font-sans">
            Structured, prioritized actions with explicit dependencies, responsible roles, success metrics, and nested decision gates.
          </p>
        </div>

        {/* Global Expand / Collapse Controls */}
        <div className="flex items-center gap-2 print:hidden">
          <button
            type="button"
            onClick={expandAll}
            className="rounded px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors border border-zinc-800"
          >
            Expand All
          </button>
          <button
            type="button"
            onClick={collapseAll}
            className="rounded px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors border border-zinc-800"
          >
            Collapse All
          </button>
        </div>
      </div>

      {/* Plan Executive Summary */}
      {actionPlan.summary && (
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/60 p-4 sm:p-5 text-xs sm:text-sm text-zinc-300 print:text-zinc-900 leading-relaxed font-sans print:bg-zinc-50 print:border-zinc-300">
          <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold block mb-1">
            Roadmap Overview
          </span>
          {actionPlan.summary}
        </div>
      )}

      {/* Key Milestones Sequence */}
      {actionPlan.key_milestones && actionPlan.key_milestones.length > 0 && (
        <div className="space-y-3">
          <span className="text-xs font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold block">
            Key Execution Milestones ({actionPlan.key_milestones.length})
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {actionPlan.key_milestones.map((ms, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2.5 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-200 print:bg-white print:border-zinc-300 print:text-black"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950/80 text-emerald-300 text-[10px] font-mono font-bold border border-emerald-800/80 print:bg-zinc-100 print:text-black">
                  {idx + 1}
                </span>
                <span className="leading-snug font-medium font-sans pt-0.5">
                  {ms}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Time Horizon Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-zinc-800/60 print:hidden">
        <span className="text-xs text-zinc-400 font-medium mr-1">Time Horizon:</span>
        <button
          type="button"
          onClick={() => setSelectedHorizon("all")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer border ${
            selectedHorizon === "all"
              ? "bg-zinc-100 text-zinc-900 border-zinc-100 font-semibold"
              : "bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:text-zinc-200 hover:bg-zinc-800/60"
          }`}
        >
          All Horizons ({actionPlan.actions.length})
        </button>

        {(["immediate", "near_term", "medium_term", "long_term"] as ActionTimeHorizon[]).map(
          (horizon) => {
            const count = actionPlan.actions.filter((a) => a.time_horizon === horizon).length;
            if (count === 0) return null;
            const cfg = TIME_HORIZON_CONFIGS[horizon];
            const isSelected = selectedHorizon === horizon;

            return (
              <button
                key={horizon}
                type="button"
                onClick={() => setSelectedHorizon(horizon)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer border ${
                  isSelected
                    ? "bg-zinc-100 text-zinc-900 border-zinc-100 font-semibold"
                    : "bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:text-zinc-200 hover:bg-zinc-800/60"
                }`}
              >
                {cfg.label} ({count})
              </button>
            );
          }
        )}
      </div>

      {/* Actions List */}
      <div className="space-y-4">
        {filteredActions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-900/20 p-6 text-center text-xs text-zinc-500">
            No action items categorized under this time horizon.
          </div>
        ) : (
          filteredActions.map((action, actionIdx) => (
            <ActionItemCard
              key={action.id}
              action={action}
              index={actionIdx}
              isExpanded={Boolean(expandedActionIds[action.id])}
              onToggle={() => toggleExpand(action.id)}
            />
          ))
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------
// Single Action Item Card Component
// ------------------------------------------------------------------------------

interface ActionItemCardProps {
  action: ActionItem;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}

function ActionItemCard({
  action,
  index,
  isExpanded,
  onToggle,
}: ActionItemCardProps) {
  const priorityCfg = PRIORITY_CONFIGS[action.priority] ?? {
    label: action.priority.toUpperCase(),
    badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
    dotClass: "bg-zinc-400",
  };

  const horizonCfg = TIME_HORIZON_CONFIGS[action.time_horizon] ?? {
    label: action.time_horizon,
    timeWindow: "",
    badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
  };

  const hasGates = action.decision_gates && action.decision_gates.length > 0;

  return (
    <article
      className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-5 space-y-4 shadow-sm print:break-inside-avoid print:bg-white print:border-zinc-300 print:text-black transition-colors"
      aria-label={`Action Item ${index + 1}: ${action.title}`}
    >
      {/* Top Header: Number, Title, Priority, Role, Horizon */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 pb-3 border-b border-zinc-800/70 print:border-zinc-300">
        <div className="space-y-1.5 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {/* Priority Badge */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold border ${priorityCfg.badgeClass} print:bg-zinc-100 print:text-black print:border-zinc-400`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${priorityCfg.dotClass} print:bg-black`} />
              {priorityCfg.label}
            </span>

            {/* Time Horizon Badge */}
            <span
              className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium border ${horizonCfg.badgeClass} print:bg-zinc-100 print:text-black print:border-zinc-400`}
            >
              {horizonCfg.label} {horizonCfg.timeWindow && `(${horizonCfg.timeWindow})`}
            </span>

            {/* Responsible Role */}
            <span className="text-[11px] font-mono text-zinc-300 print:text-zinc-800 bg-zinc-900/90 px-2 py-0.5 rounded border border-zinc-800 print:border-zinc-300">
              Role: <strong className="text-white print:text-black font-semibold">{action.responsible_role}</strong>
            </span>
          </div>

          <h4 className="text-base sm:text-lg font-semibold text-white print:text-black tracking-tight pt-1">
            <span className="font-mono text-zinc-500 mr-2 text-sm">#{index + 1}</span>
            {action.title}
          </h4>
        </div>

        {/* Expand / Collapse Toggle Button */}
        <div className="flex items-center gap-2 shrink-0 print:hidden">
          <span className="font-mono text-[10px] text-zinc-500">
            {action.id}
          </span>
          <button
            type="button"
            onClick={onToggle}
            className="rounded px-2.5 py-1 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition-colors border border-zinc-800"
            aria-expanded={isExpanded}
            aria-label={`${isExpanded ? "Collapse" : "Expand"} details for ${action.title}`}
          >
            {isExpanded ? "Hide Details" : "Details"}
          </button>
        </div>
      </div>

      {/* Core Objective */}
      <div className="space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold block">
          Strategic Objective
        </span>
        <p className="text-xs sm:text-sm text-zinc-200 print:text-zinc-900 font-medium leading-relaxed font-sans">
          {action.objective}
        </p>
      </div>

      {/* Description */}
      <div className="space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold block">
          Description &amp; Operational Scope
        </span>
        <p className="text-xs text-zinc-300 print:text-zinc-800 leading-relaxed font-sans whitespace-pre-line">
          {action.description}
        </p>
      </div>

      {/* Dependencies & Metrics Summary (Always Visible) */}
      <div className="flex flex-wrap gap-4 pt-1 text-xs font-mono text-zinc-400 print:text-zinc-700">
        {action.dependencies && action.dependencies.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-zinc-500 font-semibold">Prerequisite Dependencies:</span>
            {action.dependencies.map((dep, depIdx) => (
              <span
                key={depIdx}
                className="bg-zinc-900 text-zinc-300 border border-zinc-800 px-2 py-0.5 rounded text-[11px] print:bg-zinc-100 print:text-black print:border-zinc-300"
              >
                {dep}
              </span>
            ))}
          </div>
        )}

        {hasGates && (
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1 text-amber-400 font-semibold text-[11px]">
              <svg
                className="h-3 w-3"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              {action.decision_gates.length} Decision Gate{action.decision_gates.length > 1 ? "s" : ""} Attached
            </span>
          </div>
        )}
      </div>

      {/* Expandable Section: Success Metrics, Risk Mitigations, Fallback, Nested Decision Gates */}
      {/* On print, this section is always displayed via CSS print:block */}
      <div className={`${isExpanded ? "block" : "hidden"} print:block space-y-4 pt-3 border-t border-zinc-800/60 print:border-zinc-300`}>
        {/* Success Metrics */}
        {action.success_metrics && action.success_metrics.length > 0 && (
          <div className="space-y-1.5 bg-zinc-900/30 p-3.5 rounded-lg border border-zinc-800/50 print:bg-white print:border-zinc-300">
            <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold flex items-center gap-1">
              <svg
                className="h-3.5 w-3.5 text-emerald-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Success Metrics &amp; Validation Criteria
            </span>
            <ul className="space-y-1 pt-1 list-none text-xs text-zinc-300 print:text-zinc-800">
              {action.success_metrics.map((metric, mIdx) => (
                <li key={mIdx} className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                  <span className="font-sans leading-relaxed">{metric}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Risk Mitigations */}
        {action.risk_mitigations && action.risk_mitigations.length > 0 && (
          <div className="space-y-1.5 bg-zinc-900/30 p-3.5 rounded-lg border border-zinc-800/50 print:bg-white print:border-zinc-300">
            <span className="text-[10px] font-mono uppercase tracking-wider text-amber-400 font-semibold flex items-center gap-1">
              <svg
                className="h-3.5 w-3.5 text-amber-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              Risk Mitigations
            </span>
            <ul className="space-y-1 pt-1 list-none text-xs text-zinc-300 print:text-zinc-800">
              {action.risk_mitigations.map((mit, rIdx) => (
                <li key={rIdx} className="flex items-start gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                  <span className="font-sans leading-relaxed">{mit}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Fallback Action */}
        {action.fallback_action && (
          <div className="space-y-1 bg-rose-950/20 p-3.5 rounded-lg border border-rose-900/40 text-xs print:bg-white print:border-zinc-300">
            <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold block">
              Fallback / Contingency Action
            </span>
            <p className="text-zinc-200 print:text-zinc-800 leading-relaxed font-sans">
              {action.fallback_action}
            </p>
          </div>
        )}

        {/* Nested Decision Gates */}
        {hasGates && (
          <div className="space-y-3 pt-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-amber-400 font-semibold block">
              Associated Decision Gates ({action.decision_gates.length})
            </span>
            <div className="space-y-3">
              {action.decision_gates.map((gate, gIdx) => (
                <DecisionGateCard key={gate.id} gate={gate} index={gIdx} />
              ))}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
