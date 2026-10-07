"use client";

import React from "react";
import type { EvidencePackage } from "@/types";

interface EvidenceOverviewProps {
  pkg: EvidencePackage;
}

export function EvidenceOverview({ pkg }: EvidenceOverviewProps) {
  const totalRequirements = pkg.requirements.length;
  const fulfilledCount = pkg.requirements.filter((r) => r.status === "fulfilled").length;
  const contestedCount = pkg.requirements.filter((r) => r.status === "contested").length;
  const pendingCount = pkg.requirements.filter((r) => r.status === "pending").length;
  const unsupportedCount = pkg.requirements.filter((r) => r.status === "unsupported").length;
  const inconclusiveCount = pkg.requirements.filter((r) => r.status === "inconclusive").length;

  const totalSources = pkg.sources.length;
  const totalFindings = pkg.items.length;
  const totalGaps = pkg.gaps.length;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 sm:p-6 space-y-5 text-zinc-100 shadow-sm">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-4 border-b border-zinc-800/80">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
            Pillar 3: Empirical Audit
          </span>
          <h3 className="text-lg font-semibold text-white tracking-tight mt-0.5">
            Evidence &amp; Provenance Overview
          </h3>
        </div>
        <span className="text-xs text-zinc-400 font-mono">
          Package ID: <span className="text-zinc-200">{pkg.id}</span>
        </span>
      </div>

      {/* Synthesis Summary */}
      {pkg.summary && (
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/60 p-4">
          <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 block mb-1">
            Empirical Synthesis
          </span>
          <p className="text-sm text-zinc-200 leading-relaxed font-sans">{pkg.summary}</p>
        </div>
      )}

      {/* Truthful Metric Counter Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Total Requirements */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/50 p-3.5 space-y-1">
          <span className="text-[11px] font-medium text-zinc-400 block">
            Evidence Requirements
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-white">{totalRequirements}</span>
            <span className="text-[11px] text-zinc-500 font-mono">total</span>
          </div>
          <div className="pt-1 flex flex-wrap gap-1 text-[10px] font-mono">
            {fulfilledCount > 0 && (
              <span className="text-emerald-400 bg-emerald-950/50 border border-emerald-800/50 px-1.5 py-0.5 rounded">
                {fulfilledCount} fulfilled
              </span>
            )}
            {contestedCount > 0 && (
              <span className="text-rose-400 bg-rose-950/50 border border-rose-800/50 px-1.5 py-0.5 rounded">
                {contestedCount} contested
              </span>
            )}
            {pendingCount > 0 && (
              <span className="text-amber-400 bg-amber-950/50 border border-amber-800/50 px-1.5 py-0.5 rounded">
                {pendingCount} pending
              </span>
            )}
            {unsupportedCount > 0 && (
              <span className="text-zinc-400 bg-zinc-800/50 px-1.5 py-0.5 rounded">
                {unsupportedCount} unsupported
              </span>
            )}
            {inconclusiveCount > 0 && (
              <span className="text-zinc-400 bg-zinc-800/50 px-1.5 py-0.5 rounded">
                {inconclusiveCount} inconclusive
              </span>
            )}
          </div>
        </div>

        {/* Consulted Sources */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/50 p-3.5 space-y-1">
          <span className="text-[11px] font-medium text-zinc-400 block">
            Consulted Sources
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-white">{totalSources}</span>
            <span className="text-[11px] text-zinc-500 font-mono">sources</span>
          </div>
          <p className="text-[10px] text-zinc-500 pt-1 leading-tight">
            Retrieved during research with provenance metadata
          </p>
        </div>

        {/* Evidence Findings (Items) */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/50 p-3.5 space-y-1">
          <span className="text-[11px] font-medium text-zinc-400 block">
            Extracted Findings
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-white">{totalFindings}</span>
            <span className="text-[11px] text-zinc-500 font-mono">findings</span>
          </div>
          <p className="text-[10px] text-zinc-500 pt-1 leading-tight">
            Discrete excerpts &amp; quantitative benchmarks
          </p>
        </div>

        {/* Empirical Gaps */}
        <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/50 p-3.5 space-y-1">
          <span className="text-[11px] font-medium text-zinc-400 block">
            Identified Gaps
          </span>
          <div className="flex items-baseline gap-2">
            <span className={`text-2xl font-bold font-mono ${totalGaps > 0 ? "text-amber-400" : "text-zinc-200"}`}>
              {totalGaps}
            </span>
            <span className="text-[11px] text-zinc-500 font-mono">gaps</span>
          </div>
          <p className="text-[10px] text-zinc-500 pt-1 leading-tight">
            {totalGaps === 0 ? "No open empirical deficiencies" : "Unresolved unknowns & conflicting findings"}
          </p>
        </div>
      </div>
    </div>
  );
}
