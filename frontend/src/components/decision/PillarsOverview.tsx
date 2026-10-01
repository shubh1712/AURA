import React from "react";

const PILLARS = [
  { id: 1, title: "Decision Understanding", phase: "Ingestion" },
  { id: 2, title: "Decision Decomposition", phase: "Extraction" },
  { id: 3, title: "Evidence & Provenance", phase: "Audit" },
  { id: 4, title: "Multi-Perspective Reasoning", phase: "Evaluation" },
  { id: 5, title: "Second-Order Effects", phase: "Simulation" },
  { id: 6, title: "Scenario Generation", phase: "Simulation" },
  { id: 7, title: "Deterministic Resilience", phase: "Analysis" },
  { id: 8, title: "Conditional Recommendations", phase: "Synthesis" },
  { id: 9, title: "What-If Simulations", phase: "Interactive" },
  { id: 10, title: "Explainable Decision Briefs", phase: "Reporting" },
];

export function PillarsOverview() {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          Planned Analysis Pipeline (10 Pillars)
        </h4>
        <span className="text-[11px] text-zinc-500 font-mono">
          Phase 1+ Integration Target
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {PILLARS.map((pillar) => (
          <div
            key={pillar.id}
            className="flex items-center justify-between rounded-lg border border-zinc-800/80 bg-zinc-900/40 px-3 py-2 text-xs"
          >
            <div className="flex items-center space-x-2">
              <span className="flex h-5 w-5 items-center justify-center rounded bg-zinc-800 text-[10px] font-mono text-zinc-300">
                {pillar.id}
              </span>
              <span className="text-zinc-200 font-medium">{pillar.title}</span>
            </div>
            <span className="rounded bg-zinc-800/50 px-1.5 py-0.5 text-[10px] text-zinc-400">
              {pillar.phase}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
