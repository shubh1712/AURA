/**
 * Deterministic Resilience Engine TypeScript interfaces matching backend app.schemas.resilience.
 */

export type ResilienceRating =
  | "high"
  | "moderate"
  | "fragile"
  | "vulnerable";

export type ResiliencePillar =
  | "constraint_boundary_tolerance"
  | "pessimistic_scenario_survivability"
  | "contingency_and_fallback_coverage"
  | "information_robustness"
  | "pessimistic_survivability"
  | "contingency_coverage";

export interface ResilienceSubScore {
  category: string;
  score: number;
  max_score?: number;
  rationale: string;
  vulnerabilities_detected?: string[];

  // Optional aliases for defensive compatibility
  pillar?: ResiliencePillar | string;
  name?: string;
  weight?: number;
  vulnerabilities?: string[];
}

export interface ResilienceReport {
  id: string;
  decision_model_id: string;
  scenario_set_id: string;
  recommendation_id: string;
  overall_score: number;
  rating: ResilienceRating;
  sub_scores: ResilienceSubScore[];
  critical_vulnerabilities: string[];
  stress_test_passed: boolean;
  recommended_hedges: string[];
  calculation_version?: string;
  created_at?: string;
}
