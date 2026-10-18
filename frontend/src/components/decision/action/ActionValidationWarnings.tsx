"use client";

import React from "react";
import type { ValidationWarning, ValidationSeverity } from "@/types";

interface ActionValidationWarningsProps {
  warnings: ValidationWarning[];
}

function getSeverityConfig(severity: ValidationSeverity) {
  switch (severity) {
    case "conflict":
      return {
        title: "Hard Constraint Conflict",
        badge: "CONFLICT",
        borderClass: "border-rose-800/80 bg-rose-950/25 text-rose-200",
        badgeClass: "border-rose-700 bg-rose-900/60 text-rose-200",
        iconColor: "text-rose-400",
        description:
          "An action or gate criterion evaluates a threshold that contradicts or weakens a non-negotiable user hard constraint.",
      };
    case "review_required":
      return {
        title: "Manual Review Required",
        badge: "REVIEW REQUIRED",
        borderClass: "border-amber-800/80 bg-amber-950/25 text-amber-200",
        badgeClass: "border-amber-700 bg-amber-900/60 text-amber-200",
        iconColor: "text-amber-400",
        description:
          "Incompatible units or qualitative metrics prevent deterministic evaluation. Human verification required.",
      };
    case "warning":
      return {
        title: "Validation Warning",
        badge: "WARNING",
        borderClass: "border-zinc-700 bg-zinc-900/40 text-zinc-300",
        badgeClass: "border-zinc-600 bg-zinc-800 text-zinc-300",
        iconColor: "text-yellow-400",
        description: "Potential execution or dependency discrepancy detected.",
      };
    case "info":
    default:
      return {
        title: "Informational Notice",
        badge: "NOTICE",
        borderClass: "border-zinc-800 bg-zinc-900/30 text-zinc-400",
        badgeClass: "border-zinc-700 bg-zinc-800 text-zinc-400",
        iconColor: "text-zinc-400",
        description: "Operational guidance note.",
      };
  }
}

export function ActionValidationWarnings({
  warnings,
}: ActionValidationWarningsProps) {
  if (!warnings || warnings.length === 0) {
    return null;
  }

  // Sort conflicts first, followed by review_required, then warnings, then info
  const severityRank: Record<string, number> = {
    conflict: 1,
    review_required: 2,
    warning: 3,
    info: 4,
  };

  const sortedWarnings = [...warnings].sort(
    (a, b) =>
      (severityRank[a.severity] || 99) - (severityRank[b.severity] || 99)
  );

  return (
    <div id="action-validation-warnings-section" className="space-y-3">
      <div className="flex items-center gap-2">
        <h4 className="text-sm font-semibold text-white print:text-black tracking-tight">
          Validation &amp; Governance Safeguards
        </h4>
        <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-mono text-zinc-300">
          {warnings.length} {warnings.length === 1 ? "Notice" : "Notices"}
        </span>
      </div>

      <div className="space-y-2.5">
        {sortedWarnings.map((warn) => {
          const cfg = getSeverityConfig(warn.severity);

          return (
            <div
              key={warn.warning_id}
              id={`validation-warning-${warn.warning_id}`}
              role={warn.severity === "conflict" ? "alert" : "status"}
              className={`rounded-xl border p-4 text-xs space-y-2 shadow-sm print:border-zinc-300 print:bg-white print:text-black ${cfg.borderClass}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider print:border-zinc-300 print:bg-zinc-100 print:text-black ${cfg.badgeClass}`}
                  >
                    {cfg.badge}
                  </span>
                  <span className="font-semibold text-white print:text-black">
                    {cfg.title}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-zinc-400 print:text-zinc-600">
                  ID: {warn.warning_id}
                </span>
              </div>

              <p className="leading-relaxed text-zinc-200 print:text-black">
                {warn.message}
              </p>

              {/* Related Entity Badges */}
              {(warn.related_action_ids?.length > 0 ||
                warn.related_gate_ids?.length > 0 ||
                warn.related_criterion_ids?.length > 0) && (
                <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-zinc-800/60 text-[11px] font-mono text-zinc-400 print:text-zinc-600 print:border-zinc-200">
                  <span className="text-zinc-500">Related:</span>
                  {warn.related_action_ids?.map((aid) => (
                    <span
                      key={aid}
                      className="rounded bg-zinc-800/60 px-1.5 py-0.5 border border-zinc-700/60 text-zinc-300"
                    >
                      Action: {aid}
                    </span>
                  ))}
                  {warn.related_gate_ids?.map((gid) => (
                    <span
                      key={gid}
                      className="rounded bg-zinc-800/60 px-1.5 py-0.5 border border-zinc-700/60 text-zinc-300"
                    >
                      Gate: {gid}
                    </span>
                  ))}
                  {warn.related_criterion_ids?.map((cid) => (
                    <span
                      key={cid}
                      className="rounded bg-zinc-800/60 px-1.5 py-0.5 border border-zinc-700/60 text-zinc-300"
                    >
                      Crit: {cid}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
