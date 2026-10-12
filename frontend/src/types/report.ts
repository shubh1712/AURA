/**
 * AURA Shared Presentation & Report Model Types (Day 8G).
 *
 * Single normalized typed presentation model driving:
 * - Executive Visual Dashboard
 * - Online Summary Report (/analysis/[id]/summary)
 * - Online Detailed Audit Report (/analysis/[id]/detailed)
 * - Vector PDF generation (Summary & Detailed)
 */

import {
  CalculationResult,
  DecisionIntegrityReport,
  DecisionReadinessStatus,
  EvidenceQualityReport,
  IntegrityFinding,
  IntegrityStatus,
  OptionComparisonReport,
  UncertaintyCalibrationReport,
} from "./integrity";

export interface PerspectiveSummary {
  perspective_type: string;
  title: string;
  stance: string;
  key_argument: string;
  critical_concerns: string[];
}

export interface ActionRoadmapItem {
  step: number;
  title: string;
  time_horizon: string;
  responsible_role: string;
  decision_gate: string | null;
  fallback_plan: string | null;
}

export interface ScenarioSummaryItem {
  name: string;
  probability_weight: string;
  implication: string;
}

export interface DecisionOverviewModel {
  decision_title: string;
  recommended_direction: string;
  short_rationale: string;
  decision_readiness: DecisionReadinessStatus;
  integrity_status: IntegrityStatus;
  critical_warning_count: number;
  top_falsification_condition: string;
  key_metrics: Record<string, string>;
}

export interface SharedReportModel {
  analysis_id: string;
  created_at?: string;
  generated_at?: string;
  overview: DecisionOverviewModel;
  option_comparison?: OptionComparisonReport;
  calculations?: CalculationResult[];
  scenario_matrix?: Record<string, unknown>[];
  scenarios_summary?: ScenarioSummaryItem[];
  resilience_scorecard?: Record<string, unknown>;
  evidence_quality?: EvidenceQualityReport;
  uncertainty_calibration?: UncertaintyCalibrationReport;
  integrity_findings?: IntegrityFinding[];
  integrity_report?: DecisionIntegrityReport;
  boardroom_perspectives?: PerspectiveSummary[];
  perspectives: PerspectiveSummary[];
  action_roadmap?: ActionRoadmapItem[];
  roadmap: ActionRoadmapItem[];
  decision_gates?: Record<string, unknown>[];
  full_decision_model?: Record<string, unknown>;
  full_framing?: Record<string, unknown>;
  full_evidence_package?: Record<string, unknown>;
  full_recommendation?: Record<string, unknown>;
  full_resilience_report?: Record<string, unknown>;
  full_scenarios?: Record<string, unknown>;
  source_fingerprint?: string;
  report_mode?: string;
}
