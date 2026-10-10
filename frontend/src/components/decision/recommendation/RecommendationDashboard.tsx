"use client";

import React from "react";
import type {
  DecisionRecommendation,
  DecisionModel,
  EvidencePackage,
  ReasoningBoard,
} from "@/types";
import { ExecutiveRecommendationHero } from "./ExecutiveRecommendationHero";
import { UncertaintyReadinessSection } from "./UncertaintyReadinessSection";
import { ActionRoadmapSection } from "./ActionRoadmapSection";
import { AlternativeOptionsSection } from "./AlternativeOptionsSection";
import { EvidenceTraceabilitySection } from "./EvidenceTraceabilitySection";

interface RecommendationDashboardProps {
  recommendation: DecisionRecommendation;
  decisionModel?: DecisionModel | null;
  evidencePackage?: EvidencePackage | null;
  reasoningBoard?: ReasoningBoard | null;
}

export function RecommendationDashboard({
  recommendation,
  decisionModel,
  evidencePackage,
  reasoningBoard,
}: RecommendationDashboardProps) {
  if (!recommendation) {
    return null;
  }

  return (
    <div
      className="space-y-8"
      aria-label="Executive Recommendation Dashboard"
    >
      {/* 1. Executive Recommendation Hero (Answers: What does AURA recommend? Why?) */}
      <ExecutiveRecommendationHero recommendation={recommendation} />

      {/* 2. Uncertainty & Decision Readiness (Answers: How reliable is the recommendation?) */}
      {recommendation.uncertainty_assessment && (
        <UncertaintyReadinessSection
          uncertainty={recommendation.uncertainty_assessment}
          decisionModel={decisionModel}
          evidencePackage={evidencePackage}
        />
      )}

      {/* 3. Action Roadmap & Decision Gates (Answers: What should the user do next? What conditions change it?) */}
      {recommendation.action_plan && (
        <ActionRoadmapSection actionPlan={recommendation.action_plan} />
      )}

      {/* 4. Alternative Courses of Action */}
      {recommendation.alternative_options &&
        recommendation.alternative_options.length > 0 && (
          <AlternativeOptionsSection
            alternatives={recommendation.alternative_options}
            primaryRecommendedAction={recommendation.recommended_action}
          />
        )}

      {/* 5. Evidence Traceability & Epistemic Audit Trail */}
      <EvidenceTraceabilitySection
        recommendation={recommendation}
        evidencePackage={evidencePackage}
        decisionModel={decisionModel}
        reasoningBoard={reasoningBoard}
      />
    </div>
  );
}
