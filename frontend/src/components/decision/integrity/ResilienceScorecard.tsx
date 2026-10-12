"use client";

import React from "react";
import type { ResilienceReport } from "@/types";

interface ResilienceScorecardProps {
  report: ResilienceReport;
}

export function ResilienceScorecard({ report }: ResilienceScorecardProps) {
  const getRatingBadge = (rating?: string | null) => {
    switch ((rating || "moderate").toLowerCase()) {
      case "high":
        return {
          bg: "bg-emerald-950/60 border-emerald-800 text-emerald-300",
          color: "text-emerald-400",
          label: "High Resilience",
        };
      case "moderate":
        return {
          bg: "bg-sky-950/60 border-sky-800 text-sky-300",
          color: "text-sky-400",
          label: "Moderate Resilience",
        };
      case "fragile":
        return {
          bg: "bg-amber-950/60 border-amber-800 text-amber-300",
          color: "text-amber-400",
          label: "Fragile",
        };
      case "vulnerable":
      default:
        return {
          bg: "bg-rose-950/60 border-rose-800 text-rose-300",
          color: "text-rose-400",
          label: "Vulnerable Exposure",
        };
    }
  };

  const badge = getRatingBadge(
    report.rating || (report as unknown as { composite_rating?: string }).composite_rating
  );
  const overallScore =
    report.overall_score ??
    (report as unknown as { composite_score?: number }).composite_score ??
    0;
  const subScores = report.sub_scores || [];
  const criticalVulns =
    report.critical_vulnerabilities ||
    (report as unknown as { vulnerabilities?: string[] }).vulnerabilities ||
    [];
  const recommendedHedges = report.recommended_hedges || [];

  return (
    <div
      role="region"
      id="section-resilience-dashboard"
      aria-label="Deterministic Resilience Scorecard"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider font-semibold text-teal-400">
            Deterministic Robustness • Stage 6 Resilience
          </span>
          <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
            Decision Resilience Scorecard
          </h2>
          <span className="text-xs text-zinc-400 font-mono hidden sm:inline-block">
            Decision Resilience &amp; Stress-Test Analysis
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex px-3 py-1 rounded-lg text-xs font-mono border ${badge.bg}`}
          >
            {badge.label}
          </span>
        </div>
      </div>

      {/* Explicit Disclaimer */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3.5 text-xs text-zinc-400 flex items-start gap-2.5">
        <svg
          className="h-4 w-4 text-teal-400 shrink-0 mt-0.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="leading-relaxed">
          <strong className="text-zinc-200">Algorithmic Heuristic Notice:</strong> The composite resilience score is a deterministic structural metric across four evaluation pillars. It does not represent an empirical probability of strategic success.
        </p>
      </div>

      {/* Main Score and Pillars */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Overall Score Dial */}
        <div className="lg:col-span-1 rounded-xl border border-zinc-800 bg-zinc-950/70 p-6 flex flex-col items-center justify-center text-center space-y-2">
          <span className="text-[11px] font-mono text-zinc-400 uppercase tracking-wider">
            Composite Score
          </span>
          <div className="text-5xl font-black font-mono text-white tracking-tight">
            {overallScore.toFixed(1)}
            <span className="text-xl text-zinc-500 font-normal">/100</span>
          </div>
          <span className={`text-xs font-mono font-medium ${badge.color}`}>
            Stress Test: {report.stress_test_passed ? "PASSED" : "FAILED"}
          </span>
        </div>

        {/* Four Pillar Sub-Scores */}
        <div className="lg:col-span-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {subScores.map((sub) => (
            <div
              key={sub.category}
              className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-200 truncate" title={sub.category}>
                  {sub.category}
                </span>
                <span className="text-xs font-mono font-bold text-teal-400 shrink-0">
                  {sub.score.toFixed(1)} / {(sub.max_score ?? 25.0).toFixed(0)}
                </span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-teal-500 h-1.5 rounded-full transition-all duration-500"
                  style={{ width: `${(sub.score / (sub.max_score ?? 25.0)) * 100}%` }}
                />
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed truncate" title={sub.rationale}>
                {sub.rationale}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Vulnerabilities & Recommended Hedges */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        <div className="bg-rose-950/10 rounded-xl p-4 border border-rose-900/30 space-y-2">
          <span className="text-[11px] font-mono uppercase text-rose-400 font-semibold block">
            Critical Structural Vulnerabilities
          </span>
          <ul className="text-xs text-zinc-300 space-y-1.5">
            {criticalVulns.length > 0 ? (
              criticalVulns.map((v, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-rose-500 font-bold">•</span>
                  <span>{v}</span>
                </li>
              ))
            ) : (
              <li className="text-zinc-500 italic">No critical structural vulnerabilities detected.</li>
            )}
          </ul>
        </div>

        <div className="bg-teal-950/10 rounded-xl p-4 border border-teal-900/30 space-y-2">
          <span className="text-[11px] font-mono uppercase text-teal-400 font-semibold block">
            Recommended Operational Hedges
          </span>
          <ul className="text-xs text-zinc-300 space-y-1.5">
            {recommendedHedges.length > 0 ? (
              recommendedHedges.map((h, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-teal-500 font-bold">•</span>
                  <span>{h}</span>
                </li>
              ))
            ) : (
              <li className="text-zinc-500 italic">No additional hedges required beyond standard staging gates.</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
