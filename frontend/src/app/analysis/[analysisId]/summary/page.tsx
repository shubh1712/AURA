"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import type { SharedReportModel } from "@/types";
import { getSharedReport, getSummaryPdfUrl } from "@/lib/api";
import {
  DecisionOverviewCard,
  OptionComparisonMatrix,
  FinancialFeasibilityCard,
  IntegrityFindingsCard,
  EvidenceQualityCard,
} from "@/components/decision/integrity";

interface SummaryPageProps {
  params: Promise<{ analysisId: string }>;
}

export default function AnalysisSummaryReportPage({ params }: SummaryPageProps) {
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
            err instanceof Error ? err.message : "Failed to load summary report."
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

  const pdfUrl = getSummaryPdfUrl(analysisId);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
        <div className="text-center space-y-4">
          <div className="h-8 w-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-mono text-zinc-400">Loading Executive Summary Report...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-2xl border border-rose-900/60 bg-rose-950/20 p-8 text-center space-y-4">
          <div className="h-10 w-10 text-rose-400 mx-auto">⚠️</div>
          <h2 className="text-lg font-bold text-white">Summary Report Unavailable</h2>
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

  const { overview, integrity_report, roadmap } = report;
  const optionComparison = integrity_report?.option_comparison || report.option_comparison;
  const calculations = integrity_report?.calculations || report.calculations;
  const findings = integrity_report?.findings || report.integrity_findings;
  const evidenceQuality = integrity_report?.evidence_quality || report.evidence_quality;

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 py-8 px-4 sm:px-6 lg:px-8 print:bg-white print:text-black">
      <div className="w-full max-w-[1440px] mx-auto space-y-8">
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
            <span className="text-xs font-mono text-emerald-400 font-semibold uppercase tracking-wider">
              Executive Summary Report
            </span>
          </div>

          <div className="flex items-center gap-3">
            <a
              href={pdfUrl}
              download={`AURA_Summary_${analysisId}.pdf`}
              className="inline-flex items-center gap-2 rounded-xl border border-emerald-700/80 bg-emerald-950/60 hover:bg-emerald-900/80 px-4 py-2 text-xs font-mono text-emerald-200 hover:text-white transition-all cursor-pointer shadow-sm"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Download Summary PDF</span>
            </a>
          </div>
        </div>

        {/* 1. Persistent Decision Overview */}
        <DecisionOverviewCard
          decisionTitle={overview.decision_title}
          recommendedDirection={overview.recommended_direction}
          shortRationale={overview.short_rationale}
          decisionReadiness={overview.decision_readiness}
          integrityStatus={overview.integrity_status}
          criticalWarningCount={overview.critical_warning_count}
          topFalsificationCondition={overview.top_falsification_condition}
          keyMetrics={overview.key_metrics}
          analysisStatus="Completed"
          analysisId={analysisId}
          sourceFingerprint={report.source_fingerprint}
        />

        {/* 2. Options Comparison */}
        {optionComparison && (
          <OptionComparisonMatrix report={optionComparison} />
        )}

        {/* 3. Deterministic Financial Feasibility */}
        {calculations && calculations.length > 0 && (
          <FinancialFeasibilityCard calculations={calculations} />
        )}

        {/* 4. Action Roadmap */}
        {roadmap && roadmap.length > 0 && (
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm">
            <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
              <div>
                <span className="text-xs font-mono uppercase tracking-wider font-semibold text-emerald-400">
                  Execution Pathway
                </span>
                <h2 className="text-xl font-semibold text-white tracking-tight mt-0.5">
                  Sequenced Action Roadmap
                </h2>
              </div>
              <span className="text-xs font-mono text-zinc-400 bg-zinc-800 px-2.5 py-1 rounded">
                {roadmap.length} Actions
              </span>
            </div>

            <div className="space-y-3">
              {roadmap.map((act) => (
                <div
                  key={act.step}
                  className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 space-y-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="h-6 w-6 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-300 font-mono text-xs flex items-center justify-center font-bold">
                        {act.step}
                      </span>
                      <h3 className="text-sm font-bold text-white">{act.title}</h3>
                    </div>
                    {act.decision_gate && (
                      <p className="text-xs text-amber-300/90 pl-8">
                        Decision Gate: {act.decision_gate}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0 pl-8 sm:pl-0">
                    <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2.5 py-1 rounded border border-zinc-800">
                      {act.time_horizon}
                    </span>
                    <span className="text-[11px] font-mono text-zinc-300">
                      {act.responsible_role}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 5. Key Integrity Warnings */}
        {findings && findings.length > 0 && (
          <IntegrityFindingsCard findings={findings} />
        )}

        {/* 6. Evidence Quality */}
        {evidenceQuality && (
          <EvidenceQualityCard report={evidenceQuality} />
        )}
      </div>
    </main>
  );
}
