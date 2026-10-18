"use client";

import React from "react";
import type { SimulationResult, SimulationVariable } from "@/types";

interface SimulationConstraintImpactsProps {
  result: SimulationResult;
  variables: SimulationVariable[];
}

export function SimulationConstraintImpacts({
  result,
  variables,
}: SimulationConstraintImpactsProps) {
  const varMap = new Map<string, SimulationVariable>();
  for (const v of variables) {
    varMap.set(v.variable_id, v);
  }

  return (
    <div className="space-y-4 print:space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300 print:text-black">
            Constraint Threshold &amp; Artifact Impacts
          </h4>
          <p className="text-[11px] text-zinc-400 print:text-zinc-600 mt-0.5">
            Deterministic evaluations of operational boundaries and affected internal fields.
          </p>
        </div>
        <span className="text-[11px] font-mono text-zinc-500">
          {result.impacts.length} impact record{result.impacts.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Warnings Banner if any */}
      {result.warnings && result.warnings.length > 0 && (
        <div
          role="alert"
          className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-4 text-xs text-amber-200 space-y-2 print:bg-zinc-50 print:border-zinc-300 print:text-black"
        >
          <div className="flex items-center gap-2 font-semibold text-amber-300 print:text-black">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            <span>Simulation Modeling Caveats &amp; Warnings</span>
          </div>
          <ul className="list-disc list-inside space-y-1 text-zinc-300 print:text-zinc-800">
            {result.warnings.map((w, idx) => (
              <li key={idx} className="leading-relaxed">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Impacts List */}
      <div className="space-y-3">
        {result.impacts.map((imp, idx) => {
          const varDef = varMap.get(imp.variable_id);
          const label = varDef?.label || imp.variable_id;
          const unit = varDef?.unit || "";

          return (
            <div
              key={`${imp.variable_id}-${idx}`}
              className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4.5 space-y-3 print:bg-white print:border-zinc-300 print:text-black print:break-inside-avoid"
            >
              {/* Impact Header */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-2.5 border-b border-zinc-800/60 print:border-zinc-200">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-zinc-200 print:text-black">
                    {label}
                  </span>
                  <span className="text-[11px] font-mono text-zinc-500">
                    ({imp.original_value} &rarr; {imp.adjusted_value} {unit})
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono border border-zinc-700 bg-zinc-800/60 text-zinc-300 print:border-zinc-300 print:text-black print:bg-zinc-100">
                    {imp.calculation_status}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">
                    Rule: {imp.transformation_rule_id}
                  </span>
                </div>
              </div>

              {/* Authoritative Explanation from Engine */}
              <div>
                <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-600 block mb-1">
                  Threshold Evaluation
                </span>
                <p className="text-xs text-zinc-300 print:text-zinc-900 leading-relaxed font-sans">
                  {imp.explanation}
                </p>
              </div>

              {/* Affected Structured Fields */}
              {imp.affected_fields && imp.affected_fields.length > 0 && (
                <div className="pt-2 border-t border-zinc-800/50 print:border-zinc-200">
                  <span className="text-[10px] font-mono uppercase text-zinc-500 block mb-1">
                    Affected Structured Attribute Paths:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {imp.affected_fields.map((fieldPath, fIdx) => (
                      <span
                        key={fIdx}
                        className="inline-block px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-zinc-400 print:bg-zinc-100 print:border-zinc-300 print:text-zinc-700 truncate max-w-full"
                      >
                        {fieldPath}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
