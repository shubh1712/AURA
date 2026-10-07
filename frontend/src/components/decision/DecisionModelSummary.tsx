"use client";

import React, { useState } from "react";
import type { DecisionModel } from "@/types";

interface DecisionModelSummaryProps {
  model: DecisionModel;
}

function formatSnakeCase(str: string): string {
  return str
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function DecisionModelSummary({ model }: DecisionModelSummaryProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  const { decision, complexity, objectives, variables, tradeoffs, assumptions, unknowns, constraints } = model;

  const validObjectives = objectives.filter(
    (obj) => obj.description && obj.description.trim().length > 0
  );
  const validConstraints = constraints.filter(
    (c) => (c.description && c.description.trim().length > 0) || (c.name && c.name.trim().length > 0)
  );
  const validTradeoffs = tradeoffs.filter(
    (t) => (t.upside && t.upside.trim().length > 0) || (t.downside && t.downside.trim().length > 0)
  );
  const validVariables = variables.filter(
    (v) => (v.name && v.name.trim().length > 0) || (v.description && v.description.trim().length > 0)
  );
  const validAssumptions = assumptions.filter(
    (a) => a.statement && a.statement.trim().length > 0
  );
  const validUnknowns = unknowns.filter(
    (u) => u.question && u.question.trim().length > 0
  );

  const complexityColor =
    complexity.level === "high"
      ? "text-rose-400 bg-rose-950/40 border-rose-800/60"
      : complexity.level === "medium"
      ? "text-amber-400 bg-amber-950/40 border-amber-800/60"
      : "text-emerald-400 bg-emerald-950/40 border-emerald-800/60";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 sm:p-6 space-y-5 text-zinc-100 shadow-sm">
      {/* Top Header & Overview */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
            Pillar 2: Deconstruction Engine
          </span>
          <h3 className="text-lg font-semibold text-white tracking-tight mt-0.5">
            Structured Decision Model
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Decision Type */}
          <span className="rounded-md border border-zinc-700 bg-zinc-800/80 px-2.5 py-1 text-zinc-300 font-medium">
            {formatSnakeCase(decision.decision_type)}
          </span>

          {/* Time Horizon */}
          <span className="rounded-md border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-zinc-400 font-mono">
            {formatSnakeCase(decision.time_horizon)}
          </span>

          {/* Complexity */}
          <span className={`rounded-md border px-2.5 py-1 font-medium ${complexityColor}`}>
            Complexity: {formatSnakeCase(complexity.level)}
            {typeof complexity.score === "number" ? ` (${complexity.score.toFixed(0)})` : ""}
          </span>

          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer border border-zinc-800"
          >
            {isExpanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>

      {/* Decision Summary & Reversibility */}
      <div className="space-y-2">
        <p className="text-sm sm:text-base text-zinc-200 leading-relaxed font-sans font-medium">
          {decision.summary}
        </p>
        <p className="text-xs text-zinc-400 leading-relaxed">
          <span className="text-zinc-300 font-medium">Reversibility:</span> {formatSnakeCase(complexity.reversibility)}. {complexity.reasoning}
        </p>
      </div>

      {isExpanded && (
        <div className="space-y-6 pt-2">
          {/* Primary Objectives & Constraints Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Objectives */}
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center justify-between">
                <span>Core Objectives</span>
                <span className="font-mono text-[11px] text-zinc-500">{validObjectives.length}</span>
              </h4>
              {validObjectives.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No objectives defined.</p>
              ) : (
                <ul className="space-y-2">
                  {validObjectives.map((obj) => (
                    <li key={obj.id} className="text-xs text-zinc-300 flex items-start gap-2">
                      <span
                        className={`inline-block mt-0.5 px-1.5 py-0.2 rounded text-[10px] font-mono shrink-0 ${
                          obj.is_primary
                            ? "bg-indigo-950 text-indigo-300 border border-indigo-800/60"
                            : "bg-zinc-800 text-zinc-400"
                        }`}
                      >
                        {obj.is_primary ? "PRIMARY" : "SECONDARY"}
                      </span>
                      <span className="leading-relaxed">
                        {obj.description}
                        {obj.target_metric && (
                          <span className="text-zinc-400 ml-1">
                            (Target: {obj.target_metric})
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Constraints */}
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center justify-between">
                <span>Active Constraints</span>
                <span className="font-mono text-[11px] text-zinc-500">{validConstraints.length}</span>
              </h4>
              {validConstraints.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No explicit boundary constraints configured.</p>
              ) : (
                <ul className="space-y-2">
                  {validConstraints.map((c) => (
                    <li key={c.id} className="text-xs text-zinc-300 flex items-start gap-2">
                      <span
                        className={`inline-block mt-0.5 px-1.5 py-0.2 rounded text-[10px] font-mono shrink-0 ${
                          c.is_hard_constraint
                            ? "bg-rose-950/50 text-rose-300 border border-rose-800/50"
                            : "bg-zinc-800 text-zinc-400"
                        }`}
                      >
                        {c.is_hard_constraint ? "HARD" : "SOFT"}
                      </span>
                      <span className="leading-relaxed">
                        {c.description || c.name}
                        {c.threshold_expression && (
                          <span className="text-zinc-400 ml-1">[{c.threshold_expression}]</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Trade-offs & Variables */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Trade-offs */}
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center justify-between">
                <span>Inherent Trade-Offs</span>
                <span className="font-mono text-[11px] text-zinc-500">{validTradeoffs.length}</span>
              </h4>
              {validTradeoffs.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No explicit trade-offs documented.</p>
              ) : (
                <ul className="space-y-3">
                  {validTradeoffs.map((t) => (
                    <li key={t.id} className="text-xs space-y-1.5 rounded border border-zinc-800/50 bg-zinc-900/30 p-2.5">
                      {t.upside && (
                        <div className="flex items-start gap-1.5">
                          <span className="rounded bg-emerald-950/60 border border-emerald-800/60 px-1.5 py-0.2 text-[10px] font-mono font-medium text-emerald-300 uppercase shrink-0">
                            Upside
                          </span>
                          <span className="text-zinc-200 leading-snug">{t.upside}</span>
                        </div>
                      )}
                      {t.downside && (
                        <div className="flex items-start gap-1.5">
                          <span className="rounded bg-rose-950/60 border border-rose-800/60 px-1.5 py-0.2 text-[10px] font-mono font-medium text-rose-300 uppercase shrink-0">
                            Downside
                          </span>
                          <span className="text-zinc-300 leading-snug">{t.downside}</span>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Decision Variables */}
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center justify-between">
                <span>Key Variables</span>
                <span className="font-mono text-[11px] text-zinc-500">{validVariables.length}</span>
              </h4>
              {validVariables.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No key variables defined.</p>
              ) : (
                <ul className="space-y-2">
                  {validVariables.slice(0, 5).map((v) => (
                    <li key={v.id} className="text-xs flex items-center justify-between text-zinc-300 py-1 border-b border-zinc-800/40 last:border-none">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-200">{v.name || v.id}</span>
                        <span className="text-[10px] text-zinc-500 font-mono">
                          ({v.is_controllable ? "Controllable" : "Exogenous"})
                        </span>
                      </div>
                      <span className="text-[11px] font-mono text-zinc-400">
                        {v.baseline_value !== null && v.baseline_value !== undefined
                          ? String(v.baseline_value)
                          : formatSnakeCase(v.variable_type)}
                      </span>
                    </li>
                  ))}
                  {validVariables.length > 5 && (
                    <li className="text-[11px] text-zinc-500 text-right pt-1 font-mono">
                      +{validVariables.length - 5} more variables
                    </li>
                  )}
                </ul>
              )}
            </div>
          </div>

          {/* Assumptions & Unknowns (Compact row) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
            {/* Key Assumptions */}
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-2.5">
              <h4 className="font-semibold uppercase tracking-wider text-zinc-400 text-[11px] flex items-center justify-between">
                <span>Assumptions</span>
                <span className="font-mono text-[11px] text-zinc-500">{validAssumptions.length}</span>
              </h4>
              {validAssumptions.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No assumptions specified.</p>
              ) : (
                <ul className="space-y-1.5">
                  {validAssumptions.slice(0, 3).map((a) => (
                    <li key={a.id} className="text-zinc-300 leading-relaxed flex items-start gap-1.5">
                      <span className="text-zinc-600 font-mono select-none">&bull;</span>
                      <span>
                        {a.statement}{" "}
                        <span className="text-zinc-500 text-[10px] font-mono">
                          [{formatSnakeCase(a.confidence)} confidence]
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Unknowns */}
            <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-2.5">
              <h4 className="font-semibold uppercase tracking-wider text-zinc-400 text-[11px] flex items-center justify-between">
                <span>High-Impact Unknowns</span>
                <span className="font-mono text-[11px] text-zinc-500">{validUnknowns.length}</span>
              </h4>
              {validUnknowns.length === 0 ? (
                <p className="text-xs text-zinc-500 italic">No high-impact unknowns identified.</p>
              ) : (
                <ul className="space-y-1.5">
                  {validUnknowns.slice(0, 3).map((u) => (
                    <li key={u.id} className="text-zinc-300 leading-relaxed flex items-start gap-1.5">
                      <span className="text-zinc-600 font-mono select-none">&bull;</span>
                      <span>
                        {u.question}{" "}
                        <span className="text-zinc-500 text-[10px] font-mono">
                          [{formatSnakeCase(u.criticality)} criticality]
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
