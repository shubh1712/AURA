/**
 * AURA Scenario Engine TypeScript Contracts (Phase 5C).
 *
 * Strictly matches backend Pydantic models from backend/app/schemas/scenario.py:
 * - ScenarioType: "optimistic" | "base_case" | "pessimistic"
 * - ScenarioKeyEvent
 * - ScenarioMilestone
 * - FutureScenario
 * - ScenarioSet
 */

export type ScenarioType = "optimistic" | "base_case" | "pessimistic";

export interface ScenarioKeyEvent {
  id: string;
  title: string;
  description: string;
  timeframe: string;
  trigger_condition?: string | null;
  impact_on_decision?: string | null;
}

export interface ScenarioMilestone {
  id: string;
  title: string;
  description: string;
  time_horizon: string;
  expected_outcome: string;
}

export interface FutureScenario {
  id: string;
  scenario_type: ScenarioType;
  probability: number;
  name: string;
  narrative: string;
  key_events: ScenarioKeyEvent[];
  risks: string[];
  opportunities: string[];
  timeline: ScenarioMilestone[];
  supporting_evidence_item_ids: string[];
  relevant_assumption_ids: string[];
  relevant_constraint_ids: string[];
  relevant_gap_ids: string[];
}

export interface ScenarioSet {
  id: string;
  decision_model_id: string;
  recommendation_id?: string | null;
  reasoning_board_id?: string | null;
  evidence_package_id?: string | null;
  summary: string;
  scenarios: FutureScenario[];
  created_at: string;
}
