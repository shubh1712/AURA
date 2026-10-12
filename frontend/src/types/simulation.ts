/**
 * Authoritative TypeScript contracts matching AURA Deterministic What-if Simulation Engine (Phase 7A & 7B).
 * Parity enforced with backend/app/schemas/simulation.py.
 */

export type SimulationVariableType =
  | "percentage"
  | "currency"
  | "numeric"
  | "count"
  | "ratio";

export type SimulationUnit =
  | "USD"
  | "EUR"
  | "GBP"
  | "%"
  | "count"
  | "users"
  | "days"
  | "ms"
  | "ratio"
  | "other"
  | string;

export type SimulationCalculationStatus =
  | "calculated"
  | "unsupported_no_causal_mapping"
  | "unsupported_variable"
  | "invalid_bounds"
  | "reference_mismatch"
  | "no_adjustments";

/**
 * An authoritative numerical variable discovered from structured decision artifacts.
 */
export interface SimulationVariable {
  variable_id: string;
  label: string;
  description: string;
  unit?: string | null;
  value_type: SimulationVariableType;
  baseline_value: number;
  minimum_value?: number | null;
  maximum_value?: number | null;
  source_artifact_id: string;
  source_field_path: string;
  simulation_supported: boolean;
  support_reason: string;
}

/**
 * A user-proposed adjustment to a specific simulation variable.
 */
export interface SimulationAdjustment {
  variable_id: string;
  proposed_value: number;
  unit?: string | null;
}

/**
 * Request payload specifying baseline decision references and adjustments.
 */
export interface SimulationRequest {
  decision_model_id: string;
  scenario_set_id: string;
  recommendation_id: string;
  adjustments: SimulationAdjustment[];
}

/**
 * Granular record of how an individual adjustment transformed internal artifacts.
 */
export interface SimulationImpact {
  variable_id: string;
  original_value: number;
  adjusted_value: number;
  transformation_rule_id: string;
  affected_fields: string[];
  calculation_status: SimulationCalculationStatus;
  explanation: string;
}

/**
 * Authoritative deterministic result of a what-if simulation.
 */
export interface SimulationResult {
  id: string;
  decision_model_id: string;
  scenario_set_id: string;
  recommendation_id: string;
  applied_adjustments: SimulationAdjustment[];
  impacts: SimulationImpact[];
  baseline_fingerprint: string;
  baseline_resilience_score?: number | null;
  simulated_resilience_score?: number | null;
  score_delta?: number | null;
  warnings: string[];
  status: SimulationCalculationStatus;
  created_at?: string | null;
}

/**
 * API response contract for discovered adjustable simulation variables.
 */
export interface SimulationVariableDiscoveryResponse {
  analysis_id: string;
  job_id?: string | null;
  baseline_fingerprint: string;
  variables: SimulationVariable[];
  supported_count: number;
  unsupported_count: number;
  recalculation_capabilities: Record<string, unknown>;
}

/**
 * API request contract for submitting what-if simulation adjustments.
 */
export interface SimulationSubmitRequest {
  adjustments: SimulationAdjustment[];
  baseline_fingerprint?: string | null;
}

/**
 * API response contract for listing persisted simulations for an analysis.
 */
export interface SimulationListResponse {
  analysis_id: string;
  simulations: SimulationResult[];
  total_count: number;
}

/**
 * Authoritative API response contract for grounded simulation explanations (Phase 7D).
 */
export interface SimulationExplanationResponse {
  simulation_id: string;
  baseline_fingerprint: string;
  summary: string;
  what_changed: string[];
  constraint_implications: string[];
  resilience_interpretation: string;
  limitations: string[];
  suggested_validation_steps: string[];
  evidence_or_artifact_references: string[];
  generation_status: "generated" | "cached" | string;
  model_name?: string | null;
  prompt_version: string;
  created_at?: string | null;
}
