/**
 * AURA Decision Integrity & Cross-Stage Consistency Types (Day 8G).
 *
 * Strict typing for deterministic calculations, consistency findings,
 * qualitative option comparison, evidence quality, and uncertainty calibration.
 */

export type CalculationStatus =
  | "feasible"
  | "infeasible"
  | "unresolved"
  | "not_applicable";

export interface CalculationResult {
  calculation_id: string;
  title: string;
  category: string;
  formula?: string;
  formula_expression?: string;
  status: CalculationStatus;
  value: number | null;
  value_min?: number | null;
  value_max?: number | null;
  unit: string | null;
  currency: string | null;
  provenance?: string;
  explanation: string;
  missing_inputs: string[];
  supported_range?: [number, number] | null;
  assumptions?: string[];
  explicit_assumptions?: string[];
}

export type IntegritySeverity = "critical" | "high" | "medium" | "low";
export type FindingStatus = "confirmed" | "requires_review" | "unresolved";

export interface IntegrityFinding {
  finding_id: string;
  rule_code: string;
  severity: IntegritySeverity;
  status: FindingStatus;
  affected_stages: number[];
  title: string;
  description: string;
  relevant_values: Record<string, unknown>;
  units: string | null;
  provenance: string;
  suggested_resolution: string;
}

export interface OptionComparisonItem {
  option_id: string;
  title: string;
  description: string;
  is_recommended: boolean;
  strengths: string[];
  weaknesses: string[];
  constraint_compatibility: string;
  supporting_evidence_count: number;
  missing_evidence: string[];
  key_tradeoffs: string[];
  feasibility_status: string;
}

export interface OptionComparisonReport {
  evaluated_criteria: string[];
  options: OptionComparisonItem[];
  comparison_matrix_note: string;
  is_conclusive: boolean;
}

export type SourceCategory =
  | "primary_empirical"
  | "independent_secondary"
  | "official_standard"
  | "vendor_produced"
  | "opinion_commentary"
  | "unknown";

export interface SourceQualityClassification {
  source_id: string;
  title: string;
  url: string;
  category: SourceCategory;
  is_independent: boolean;
  is_duplicate: boolean;
  credibility_notes: string;
  limitations: string[];
}

export interface EvidenceQualityReport {
  total_sources: number;
  duplicate_sources_detected: number;
  category_breakdown: Record<string, number>;
  classifications: SourceQualityClassification[];
  independence_ratio: number;
}

export type GapDecisionImpact =
  | "blocks_calculation"
  | "determines_hard_constraint"
  | "alters_recommendation"
  | "expansion_gate"
  | "informational";

export interface RankedEvidenceGap {
  gap_id: string;
  description: string;
  decision_impact: GapDecisionImpact;
  rank: number;
  concrete_validation_action: string;
}

export interface UncertaintyCalibrationReport {
  is_calibrated: boolean;
  scenario_weights_note: string;
  ranked_gaps: RankedEvidenceGap[];
  calibration_warnings: string[];
}

export type IntegrityStatus =
  | "checking"
  | "passed"
  | "warning"
  | "warnings_present"
  | "critical_concerns"
  | "integrity_compromised"
  | "insufficient_data"
  | "unresolved"
  | "unavailable";

export type DecisionReadinessStatus =
  | "ready"
  | "conditional"
  | "needs_validation"
  | "blocked";

export interface DecisionIntegrityReport {
  analysis_id: string;
  rule_version: string;
  evaluation_timestamp: string;
  overall_status: IntegrityStatus;
  decision_readiness: DecisionReadinessStatus;
  severity_counts: Record<string, number>;
  calculations: CalculationResult[];
  findings: IntegrityFinding[];
  option_comparison: OptionComparisonReport;
  evidence_quality: EvidenceQualityReport;
  uncertainty_calibration: UncertaintyCalibrationReport;
  source_fingerprint: string;
}
