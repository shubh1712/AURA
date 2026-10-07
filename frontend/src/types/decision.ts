import type { ConfidenceLevel, CriticalityLevel } from "./evidence";

export type DecisionStatus =
  | "idle"
  | "draft"
  | "submitting"
  | "completed"
  | "failed"
  | "error";

export interface DecisionFormData {
  question: string;
  context: string;
  constraints: string;
}

export interface DecisionInput {
  title: string;
  context: string;
  targetOutcome?: string;
  constraints?: string[];
}

export interface DecisionDecompositionSummary {
  variablesCount: number;
  constraintsCount: number;
  stakeholdersCount: number;
}

export interface AnalysisSession {
  id: string;
  formData: DecisionFormData;
  status: DecisionStatus;
  createdAt: string;
  updatedAt: string;
}

// ------------------------------------------------------------------------------
// Canonical Backend DecisionModel Types (mirrors backend/app/schemas/decision_model.py)
// ------------------------------------------------------------------------------

export type ProvenanceType = "user_provided" | "inferred" | "unknown";

export type DecisionType =
  | "resource_allocation"
  | "strategic_direction"
  | "architecture_technology"
  | "operational_policy"
  | "product_roadmap"
  | "general_choice";

export type TimeHorizon =
  | "immediate"
  | "short_term"
  | "medium_term"
  | "long_term";

export type ComplexityLevel = "low" | "medium" | "high";

export type ReversibilityLevel =
  | "reversible"
  | "partially_reversible"
  | "irreversible";

export type VariableType =
  | "percentage"
  | "currency"
  | "numeric"
  | "boolean"
  | "categorical"
  | "qualitative";

export interface Decision {
  raw_prompt: string;
  summary: string;
  decision_type: DecisionType;
  time_horizon: TimeHorizon;
}

export interface Complexity {
  level: ComplexityLevel;
  reasoning: string;
  reversibility: ReversibilityLevel;
  score?: number | null;
}

export interface Objective {
  id: string;
  description: string;
  is_primary: boolean;
  target_metric?: string | null;
  provenance: ProvenanceType;
}

export interface Variable {
  id: string;
  name: string;
  description: string;
  variable_type: VariableType;
  baseline_value?: number | string | boolean | null;
  proposed_value?: number | string | boolean | null;
  unit?: string | null;
  is_controllable: boolean;
  provenance: ProvenanceType;
  baseline_provenance?: ProvenanceType | null;
  proposed_provenance?: ProvenanceType | null;
}

export interface Constraint {
  id: string;
  name: string;
  description: string;
  is_hard_constraint: boolean;
  threshold_expression?: string | null;
  source: string;
  provenance: ProvenanceType;
}

export interface Stakeholder {
  id: string;
  group: string;
  impact_nature: string;
  influence_level: CriticalityLevel;
  provenance: ProvenanceType;
}

export interface Tradeoff {
  id: string;
  upside: string;
  downside: string;
  affected_variable_ids: string[];
  provenance: ProvenanceType;
}

export interface Assumption {
  id: string;
  statement: string;
  confidence: ConfidenceLevel;
  falsification_condition?: string | null;
  provenance: ProvenanceType;
}

export interface Unknown {
  id: string;
  question: string;
  criticality: CriticalityLevel;
  potential_sources: string[];
  provenance: ProvenanceType;
}

export interface DecisionModel {
  id: string;
  decision: Decision;
  complexity: Complexity;
  objectives: Objective[];
  variables: Variable[];
  constraints: Constraint[];
  stakeholders: Stakeholder[];
  tradeoffs: Tradeoff[];
  assumptions: Assumption[];
  unknowns: Unknown[];
  key_questions: string[];
}
