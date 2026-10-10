"use client";

import React from "react";
import type {
  UncertaintyAssessment,
  DecisionModel,
  EvidencePackage,
} from "@/types";
import {
  EVIDENCE_STRENGTH_CONFIGS,
  DECISION_READINESS_CONFIGS,
  RECOMMENDATION_STABILITY_CONFIGS,
  resolveAssumption,
  resolveEvidenceGap,
} from "@/lib/recommendationHelpers";

interface UncertaintyReadinessSectionProps {
  uncertainty: UncertaintyAssessment;
  decisionModel?: DecisionModel | null;
  evidencePackage?: EvidencePackage | null;
}

export function UncertaintyReadinessSection({
  uncertainty,
  decisionModel,
  evidencePackage,
}: UncertaintyReadinessSectionProps) {
  const strengthCfg =
    EVIDENCE_STRENGTH_CONFIGS[uncertainty.evidence_strength] ?? {
      value: uncertainty.evidence_strength,
      label: uncertainty.evidence_strength.toUpperCase(),
      badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
      description: "Classified evidence strength.",
    };

  const readinessCfg =
    DECISION_READINESS_CONFIGS[uncertainty.decision_readiness] ?? {
      value: uncertainty.decision_readiness,
      label: uncertainty.decision_readiness.toUpperCase(),
      badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
      description: "Classified decision readiness.",
    };

  const stabilityCfg =
    RECOMMENDATION_STABILITY_CONFIGS[uncertainty.recommendation_stability] ?? {
      value: uncertainty.recommendation_stability,
      label: uncertainty.recommendation_stability.toUpperCase(),
      badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
      description: "Classified recommendation stability.",
    };

  return (
    <section
      id="section-uncertainty-readiness"
      aria-labelledby="uncertainty-readiness-heading"
      className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm print:break-inside-avoid print:bg-white print:text-black print:border-zinc-300"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-5 border-b border-zinc-800/80 print:border-zinc-300">
        <div>
          <span className="text-xs font-mono uppercase tracking-wider text-sky-400 font-semibold print:text-zinc-700">
            Epistemic Reliability &amp; Governance
          </span>
          <h3
            id="uncertainty-readiness-heading"
            className="text-xl font-bold text-white print:text-black tracking-tight mt-0.5"
          >
            Uncertainty &amp; Decision Readiness
          </h3>
          <p className="text-xs sm:text-sm text-zinc-400 print:text-zinc-600 mt-1 max-w-2xl font-sans">
            Explicit categorical evaluation of factual strength, operational readiness, and recommendation sensitivity.
            A recommendation can be actionable while still conditional.
          </p>
        </div>

        <span className="inline-flex items-center text-[11px] font-mono text-zinc-400 print:text-zinc-600 bg-zinc-950/60 px-2.5 py-1 rounded border border-zinc-800 print:border-zinc-300">
          Deterministic Assessment
        </span>
      </div>

      {/* 1. Three Core Categorical Triad Cards (NO fabricated percentages) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Evidence Strength Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold">
              Evidence Strength
            </span>
            <span
              className={`rounded px-2.5 py-0.5 text-xs font-mono font-semibold border ${strengthCfg.badgeClass} print:bg-zinc-100 print:text-black print:border-zinc-400`}
            >
              {strengthCfg.label}
            </span>
          </div>
          <p className="text-xs text-zinc-300 print:text-zinc-800 leading-relaxed font-sans">
            {strengthCfg.description}
          </p>
          <div className="pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-500 font-sans">
            Measures empirical backing across requirements and sources.
          </div>
        </div>

        {/* Decision Readiness Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold">
              Decision Readiness
            </span>
            <span
              className={`rounded px-2.5 py-0.5 text-xs font-mono font-semibold border ${readinessCfg.badgeClass} print:bg-zinc-100 print:text-black print:border-zinc-400`}
            >
              {readinessCfg.label}
            </span>
          </div>
          <p className="text-xs text-zinc-300 print:text-zinc-800 leading-relaxed font-sans">
            {readinessCfg.description}
          </p>
          <div className="pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-500 font-sans">
            Measures operational and stakeholder clearance to execute now.
          </div>
        </div>

        {/* Recommendation Stability Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 print:text-zinc-700 font-semibold">
              Stability Under Change
            </span>
            <span
              className={`rounded px-2.5 py-0.5 text-xs font-mono font-semibold border ${stabilityCfg.badgeClass} print:bg-zinc-100 print:text-black print:border-zinc-400`}
            >
              {stabilityCfg.label}
            </span>
          </div>
          <p className="text-xs text-zinc-300 print:text-zinc-800 leading-relaxed font-sans">
            {stabilityCfg.description}
          </p>
          <div className="pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-500 font-sans">
            Sensitivity to shifts in baseline assumptions or new findings.
          </div>
        </div>
      </div>

      {/* 2. Conditions That Would Change the Recommendation */}
      {uncertainty.conditions_changing_recommendation &&
        uncertainty.conditions_changing_recommendation.length > 0 && (
          <div className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300">
            <div className="flex items-center gap-2">
              <svg
                className="h-4 w-4 text-amber-400 shrink-0"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <h4 className="text-sm font-semibold text-amber-300 print:text-zinc-900 tracking-tight">
                Conditions That Would Change the Recommendation (
                {uncertainty.conditions_changing_recommendation.length})
              </h4>
            </div>
            <p className="text-xs text-zinc-300 print:text-zinc-700">
              If any of the following empirical conditions occur or are verified, this decision must be re-evaluated:
            </p>
            <ul className="space-y-2 pt-1 list-none">
              {uncertainty.conditions_changing_recommendation.map((cond, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 text-xs text-zinc-200 print:text-zinc-900 bg-zinc-950/60 p-3 rounded-lg border border-zinc-800/80 print:bg-white print:border-zinc-300"
                >
                  <span className="font-mono text-amber-400 shrink-0 font-semibold">
                    [{idx + 1}]
                  </span>
                  <span className="leading-relaxed font-sans">{cond}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* 3. Critical Missing Information */}
      {uncertainty.critical_missing_information &&
        uncertainty.critical_missing_information.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-3 print:bg-zinc-50 print:border-zinc-300">
            <div className="flex items-center gap-2">
              <svg
                className="h-4 w-4 text-sky-400 shrink-0"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <h4 className="text-sm font-semibold text-white print:text-zinc-900 tracking-tight">
                Critical Missing Information ({uncertainty.critical_missing_information.length})
              </h4>
            </div>
            <p className="text-xs text-zinc-400 print:text-zinc-700">
              Data gaps that, if resolved with verified evidence, would significantly elevate certainty:
            </p>
            <ul className="space-y-2 pt-1 list-none">
              {uncertainty.critical_missing_information.map((item, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2.5 text-xs text-zinc-300 print:text-zinc-800 bg-zinc-900/50 p-2.5 rounded-lg border border-zinc-800/60 print:bg-white print:border-zinc-300"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-400 mt-1.5 shrink-0" />
                  <span className="leading-relaxed font-sans">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* 4. Assumptions and Evidence Gaps Relied Upon (Resolved Traceability) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        {/* Assumptions Relied Upon */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-3 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-amber-400 font-semibold">
              Assumptions Relied Upon ({uncertainty.assumptions_relied_upon?.length || 0})
            </span>
            <a
              href="#section-decision-model"
              className="text-[11px] font-mono text-zinc-400 hover:text-zinc-200 hover:underline print:hidden"
            >
              View Model &rarr;
            </a>
          </div>
          {uncertainty.assumptions_relied_upon &&
          uncertainty.assumptions_relied_upon.length > 0 ? (
            <div className="space-y-2">
              {uncertainty.assumptions_relied_upon.map((assumpId) => {
                const resolved = resolveAssumption(assumpId, decisionModel);
                return (
                  <div
                    key={assumpId}
                    className="p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/40 text-xs space-y-1 print:bg-white print:border-zinc-300"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-amber-400 font-semibold">
                        {assumpId}
                      </span>
                      {resolved.confidence && (
                        <span className="text-[10px] font-mono text-zinc-400 bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                          Confidence: {resolved.confidence}
                        </span>
                      )}
                    </div>
                    <p className="text-zinc-300 print:text-zinc-800 font-sans leading-relaxed">
                      {resolved.statement}
                    </p>
                    {resolved.falsificationCondition && (
                      <p className="text-[11px] text-zinc-500 font-sans italic">
                        Falsifiable if: {resolved.falsificationCondition}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">
              No specific model assumptions declared as critical dependencies.
            </p>
          )}
        </div>

        {/* Evidence Gaps Relied Upon */}
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/40 p-4 space-y-3 print:bg-zinc-50 print:border-zinc-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-rose-400 font-semibold">
              Evidence Gaps Relied Upon ({uncertainty.evidence_gaps_relied_upon?.length || 0})
            </span>
            <a
              href="#section-evidence-gaps"
              className="text-[11px] font-mono text-zinc-400 hover:text-zinc-200 hover:underline print:hidden"
            >
              View Gaps &rarr;
            </a>
          </div>
          {uncertainty.evidence_gaps_relied_upon &&
          uncertainty.evidence_gaps_relied_upon.length > 0 ? (
            <div className="space-y-2">
              {uncertainty.evidence_gaps_relied_upon.map((gapId) => {
                const resolved = resolveEvidenceGap(gapId, evidencePackage);
                return (
                  <div
                    key={gapId}
                    className="p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/40 text-xs space-y-1 print:bg-white print:border-zinc-300"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-rose-400 font-semibold">
                        {gapId}
                      </span>
                      {resolved.found ? (
                        <span className="text-[10px] font-mono text-rose-300 bg-rose-950/40 px-1.5 py-0.5 rounded border border-rose-800/40">
                          Active Gap
                        </span>
                      ) : null}
                    </div>
                    <p className="text-zinc-300 print:text-zinc-800 font-sans leading-relaxed">
                      {resolved.description}
                    </p>
                    {resolved.resolutionGuidance && (
                      <p className="text-[11px] text-zinc-500 font-sans">
                        Guidance: {resolved.resolutionGuidance}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">
              No outstanding evidence gaps identified as critical blockers.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
