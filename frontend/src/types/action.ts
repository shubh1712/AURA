/**
 * AURA Action Intelligence TypeScript Contracts (Day 8A).
 *
 * Strictly aligns with backend Pydantic models from:
 * backend/app/schemas/action_intelligence.py:
 * - CriterionType
 * - ComparisonOperator
 * - ActionPriority
 * - ValidationSeverity
 * - ActionCriterion
 * - IntelligentActionItem
 * - IntelligentDecisionGate
 * - ValidationWarning
 * - IntelligentActionPlan
 * - ActionPlanResponse
 * - ActionPlanGenerationState
 */

export type CriterionType =
  | "hard_constraint"
  | "recommendation_target"
  | "evidence_threshold"
  | "qualitative"
  | "unsupported_metric";

export type ComparisonOperator =
  | ">="
  | "<="
  | ">"
  | "<"
  | "=="
  | "!="
  | "contains"
  | "qualitative";

export type ActionPriority = "high" | "medium" | "low";

export type ValidationSeverity =
  | "conflict"
  | "review_required"
  | "warning"
  | "info";

export interface ActionCriterion {
  criterion_id: string;
  criterion_type: CriterionType;
  description: string;
  metric_name?: string | null;
  operator?: ComparisonOperator | null;
  threshold_value?: number | null;
  threshold_raw?: string | null;
  unit?: string | null;
  provenance_type: string;
  source_reference?: string | null;
  is_hard?: boolean;
}

export interface IntelligentActionItem {
  action_id: string;
  source_action_reference?: string | null;
  title: string;
  description: string;
  priority: ActionPriority;
  sequence: number;
  owner_role: string;
  dependencies: string[];
  timing?: string | null;
  prerequisites: string[];
  execution_steps?: string[] | null;
  success_criteria: ActionCriterion[];
  risk_mitigations: string[];
  contingency_or_rollback?: string | null;
  evidence_references: string[];
  rationale: string;
  confidence_label: "high" | "moderate" | "low" | string;
  confidence_rationale?: string | null;
  missing_information: string[];
}

export interface IntelligentDecisionGate {
  gate_id: string;
  title: string;
  checkpoint: string;
  criteria: ActionCriterion[];
  related_action_ids: string[];
  failure_response: string;
  source_references: string[];
  unresolved_conflicts: string[];
}

export interface ValidationWarning {
  warning_id: string;
  severity: ValidationSeverity;
  message: string;
  related_action_ids: string[];
  related_gate_ids: string[];
  related_criterion_ids: string[];
}

export interface IntelligentActionPlan {
  plan_id: string;
  analysis_id: string;
  source_recommendation_fingerprint: string;
  schema_version: string;
  generator_version: string;
  created_at: string;
  strategy_summary: string;
  actions: IntelligentActionItem[];
  decision_gates: IntelligentDecisionGate[];
  unresolved_questions: string[];
  limitations: string[];
  validation_warnings: ValidationWarning[];
  generation_metadata: Record<string, unknown>;
}

export interface ActionPlanResponse {
  analysis_id: string;
  status: "ready" | "cached" | "running" | "failed" | "not_generated" | string;
  cached: boolean;
  plan: IntelligentActionPlan | null;
  error_message?: string | null;
}

export type ActionPlanGenerationState =
  | "idle"
  | "loading"
  | "success"
  | "cached"
  | "error";
