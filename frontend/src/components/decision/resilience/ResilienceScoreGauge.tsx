"use client";

import React from "react";
import type { ResilienceRating } from "@/types/resilience";
import {
  formatScore,
  getRatingMetadata,
  getStressTestMetadata,
} from "@/lib/resilienceHelpers";

interface ResilienceScoreGaugeProps {
  score: number;
  rating: ResilienceRating | string;
  stressTestPassed: boolean;
  calculationVersion?: string | null;
  reportId?: string | null;
}

export function ResilienceScoreGauge({
  score,
  rating,
  stressTestPassed,
  calculationVersion,
  reportId,
}: ResilienceScoreGaugeProps) {
  const boundedScore = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
  const ratingMeta = getRatingMetadata(rating || boundedScore);
  const stressMeta = getStressTestMetadata(Boolean(stressTestPassed));

  // Circular gauge geometry
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (boundedScore / 100) * circumference;

  return (
    <div
      aria-label="Resilience Assessment Overview"
      className="rounded-2xl border border-zinc-800/90 bg-zinc-950/70 p-6 sm:p-7 text-zinc-100 shadow-md space-y-6 print:bg-white print:border-zinc-300 print:text-black"
    >
      {/* Header bar: Section title + version + report ID */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-indigo-400 print:text-zinc-700 font-semibold">
            Deterministic Heuristic Evaluation
          </span>
          <h3 className="text-lg font-semibold text-white print:text-black tracking-tight mt-0.5">
            Composite Decision Resilience Score
          </h3>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {calculationVersion && (
            <span className="inline-flex items-center rounded-md border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[11px] font-mono text-zinc-300 print:bg-zinc-100 print:text-black print:border-zinc-300">
              Algorithm v{calculationVersion}
            </span>
          )}
          {reportId && (
            <span
              title={`Report ID: ${reportId}`}
              className="inline-flex items-center rounded-md border border-zinc-800/80 bg-zinc-900/60 px-2 py-0.5 text-[10px] font-mono text-zinc-400 print:hidden"
            >
              {reportId.slice(0, 16)}…
            </span>
          )}
        </div>
      </div>

      {/* Main Grid: Gauge + Rating Details + Stress Test */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        {/* Left Column: Circular Visual Gauge (4 cols) */}
        <div className="lg:col-span-4 flex flex-col items-center justify-center p-3">
          <div
            role="progressbar"
            aria-valuenow={boundedScore}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Overall resilience score: ${formatScore(boundedScore)} out of 100`}
            className="relative flex items-center justify-center"
          >
            <svg
              className="w-36 h-36 transform -rotate-90"
              viewBox="0 0 130 130"
              aria-hidden="true"
            >
              {/* Background track circle */}
              <circle
                cx="65"
                cy="65"
                r={radius}
                className="stroke-zinc-800/90 print:stroke-zinc-200"
                strokeWidth="11"
                fill="transparent"
              />
              {/* Animated/static value circle */}
              <circle
                cx="65"
                cy="65"
                r={radius}
                stroke={ratingMeta.colorClass.gaugeStroke}
                strokeWidth="11"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                fill="transparent"
                className="transition-all duration-700 ease-out"
              />
            </svg>

            {/* Gauge Center Text */}
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
              <span className="text-3xl sm:text-4xl font-extrabold font-mono tracking-tight text-white print:text-black">
                {formatScore(boundedScore)}
              </span>
              <span className="text-[11px] font-mono text-zinc-400 print:text-zinc-600 mt-0.5">
                / 100
              </span>
            </div>
          </div>

          <span className="text-[11px] font-mono text-zinc-400 print:text-zinc-600 mt-3 text-center">
            Scale: 0 (Vulnerable) to 100 (High)
          </span>
        </div>

        {/* Middle/Right Column: Rating info & Stress-test card (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {/* Rating description card */}
          <div
            className={`rounded-xl border p-4 sm:p-5 ${ratingMeta.colorClass.bg} ${ratingMeta.colorClass.border} print:bg-zinc-50 print:border-zinc-300 print:text-black space-y-2`}
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider font-mono ${ratingMeta.colorClass.badgeBg} ${ratingMeta.colorClass.badgeBorder} ${ratingMeta.colorClass.badgeText} print:bg-zinc-200 print:text-black print:border-zinc-400`}
                >
                  {ratingMeta.label}
                </span>
                <span className="text-xs font-mono text-zinc-400 print:text-zinc-600">
                  (Band: {ratingMeta.rangeText})
                </span>
              </div>
            </div>

            <p className="text-xs sm:text-sm text-zinc-200 print:text-black leading-relaxed font-sans">
              {ratingMeta.description}
            </p>
          </div>

          {/* Stress-Test Status Banner */}
          <div
            className={`rounded-xl border p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
              stressMeta.passed
                ? "border-emerald-800/60 bg-emerald-950/20 text-emerald-200 print:bg-zinc-50 print:border-zinc-300 print:text-black"
                : "border-rose-800/60 bg-rose-950/20 text-rose-200 print:bg-zinc-50 print:border-zinc-300 print:text-black"
            }`}
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    stressMeta.passed ? "bg-emerald-400" : "bg-rose-400"
                  }`}
                  aria-hidden="true"
                />
                <span className="font-semibold text-xs sm:text-sm text-white print:text-black">
                  {stressMeta.statusLabel}
                </span>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                    stressMeta.passed
                      ? "border-emerald-700/80 bg-emerald-950/40 text-emerald-300 print:bg-zinc-100 print:text-black"
                      : "border-rose-700/80 bg-rose-950/40 text-rose-300 print:bg-zinc-100 print:text-black"
                  }`}
                >
                  {stressMeta.badgeLabel}
                </span>
              </div>
              <p className="text-[11px] text-zinc-400 print:text-zinc-600 leading-relaxed font-sans">
                {stressMeta.thresholdsExplanation}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Mandatory Deterministic Heuristic Disclaimer */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-3.5 sm:p-4 text-xs text-zinc-300 print:bg-zinc-50 print:border-zinc-300 print:text-black flex items-start gap-3">
        <svg
          className="h-4 w-4 text-indigo-400 print:text-zinc-600 shrink-0 mt-0.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        <div className="space-y-1 leading-relaxed">
          <p className="font-medium text-white print:text-black">
            Deterministic Heuristic Disclaimer:
          </p>
          <p className="text-zinc-300 print:text-zinc-700">
            Resilience is a deterministic heuristic score, not the probability of decision success. It evaluates mathematical and structural robustness across constraints, adverse scenario milestones, rollback coverage, and evidence confidence.
          </p>
        </div>
      </div>
    </div>
  );
}
