"use client";

import React from "react";
import type { AnalysisResponse } from "@/types";
import { ActionTimelineVisual } from "../charts/ActionTimelineVisual";
import { DecisionGateVisual } from "../charts/DecisionGateVisual";
import { ActionIntelligenceDashboard } from "../action/ActionIntelligenceDashboard";
import { ActionUnavailableBanner } from "../action/ActionUnavailableBanner";

interface ActionPlanViewProps {
  result: AnalysisResponse;
  ownerId?: string | null;
}

export function ActionPlanView({ result, ownerId }: ActionPlanViewProps) {
  const recommendation = result.recommendation;
  const hasRecommendation = Boolean(recommendation);
  const baselinePlan = recommendation?.action_plan;

  // Flatten decision gates from baseline actions if available
  const baselineGates = baselinePlan?.actions?.flatMap((a) => a.decision_gates || []) || [];

  return (
    <div className="space-y-7" aria-label="Action Execution Plan and Governance">
      {/* 1. Header Banner */}
      <div className="rounded-2xl border border-zinc-800 bg-gradient-to-r from-zinc-950 via-zinc-900/40 to-zinc-950 p-6 sm:p-7 space-y-2 text-zinc-100 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
            Execution Intelligence
          </span>
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        </div>
        <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
          Operational Roadmap &amp; Decision Gates
        </h3>
        <p className="text-xs sm:text-sm text-zinc-400 max-w-3xl font-sans leading-relaxed">
          Phased execution strategy grounded in validated decision parameters.
          Includes role responsibilities, explicit dependencies, concrete execution steps, and mandatory rollback response criteria.
        </p>
      </div>

      {/* 2. Baseline Visual Timeline & Decision Gates (Immediately available from Stage 4) */}
      {baselinePlan && baselinePlan.actions && baselinePlan.actions.length > 0 && (
        <div className="space-y-6">
          {/* Visual Phased Timeline */}
          <ActionTimelineVisual actions={baselinePlan.actions} />

          {/* Decision Gates & Rollback Triggers */}
          {baselineGates.length > 0 && (
            <DecisionGateVisual gates={baselineGates} />
          )}
        </div>
      )}

      {/* 3. Action Intelligence (Gemini-Powered Deep Operationalization) */}
      <div className="space-y-4 pt-2">
        {hasRecommendation ? (
          <ActionIntelligenceDashboard
            analysisId={result.analysis_id}
            ownerId={ownerId || null}
          />
        ) : (
          <ActionUnavailableBanner
            historical={false}
            reason={
              result.recommendation_error ||
              "Decision Recommendation (Stage 4) is required to generate an operational Action Plan."
            }
          />
        )}
      </div>
    </div>
  );
}
