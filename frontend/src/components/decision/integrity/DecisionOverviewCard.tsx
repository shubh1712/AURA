"use client";

import React, { useState } from "react";
import type { DecisionReadinessStatus, IntegrityStatus } from "@/types";

interface DecisionOverviewCardProps {
  decisionTitle: string;
  recommendedDirection?: string | null;
  shortRationale?: string | null;
  decisionReadiness?: DecisionReadinessStatus;
  integrityStatus?: IntegrityStatus;
  criticalWarningCount?: number;
  topFalsificationCondition?: string | null;
  keyMetrics?: Record<string, string>;
  analysisStatus: string;
  analysisId: string;
  sourceFingerprint?: string;
  onReset?: () => void;
}

export function DecisionOverviewCard({
  decisionTitle,
  recommendedDirection,
  shortRationale,
  decisionReadiness = "needs_validation",
  integrityStatus = "checking",
  criticalWarningCount = 0,
  topFalsificationCondition,
  keyMetrics = {},
  analysisStatus,
  analysisId,
  sourceFingerprint,
}: DecisionOverviewCardProps) {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  const getReadinessBadge = (readiness: DecisionReadinessStatus) => {
    switch (readiness) {
      case "ready":
        return {
          bg: "bg-emerald-950/70 border-emerald-700/80 text-emerald-300",
          dot: "bg-emerald-400",
          label: "Ready to Execute",
        };
      case "conditional":
        return {
          bg: "bg-sky-950/70 border-sky-700/80 text-sky-300",
          dot: "bg-sky-400",
          label: "Conditional Approval",
        };
      case "needs_validation":
        return {
          bg: "bg-amber-950/70 border-amber-700/80 text-amber-300",
          dot: "bg-amber-400",
          label: "Needs Preliminary Validation",
        };
      case "blocked":
      default:
        return {
          bg: "bg-rose-950/70 border-rose-700/80 text-rose-300",
          dot: "bg-rose-400",
          label: "Execution Blocked",
        };
    }
  };

  const getIntegrityBadge = (status: IntegrityStatus) => {
    switch (status) {
      case "checking":
        return {
          bg: "bg-zinc-900 border-zinc-700 text-zinc-300 animate-pulse",
          dot: "bg-zinc-400 animate-ping",
          label: "Checking Mathematical Integrity...",
        };
      case "passed":
        return {
          bg: "bg-emerald-950/60 border-emerald-700/80 text-emerald-300",
          dot: "bg-emerald-400",
          label: "Mathematical Integrity Verified",
        };
      case "warning":
      case "warnings_present":
        return {
          bg: "bg-amber-950/60 border-amber-700/80 text-amber-300",
          dot: "bg-amber-400",
          label: criticalWarningCount > 0
            ? `Findings Require Attention (${criticalWarningCount} Cross-Stage Warning${criticalWarningCount === 1 ? "" : "s"})`
            : "Findings Require Attention",
        };
      case "critical_concerns":
      case "integrity_compromised":
        return {
          bg: "bg-rose-950/60 border-rose-700/80 text-rose-300",
          dot: "bg-rose-400",
          label: "Critical Contradictions Detected",
        };
      case "insufficient_data":
      case "unresolved":
        return {
          bg: "bg-indigo-950/60 border-indigo-700/80 text-indigo-300",
          dot: "bg-indigo-400",
          label: "Unresolved (Missing Quantitative Inputs)",
        };
      case "unavailable":
      default:
        return {
          bg: "bg-zinc-800/80 border-zinc-700 text-zinc-400",
          dot: "bg-zinc-500",
          label: "Integrity Check Unavailable",
        };
    }
  };

  const readinessStyle = getReadinessBadge(decisionReadiness);
  const integrityStyle = getIntegrityBadge(integrityStatus);

  return (
    <div
      role="region"
      aria-label="Executive Decision Overview"
      className="rounded-2xl border border-zinc-800 bg-gradient-to-b from-zinc-900/90 to-zinc-950/90 p-5 sm:p-7 lg:p-8 shadow-xl text-zinc-100 backdrop-blur-md relative overflow-hidden space-y-6"
    >
      {/* Subtle glow accent based on readiness */}
      <div
        className={`absolute -top-24 -right-24 h-56 w-56 rounded-full blur-3xl opacity-20 pointer-events-none ${
          decisionReadiness === "ready"
            ? "bg-emerald-500"
            : decisionReadiness === "conditional"
            ? "bg-sky-500"
            : decisionReadiness === "needs_validation"
            ? "bg-amber-500"
            : "bg-rose-500"
        }`}
      />

      {/* 1. Decision Overview Eyebrow & Pipeline Status */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-mono text-zinc-400 border-b border-zinc-800/80 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-widest text-emerald-400/90 font-semibold">
            Executive Decision Intelligence
          </span>
          <span className="text-zinc-600 hidden sm:inline">•</span>
          <span className="text-zinc-400">
            Pipeline:{" "}
            <span className="text-zinc-200 font-medium">
              {analysisStatus === "completed"
                ? "Analysis Complete (completed)"
                : analysisStatus === "partial_success"
                ? "Partial Analysis Complete (partial_success)"
                : analysisStatus}
            </span>
          </span>
        </div>

        {/* Technical Details Toggle */}
        <button
          type="button"
          onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
          className="text-[11px] font-mono text-zinc-400 hover:text-zinc-200 underline underline-offset-4 decoration-zinc-700 cursor-pointer"
        >
          {showTechnicalDetails ? "Hide Technical Details" : "Technical Details"}
        </button>
      </div>

      {/* Optional Technical Details Disclosure */}
      {showTechnicalDetails && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-3.5 text-xs font-mono text-zinc-400 space-y-1.5 animate-fadeIn">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-zinc-500">Analysis ID:</span>
            <span className="text-zinc-200 select-all">{analysisId}</span>
          </div>
          {sourceFingerprint && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-zinc-500">Deterministic Fingerprint:</span>
              <span className="text-zinc-300 font-mono select-all truncate max-w-md">{sourceFingerprint}</span>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
            <span>Deterministic engine: 6-stage pipeline • Zero hallucinated scores</span>
          </div>
        </div>
      )}

      {/* 2. Responsive Status Badges Row */}
      <div className="flex flex-wrap items-center gap-3">
        <div
          className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-1.5 text-xs font-medium font-mono shadow-sm ${readinessStyle.bg}`}
        >
          <span className={`h-2 w-2 rounded-full ${readinessStyle.dot}`} />
          <span>{readinessStyle.label}</span>
        </div>

        <div
          className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-1.5 text-xs font-mono shadow-sm ${integrityStyle.bg}`}
        >
          <span className={`h-2 w-2 rounded-full ${integrityStyle.dot}`} />
          <span>{integrityStyle.label}</span>
        </div>
      </div>

      {/* 3. Clear Decision Title */}
      <div>
        <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold tracking-tight text-white leading-snug">
          {decisionTitle}
        </h1>
      </div>

      {/* 4. Strategic Recommendation Card (Spanning full available width) */}
      {recommendedDirection && (
        <div className="rounded-xl border border-emerald-900/60 bg-emerald-950/20 p-5 sm:p-6 space-y-2 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-semibold">
              Executive Recommendation
            </span>
          </div>
          <p className="text-base sm:text-lg font-medium text-zinc-100 leading-relaxed">
            {recommendedDirection}
          </p>
        </div>
      )}

      {/* 5. Executive Rationale & Falsification Condition */}
      <div className="space-y-4">
        {shortRationale && (
          <div className="space-y-1.5">
            <h2 className="text-xs font-mono uppercase tracking-wider text-zinc-400 font-medium">
              Executive Rationale
            </h2>
            <p className="text-sm text-zinc-300 leading-relaxed max-w-4xl">
              {shortRationale}
            </p>
          </div>
        )}

        {topFalsificationCondition && (
          <div className="rounded-xl border border-amber-900/50 bg-amber-950/20 p-4 text-xs sm:text-sm text-amber-200/90 flex items-start gap-3 shadow-sm">
            <svg
              className="h-4 w-4 text-amber-400 shrink-0 mt-0.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="space-y-1">
              <span className="font-semibold text-amber-300 block font-mono text-xs uppercase tracking-wider">
                Critical Falsification Condition:
              </span>
              <p className="leading-relaxed">{topFalsificationCondition}</p>
            </div>
          </div>
        )}
      </div>

      {/* 6. Supported Key Metrics in Responsive Cards (Full labels visible by default) */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/60 p-5 space-y-3.5">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-mono uppercase tracking-wider text-zinc-400 font-semibold">
            Supported Key Metrics
          </h2>
          <span className="text-[11px] font-mono text-zinc-500">
            {Object.keys(keyMetrics).length} Verified Metrics
          </span>
        </div>

        {Object.keys(keyMetrics).length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            {Object.entries(keyMetrics).map(([label, val]) => (
              <div
                key={label}
                className="bg-zinc-900/70 hover:bg-zinc-900 rounded-xl p-3.5 border border-zinc-800/80 flex flex-col justify-between transition-colors shadow-sm"
              >
                <div className="text-xs text-zinc-400 font-mono leading-snug break-words">
                  {label}
                </div>
                <div className="text-base sm:text-lg font-bold text-white mt-2 break-words">
                  {val}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-zinc-500 italic py-2">
            No empirical quantitative metrics verified for this decision.
          </div>
        )}
      </div>
    </div>
  );
}
