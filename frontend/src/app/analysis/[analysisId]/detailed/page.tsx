"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import type { SharedReportModel } from "@/types";
import { getSharedReport, getDetailedPdfUrl } from "@/lib/api";
import {
  DecisionOverviewCard,
  OptionComparisonMatrix,
  FinancialFeasibilityCard,
  IntegrityFindingsCard,
  EvidenceQualityCard,
} from "@/components/decision/integrity";

interface DetailedPageProps {
  params: Promise<{ analysisId: string }>;
}

export default function AnalysisDetailedReportPage({ params }: DetailedPageProps) {
  const { analysisId } = use(params);
  const [report, setReport] = useState<SharedReportModel | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadReport() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await getSharedReport(analysisId);
        if (isMounted) {
          setReport(data);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(
            err instanceof Error ? err.message : "Failed to load detailed report."
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadReport();
    return () => {
      isMounted = false;
    };
  }, [analysisId]);

  const pdfUrl = getDetailedPdfUrl(analysisId);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
        <div className="text-center space-y-4">
          <div className="h-8 w-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-mono text-zinc-400">Loading Comprehensive Audit Report...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-2xl border border-rose-900/60 bg-rose-950/20 p-8 text-center space-y-4">
          <div className="h-10 w-10 text-rose-400 mx-auto">⚠️</div>
          <h2 className="text-lg font-bold text-white">Detailed Report Unavailable</h2>
          <p className="text-xs text-rose-300/80">{error || "Analysis not found."}</p>
          <Link
            href="/"
            className="inline-flex items-center justify-center px-4 py-2 rounded-xl border border-zinc-700 bg-zinc-800 text-xs font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors"
          >
            &larr; Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const { overview, integrity_report, perspectives, roadmap, full_framing } = report;
  const optionComparison = integrity_report?.option_comparison || report.option_comparison;
  const calculations = integrity_report?.calculations || report.calculations;
  const findings = integrity_report?.findings || report.integrity_findings;
  const evidenceQuality = integrity_report?.evidence_quality || report.evidence_quality;

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 py-8 px-4 sm:px-6 lg:px-8 print:bg-white print:text-black">
      <div className="w-full max-w-[1536px] mx-auto space-y-8">
        {/* Navigation & Action Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-zinc-800 print:hidden">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-xs font-mono text-zinc-400 hover:text-white transition-colors cursor-pointer"
            >
              <span>&larr;</span>
              <span>Back to Dashboard</span>
            </Link>
            <span className="text-zinc-700">•</span>
            <span className="text-xs font-mono text-purple-400 font-semibold uppercase tracking-wider">
              Comprehensive Audit Report
            </span>
          </div>

          <div className="flex items-center gap-3">
            <a
              href={pdfUrl}
              download={`AURA_Detailed_${analysisId}.pdf`}
              className="inline-flex items-center gap-2 rounded-xl border border-purple-700/80 bg-purple-950/60 hover:bg-purple-900/80 px-4 py-2 text-xs font-mono text-purple-200 hover:text-white transition-all cursor-pointer shadow-sm"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Download Detailed PDF</span>
            </a>
          </div>
        </div>

        {/* Table of Contents Header */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 text-xs text-zinc-400 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono">
          <span className="text-zinc-500 uppercase font-bold">Audit Sections:</span>
          <a href="#overview" className="hover:text-white hover:underline">1. Overview</a>
          <a href="#boardroom" className="hover:text-white hover:underline">2. Boardroom Deliberation</a>
          <a href="#options" className="hover:text-white hover:underline">3. Option Comparison</a>
          <a href="#financial" className="hover:text-white hover:underline">4. Financial Feasibility</a>
          <a href="#integrity" className="hover:text-white hover:underline">5. Integrity Findings</a>
          <a href="#evidence" className="hover:text-white hover:underline">6. Evidence Quality</a>
          <a href="#roadmap" className="hover:text-white hover:underline">7. Implementation Roadmap</a>
          <a href="#framing" className="hover:text-white hover:underline">8. Decision Framing</a>
        </div>

        {/* 1. Persistent Decision Overview */}
        <section id="overview">
          <DecisionOverviewCard
            decisionTitle={overview.decision_title}
            recommendedDirection={overview.recommended_direction}
            shortRationale={overview.short_rationale}
            decisionReadiness={overview.decision_readiness}
            integrityStatus={overview.integrity_status}
            criticalWarningCount={overview.critical_warning_count}
            topFalsificationCondition={overview.top_falsification_condition}
            keyMetrics={overview.key_metrics}
            analysisStatus="Completed Audit"
            analysisId={analysisId}
            sourceFingerprint={report.source_fingerprint}
          />
        </section>

        {/* 2. AI Boardroom Multi-Perspective Deliberation */}
        {perspectives && perspectives.length > 0 && (
          <section id="boardroom" className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm">
            <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
              <div>
                <span className="text-xs font-mono uppercase tracking-wider font-semibold text-sky-400">
                  Stage 3 Deliberation
                </span>
                <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
                  AI Boardroom Perspectives
                </h2>
              </div>
              <span className="text-xs font-mono text-zinc-400 bg-zinc-800 px-2.5 py-1 rounded">
                {perspectives.length} Perspectives
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {perspectives.map((p) => (
                <div
                  key={p.perspective_type}
                  className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-white capitalize">{p.title}</h3>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                      {p.stance}
                    </span>
                  </div>

                  <p className="text-xs text-zinc-300 leading-relaxed">
                    {p.key_argument}
                  </p>

                  {p.critical_concerns.length > 0 && (
                    <div className="pt-2 border-t border-zinc-800/80">
                      <span className="text-[10px] font-mono text-rose-400 font-semibold block mb-1">
                        Critical Concerns Flagged:
                      </span>
                      <ul className="text-[11px] text-zinc-400 space-y-1">
                        {p.critical_concerns.map((c, i) => (
                          <li key={i} className="flex items-start gap-1.5">
                            <span className="text-rose-500 font-bold">•</span>
                            <span>{c}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 3. Option Comparison */}
        {optionComparison && (
          <section id="options">
            <OptionComparisonMatrix report={optionComparison} />
          </section>
        )}

        {/* 4. Deterministic Financial Feasibility */}
        {calculations && calculations.length > 0 && (
          <section id="financial">
            <FinancialFeasibilityCard calculations={calculations} />
          </section>
        )}

        {/* 5. Key Integrity Findings */}
        {findings && findings.length > 0 && (
          <section id="integrity">
            <IntegrityFindingsCard findings={findings} />
          </section>
        )}

        {/* 6. Evidence Quality */}
        {evidenceQuality && (
          <section id="evidence">
            <EvidenceQualityCard report={evidenceQuality} />
          </section>
        )}

        {/* 7. Action Roadmap */}
        {roadmap && roadmap.length > 0 && (
          <section id="roadmap" className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm">
            <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
              <div>
                <span className="text-xs font-mono uppercase tracking-wider font-semibold text-emerald-400">
                  Implementation Roadmap
                </span>
                <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
                  Detailed Implementation &amp; Decision Gates
                </h2>
              </div>
              <span className="text-xs font-mono text-zinc-400 bg-zinc-800 px-2.5 py-1 rounded">
                {roadmap.length} Actions
              </span>
            </div>

            <div className="space-y-4">
              {roadmap.map((act) => (
                <div
                  key={act.step}
                  className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-3"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="h-6 w-6 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-300 font-mono text-xs flex items-center justify-center font-bold">
                        {act.step}
                      </span>
                      <h3 className="text-sm font-bold text-white">{act.title}</h3>
                    </div>
                    <div className="flex items-center gap-2 text-xs font-mono">
                      <span className="text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                        {act.time_horizon}
                      </span>
                      <span className="text-zinc-300">{act.responsible_role}</span>
                    </div>
                  </div>

                  {act.decision_gate && (
                    <div className="rounded-lg bg-amber-950/20 border border-amber-900/40 p-3 text-xs text-amber-200 space-y-1">
                      <span className="font-semibold text-amber-400 block font-mono text-[11px]">
                        Go/No-Go Decision Gate:
                      </span>
                      <p>{act.decision_gate}</p>
                    </div>
                  )}

                  {act.fallback_plan && (
                    <div className="rounded-lg bg-zinc-900/60 border border-zinc-800 p-3 text-xs text-zinc-300 space-y-1">
                      <span className="font-semibold text-zinc-400 block font-mono text-[11px]">
                        Staged Fallback Plan:
                      </span>
                      <p>{act.fallback_plan}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 8. Raw Decision Framing Artifacts */}
        {full_framing && Object.keys(full_framing).length > 0 && (
          <section id="framing" className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-4 text-zinc-100 shadow-sm">
            <div className="pb-4 border-b border-zinc-800">
              <span className="text-xs font-mono uppercase tracking-wider font-semibold text-zinc-400">
                Stage 1 Artifact
              </span>
              <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
                Structured Decision Framing Parameters
              </h2>
            </div>

            <pre className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 text-[11px] font-mono text-zinc-300 overflow-x-auto max-h-96">
              {JSON.stringify(full_framing, null, 2)}
            </pre>
          </section>
        )}
      </div>
    </main>
  );
}
