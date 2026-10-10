/**
 * AURA Decision Recommendation & Action Planning TypeScript contracts.
 * Matches backend app.schemas.recommendation.
 */

export type RecommendationDecisionStatus =
  | "proceed"
  | "conditional"
  | "pilot"
  | "defer"
  | "reject"
  | "insufficient_evidence";

export type DecisionStatus = RecommendationDecisionStatus;

export type EvidenceStrength =
  | "strong"
  | "moderate"
  | "limited"
  | "contested"
  | "insufficient";

export type DecisionReadiness =
  | "ready"
  | "conditional"
  | "needs_validation"
  | "blocked";

export type RecommendationStability = "high" | "moderate" | "volatile";

export type ActionPriority = "critical" | "high" | "medium" | "low";

export type ActionTimeHorizon =
  | "immediate"
  | "near_term"
  | "medium_term"
  | "long_term";

export interface AlternativeOption {
  id: string;
  name: string;
  description: string;
  tradeoffs: string[];
  why_not_recommended: string;
}

export interface DecisionGate {
  id: string;
  condition: string;
  target_milestone: string;
  verification_method: string;
  fallback_action: string;
}

export interface ActionItem {
  id: string;
  title: string;
  objective: string;
  description: string;
  priority: ActionPriority;
  responsible_role: string;
  time_horizon: ActionTimeHorizon;
  dependencies: string[];
  success_metrics: string[];
  risk_mitigations: string[];
  decision_gates: DecisionGate[];
  fallback_action?: string | null;
}

export interface ActionPlan {
  summary: string;
  actions: ActionItem[];
  key_milestones: string[];
}

export interface UncertaintyAssessment {
  evidence_strength: EvidenceStrength;
  decision_readiness: DecisionReadiness;
  recommendation_stability: RecommendationStability;
  critical_missing_information: string[];
  conditions_changing_recommendation: string[];
  assumptions_relied_upon: string[];
  evidence_gaps_relied_upon: string[];
}

export interface DecisionRecommendation {
  id: string;
  decision_model_id: string;
  evidence_package_id: string;
  reasoning_board_id: string;
  decision_status: DecisionStatus;
  recommended_action: string;
  executive_rationale: string;
  supporting_evidence_item_ids: string[];
  relevant_assumption_ids: string[];
  relevant_evidence_gap_ids: string[];
  unresolved_disagreement_ids: string[];
  alternative_options: AlternativeOption[];
  uncertainty_assessment: UncertaintyAssessment;
  action_plan: ActionPlan;
  created_at: string;
}
