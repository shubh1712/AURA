"use client";

import React, { useState } from "react";
import type { IntegrityFinding, IntegritySeverity } from "@/types";

interface IntegrityFindingsCardProps {
  findings: IntegrityFinding[];
}

export function IntegrityFindingsCard({ findings }: IntegrityFindingsCardProps) {
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");

  const filteredFindings =
    filterSeverity === "ALL"
      ? findings
      : findings.filter((f) => f.severity.toUpperCase() === filterSeverity);

  const getSeverityBadge = (sev: IntegritySeverity) => {
    switch (sev) {
      case "critical":
        return "bg-rose-950/80 border-rose-800 text-rose-300";
      case "high":
        return "bg-amber-950/80 border-amber-800 text-amber-300";
      case "medium":
        return "bg-yellow-950/80 border-yellow-800 text-yellow-300";
      case "low":
      default:
        return "bg-zinc-800 border-zinc-700 text-zinc-300";
    }
  };

  const getStatusBadge = (status: IntegrityFinding["status"]) => {
    switch (status) {
      case "confirmed":
        return "bg-rose-950/40 text-rose-300 border-rose-900/60";
      case "requires_review":
        return "bg-amber-950/40 text-amber-300 border-amber-900/60";
      case "unresolved":
      default:
        return "bg-zinc-800 text-zinc-400 border-zinc-700";
    }
  };

  return (
    <div
      role="region"
      aria-label="Cross-Stage Decision Integrity Findings"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider font-semibold text-rose-400">
            Automated Cross-Stage Verification
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Decision Integrity Findings
          </h2>
        </div>

        {/* Severity Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 bg-zinc-950/80 p-1 rounded-xl border border-zinc-800 text-xs font-mono">
          {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((sev) => {
            const count =
              sev === "ALL"
                ? findings.length
                : findings.filter((f) => f.severity.toUpperCase() === sev).length;

            return (
              <button
                key={sev}
                onClick={() => setFilterSeverity(sev)}
                className={`cursor-pointer px-2.5 py-1 rounded-lg transition-colors ${
                  filterSeverity === sev
                    ? "bg-zinc-800 text-white font-bold"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {sev} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {filteredFindings.length === 0 ? (
        <div className="rounded-xl border border-emerald-900/40 bg-emerald-950/20 p-6 text-center text-xs text-emerald-300">
          No integrity findings detected for the selected filter.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredFindings.map((finding) => (
            <div
              key={finding.finding_id}
              className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-5 space-y-3 transition-all hover:border-zinc-700"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border uppercase font-semibold ${getSeverityBadge(
                      finding.severity
                    )}`}
                  >
                    {finding.severity}
                  </span>
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-[10px] font-mono border ${getStatusBadge(
                      finding.status
                    )}`}
                  >
                    {finding.status.replace("_", " ")}
                  </span>
                  <span className="text-[11px] font-mono text-zinc-500">
                    Rule: <code className="text-zinc-300">{finding.rule_code}</code>
                  </span>
                </div>

                <div className="text-[11px] font-mono text-zinc-400">
                  Affected Stages:{" "}
                  <span className="text-white font-semibold">
                    {finding.affected_stages.map((s) => `Stage ${s}`).join(", ")}
                  </span>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold text-white">
                  {finding.title}
                </h3>
                <p className="text-xs text-zinc-300 leading-relaxed mt-1">
                  {finding.description}
                </p>
              </div>

              {/* Suggested Resolution Box */}
              <div className="rounded-lg bg-zinc-900/90 border border-zinc-800/80 p-3 text-xs space-y-1">
                <span className="text-[11px] font-mono text-amber-400 font-semibold block">
                  Suggested Actionable Resolution:
                </span>
                <p className="text-zinc-300 text-xs leading-relaxed">
                  {finding.suggested_resolution}
                </p>
              </div>

              <div className="text-[10px] font-mono text-zinc-500 flex items-center justify-between pt-1">
                <span>Provenance: {finding.provenance}</span>
                <span>ID: {finding.finding_id}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
