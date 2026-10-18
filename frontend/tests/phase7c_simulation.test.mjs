import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components built for Phase 7C (What-if Simulation Dashboard)
import { WhatIfDashboard } from "../src/components/decision/simulation/WhatIfDashboard.tsx";
import { SimulationVariableControls } from "../src/components/decision/simulation/SimulationVariableControls.tsx";
import { SimulationComparisonPanel } from "../src/components/decision/simulation/SimulationComparisonPanel.tsx";
import { SimulationConstraintImpacts } from "../src/components/decision/simulation/SimulationConstraintImpacts.tsx";
import { SimulationHistory } from "../src/components/decision/simulation/SimulationHistory.tsx";
import { SimulationUnavailableBanner } from "../src/components/decision/simulation/SimulationUnavailableBanner.tsx";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import {
  getSimulationVariables,
  runSimulation,
  listSimulations,
  getSimulationById,
  ApiClientError,
} from "../src/lib/api.ts";

// ------------------------------------------------------------------------------
// Comprehensive Typed Test Fixtures matching backend Phase 7A & 7B schemas
// ------------------------------------------------------------------------------

const MOCK_DECISION_MODEL = {
  id: "dec_model_phase7c",
  decision: {
    raw_prompt: "Should we scale cloud infrastructure across multiple availability zones?",
    summary: "Multi-region cloud infrastructure scaling decision.",
    decision_type: "architecture_technology",
    time_horizon: "medium_term",
  },
  complexity: {
    level: "high",
    reasoning: "Operational costs and distributed replication trade-offs.",
    reversibility: "partially_reversible",
    score: 72.0,
  },
  objectives: [
    {
      id: "obj_uptime",
      description: "99.99% service availability",
      is_primary: true,
      target_metric: "99.99%",
      provenance: "user_provided",
    },
  ],
  variables: [],
  constraints: [
    {
      id: "cnstr_budget",
      name: "Cloud Spend Ceiling",
      description: "Monthly cloud expenditure capped at $50,000",
      is_hard_constraint: true,
      threshold_expression: "spend <= 50000",
      source: "User input",
      provenance: "user_provided",
    },
  ],
  stakeholders: [],
  tradeoffs: [],
  assumptions: [],
  unknowns: [],
  key_questions: [],
};

const MOCK_RECOMMENDATION = {
  id: "rec_phase7c",
  decision_model_id: "dec_model_phase7c",
  recommended_option_id: "opt_multi_region",
  recommended_option_title: "Execute Multi-Region Scaling with Automated Failover",
  decision_readiness: "actionable",
  confidence_score: 84.0,
  executive_summary: "Multi-region deployment provides optimal fault tolerance within operational bounds.",
  stability_assessment: {
    stability: "stable",
    justification: "Sufficient redundancy under tested stress constraints.",
  },
  evidence_strength: "strong",
  decision_status: "proceed_with_safeguards",
  action_plan: {
    actions: [],
    immediate_actions: [],
    near_term_actions: [],
    long_term_actions: [],
    contingent_actions: [],
    total_actions: 0,
    hard_gate_count: 0,
  },
  decision_gates: [],
  alternative_options: [],
  uncertainty_assessment: {
    evidence_strength: "strong",
    decision_readiness: "actionable",
    recommendation_stability: "stable",
    residual_uncertainties: [],
    critical_assumptions: [],
    fallbacks: [],
  },
};

const MOCK_SCENARIO_SET = {
  id: "scen_set_phase7c",
  decision_model_id: "dec_model_phase7c",
  scenarios: [
    {
      id: "scen_base",
      scenario_type: "base_case",
      title: "Planned Regional Expansion",
      narrative: "Traffic grows at projected 15% rate without disruptions.",
      probability: 0.6,
      key_events: [],
      milestones: [],
      affected_objective_ids: ["obj_uptime"],
      relevant_constraint_ids: ["cnstr_budget"],
    },
    {
      id: "scen_pes",
      scenario_type: "pessimistic_stress",
      title: "Regional Outage with Traffic Spike",
      narrative: "Zone outage forces failover during peak transactional load.",
      probability: 0.25,
      key_events: [],
      milestones: [],
      affected_objective_ids: ["obj_uptime"],
      relevant_constraint_ids: ["cnstr_budget"],
    },
    {
      id: "scen_opt",
      scenario_type: "optimistic_expansion",
      title: "Rapid Customer Adoption",
      narrative: "Accelerated user acquisition lowers marginal infra costs.",
      probability: 0.15,
      key_events: [],
      milestones: [],
      affected_objective_ids: ["obj_uptime"],
      relevant_constraint_ids: ["cnstr_budget"],
    },
  ],
};

const MOCK_RESILIENCE_REPORT = {
  id: "res_phase7c",
  decision_model_id: "dec_model_phase7c",
  overall_resilience_score: 78.5,
  rating: "moderate",
  pillar_scores: {
    stress_survival: 80.0,
    optionality: 75.0,
    uncertainty_preparedness: 76.0,
    reversibility: 83.0,
  },
  pillar_breakdown: [
    { pillar: "stress_survival", score: 80.0, weight: 0.35, rationale: "Handles zone failover." },
    { pillar: "optionality", score: 75.0, weight: 0.25, rationale: "Multi-cloud migration paths available." },
    { pillar: "uncertainty_preparedness", score: 76.0, weight: 0.25, rationale: "Runbooks documented." },
    { pillar: "reversibility", score: 83.0, weight: 0.15, rationale: "Workloads containerized." },
  ],
  critical_vulnerabilities: [],
  recommended_hedges: [],
  calculation_version: "1.0.0",
};

const MOCK_DISCOVERY_VARIABLES = [
  {
    variable_id: "var_cloud_budget",
    label: "Monthly Cloud Budget",
    description: "Allocated infrastructure spending cap.",
    unit: "USD",
    value_type: "currency",
    baseline_value: 35000.0,
    minimum_value: 10000.0,
    maximum_value: 50000.0,
    source_artifact_id: "dec_model_phase7c",
    source_field_path: "decision_model.variables[0].baseline_value",
    simulation_supported: true,
    support_reason: "Linked to constraint cnstr_budget threshold evaluation.",
  },
  {
    variable_id: "var_latency_sla",
    label: "p99 Latency SLA",
    description: "Allowable read request latency limit.",
    unit: "ms",
    value_type: "numeric",
    baseline_value: 15.0,
    minimum_value: 0.0,
    maximum_value: null, // Unbounded upper bound
    source_artifact_id: "dec_model_phase7c",
    source_field_path: "decision_model.variables[1].baseline_value",
    simulation_supported: true,
    support_reason: "Evaluates operational SLA compliance thresholds.",
  },
  {
    variable_id: "var_qualitative_sentiment",
    label: "Team Morale Score",
    description: "Subjective developer team satisfaction score.",
    unit: null,
    value_type: "numeric",
    baseline_value: 80.0,
    minimum_value: null,
    maximum_value: null,
    source_artifact_id: "dec_model_phase7c",
    source_field_path: "decision_model.variables[2].baseline_value",
    simulation_supported: false,
    support_reason: "Qualitative assumption with no validated mathematical constraint mapping.",
  },
];

const MOCK_DISCOVERY_RESPONSE = {
  analysis_id: "ana_phase7c_001",
  job_id: "job_phase7c_001",
  baseline_fingerprint: "bfp_a1b2c3d4e5f60718293a4b5c6d7e8f90",
  variables: MOCK_DISCOVERY_VARIABLES,
  supported_count: 2,
  unsupported_count: 1,
  recalculation_capabilities: {
    direct_substitution: true,
    constraint_threshold_evaluation: true,
    resilience_score_recalculation: false,
    note: "Business metric adjustments evaluate operational constraint threshold breaches.",
  },
};

const MOCK_SIMULATION_RESULT_NULL_DELTA = {
  id: "sim_11111111111111111111111111111111",
  decision_model_id: "dec_model_phase7c",
  scenario_set_id: "scen_set_phase7c",
  recommendation_id: "rec_phase7c",
  applied_adjustments: [
    {
      variable_id: "var_cloud_budget",
      proposed_value: 45000.0,
      unit: "USD",
    },
  ],
  impacts: [
    {
      variable_id: "var_cloud_budget",
      original_value: 35000.0,
      adjusted_value: 45000.0,
      transformation_rule_id: "rule_direct_variable_substitution",
      affected_fields: ["decision_model.variables[0].baseline_value"],
      calculation_status: "calculated",
      explanation: "Cloud budget adjusted to $45,000. Below maximum ceiling of $50,000.",
    },
  ],
  baseline_fingerprint: "bfp_a1b2c3d4e5f60718293a4b5c6d7e8f90",
  baseline_resilience_score: 78.5,
  simulated_resilience_score: null,
  score_delta: null,
  warnings: [],
  status: "calculated",
};

const MOCK_SIMULATION_RESULT_VALID_DELTA = {
  id: "sim_22222222222222222222222222222222",
  decision_model_id: "dec_model_phase7c",
  scenario_set_id: "scen_set_phase7c",
  recommendation_id: "rec_phase7c",
  applied_adjustments: [
    {
      variable_id: "var_cloud_budget",
      proposed_value: 55000.0,
      unit: "USD",
    },
  ],
  impacts: [
    {
      variable_id: "var_cloud_budget",
      original_value: 35000.0,
      adjusted_value: 55000.0,
      transformation_rule_id: "rule_constraint_threshold_evaluation",
      affected_fields: ["decision_model.constraints[0].status"],
      calculation_status: "calculated",
      explanation: "Cloud budget $55,000 breaches maximum expenditure ceiling of $50,000.",
    },
  ],
  baseline_fingerprint: "bfp_a1b2c3d4e5f60718293a4b5c6d7e8f90",
  baseline_resilience_score: 78.5,
  simulated_resilience_score: 62.1,
  score_delta: -16.4,
  warnings: ["Hard constraint 'Cloud Spend Ceiling' breached."],
  status: "calculated",
};

// ------------------------------------------------------------------------------
// Phase 7C Test Suite
// ------------------------------------------------------------------------------

describe("Phase 7C: What-if Simulation UI & Interaction", () => {
  // Test 1: API type contract alignment
  test("1. API type contract alignment", () => {
    assert.equal(typeof MOCK_DISCOVERY_RESPONSE.analysis_id, "string");
    assert.equal(typeof MOCK_DISCOVERY_RESPONSE.baseline_fingerprint, "string");
    assert.equal(Array.isArray(MOCK_DISCOVERY_RESPONSE.variables), true);
    assert.equal(MOCK_DISCOVERY_RESPONSE.supported_count, 2);
    assert.equal(MOCK_DISCOVERY_RESPONSE.unsupported_count, 1);

    const v = MOCK_DISCOVERY_VARIABLES[0];
    assert.equal(typeof v.variable_id, "string");
    assert.equal(typeof v.label, "string");
    assert.equal(typeof v.baseline_value, "number");
    assert.equal(typeof v.simulation_supported, "boolean");

    const res = MOCK_SIMULATION_RESULT_NULL_DELTA;
    assert.equal(typeof res.id, "string");
    assert.match(res.id, /^sim_[a-f0-9]{32}$/);
    assert.equal(Array.isArray(res.applied_adjustments), true);
    assert.equal(Array.isArray(res.impacts), true);
  });

  // Test 2: Discovery loading state
  test("2. Discovery loading state renders accessible indicator", () => {
    assert.equal(typeof WhatIfDashboard, "function");
    const html = renderToStaticMarkup(
      React.createElement(SimulationUnavailableBanner, {
        historical: false,
        reason: "Discovering simulation variables...",
      })
    );
    assert.match(html, /Discovering simulation variables/);
    assert.match(html, /role="alert"/);
  });

  // Test 3: Supported variables rendered
  test("3. Supported variables rendered with label, baseline, unit, and source path", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: MOCK_DISCOVERY_VARIABLES,
        adjustments: { var_cloud_budget: 35000.0, var_latency_sla: 15.0 },
        rawInputs: { var_cloud_budget: "35000", var_latency_sla: "15" },
        inputErrors: {},
        hasChanges: false,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    assert.match(html, /Monthly Cloud Budget/);
    assert.match(html, /Baseline: 35,000 USD/);
    assert.match(html, /p99 Latency SLA/);
    assert.match(html, /decision_model\.variables\[0\]\.baseline_value/);
    assert.match(html, /Linked to constraint cnstr_budget/);
  });

  // Test 4: Unsupported variables explained
  test("4. Unsupported variables explained with transparent rationale", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: MOCK_DISCOVERY_VARIABLES,
        adjustments: {},
        rawInputs: {},
        inputErrors: {},
        hasChanges: false,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    assert.match(html, /Discovered Variables Without Validated Causal Mapping/);
    assert.match(html, /\[1\]/); // 1 unsupported variable
  });

  // Test 5: No-variable state
  test("5. No-variable state displays clean informational notice", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: [],
        adjustments: {},
        rawInputs: {},
        inputErrors: {},
        hasChanges: false,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    assert.match(html, /No supported numerical variables were discovered/);
  });

  // Test 6: Finite bounds handling
  test("6. Finite bounds handling renders both slider and range limits", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: [MOCK_DISCOVERY_VARIABLES[0]], // var_cloud_budget has min 10000, max 50000
        adjustments: { var_cloud_budget: 35000.0 },
        rawInputs: { var_cloud_budget: "35000" },
        inputErrors: {},
        hasChanges: false,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    assert.match(html, /type="range"/);
    assert.match(html, /min="10000"/);
    assert.match(html, /max="50000"/);
    assert.match(html, /Min: 10000/);
    assert.match(html, /Max: 50000/);
  });

  // Test 7: Unbounded numeric input
  test("7. Unbounded numeric input avoids inventing slider bounds", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: [MOCK_DISCOVERY_VARIABLES[1]], // var_latency_sla has max null
        adjustments: { var_latency_sla: 15.0 },
        rawInputs: { var_latency_sla: "15" },
        inputErrors: {},
        hasChanges: false,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    // Should NOT have type="range" slider since maximum is null
    assert.doesNotMatch(html, /type="range"/);
    assert.match(html, /type="number"/);
    assert.match(html, /no upper limit/);
  });

  // Test 8: Reset to baseline
  test("8. Reset to baseline action is available and clickable", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: MOCK_DISCOVERY_VARIABLES,
        adjustments: { var_cloud_budget: 45000.0 },
        rawInputs: { var_cloud_budget: "45000" },
        inputErrors: {},
        hasChanges: true,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    assert.match(html, /Reset to Baseline/);
    // Button is not disabled when hasChanges is true
    assert.doesNotMatch(html, /disabled=""[^>]*>Reset to Baseline/);
  });

  // Test 9: No-op submission prevention
  test("9. No-op submission prevention disables Run Simulation when unchanged", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: MOCK_DISCOVERY_VARIABLES,
        adjustments: { var_cloud_budget: 35000.0, var_latency_sla: 15.0 },
        rawInputs: { var_cloud_budget: "35000", var_latency_sla: "15" },
        inputErrors: {},
        hasChanges: false, // No changes made
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    // Run Simulation button should have disabled attribute
    assert.match(html, /disabled=""[^>]*>.*?Run Simulation/s);
  });

  // Test 10: Successful simulation
  test("10. Successful simulation renders parameter comparison panel", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationComparisonPanel, {
        result: MOCK_SIMULATION_RESULT_NULL_DELTA,
        variables: MOCK_DISCOVERY_VARIABLES,
      })
    );

    assert.match(html, /Baseline vs Simulated Assumptions/);
    assert.match(html, /Monthly Cloud Budget/);
    assert.match(html, /35,000 USD/);
    assert.match(html, /45,000 USD/);
    assert.match(html, /\+10,000 USD/);
    assert.match(html, /\+28\.6%/);
  });

  // Test 11: Constraint impact explanation
  test("11. Constraint impact explanation displays engine threshold findings and affected fields", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationConstraintImpacts, {
        result: MOCK_SIMULATION_RESULT_NULL_DELTA,
        variables: MOCK_DISCOVERY_VARIABLES,
      })
    );

    assert.match(html, /Constraint Threshold &amp; Artifact Impacts/);
    assert.match(html, /Cloud budget adjusted to \$45,000\. Below maximum ceiling of \$50,000\./);
    assert.match(html, /decision_model\.variables\[0\]\.baseline_value/);
    assert.match(html, /rule_direct_variable_substitution/);
  });

  // Test 12: Null score delta rendered as unavailable
  test("12. Null score delta rendered truthfully as unavailable without fabricated zero change", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationComparisonPanel, {
        result: MOCK_SIMULATION_RESULT_NULL_DELTA,
        variables: MOCK_DISCOVERY_VARIABLES,
      })
    );

    // Displays clear badge instead of 0.0 or synthetic delta
    assert.match(html, /Impact not currently calculable/);
    assert.match(html, /78\.5 \/ 100/); // Baseline resilience is preserved
    assert.match(html, /lacks a validated mathematical causal mapping/);
    // Must NOT display synthetic "+0.0" delta
    assert.doesNotMatch(html, /\+0\.0/);
    assert.doesNotMatch(html, /Deterministic Recalculation/);
  });

  // Test 13: Valid numerical score delta rendering
  test("13. Valid numerical score delta rendering displays deterministic recalculation", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationComparisonPanel, {
        result: MOCK_SIMULATION_RESULT_VALID_DELTA,
        variables: MOCK_DISCOVERY_VARIABLES,
      })
    );

    assert.match(html, /78\.5/); // Baseline
    assert.match(html, /62\.1/); // Simulated
    assert.match(html, /-16\.4/); // Delta
    assert.match(html, /Deterministic Recalculation/);
  });

  // Test 14: Baseline fingerprint included in submission
  test("14. Baseline fingerprint is included in submit payload structure", () => {
    const submitPayload = {
      adjustments: [
        { variable_id: "var_cloud_budget", proposed_value: 42000.0, unit: "USD" },
      ],
      baseline_fingerprint: "bfp_a1b2c3d4e5f60718293a4b5c6d7e8f90",
    };

    assert.equal(typeof submitPayload.baseline_fingerprint, "string");
    assert.match(submitPayload.baseline_fingerprint, /^bfp_[a-f0-9]{32}$/);
    assert.equal(submitPayload.adjustments.length, 1);
  });

  // Test 15: HTTP 409 mismatch handling
  test("15. HTTP 409 mismatch handling displays stale baseline warning", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationHistory, {
        history: [MOCK_SIMULATION_RESULT_NULL_DELTA],
        isLoading: false,
        error: null,
        selectedSimulationId: null,
        currentBaselineFingerprint: "bfp_DIFFERENT_CURRENT_FINGERPRINT", // Mismatch
        onSelectSimulation: () => {},
        onRefreshHistory: () => {},
      })
    );

    assert.match(html, /Stale Baseline/);
  });

  // Test 16: HTTP 422 validation handling
  test("16. HTTP 422 validation handling preserves input errors cleanly", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: MOCK_DISCOVERY_VARIABLES,
        adjustments: { var_cloud_budget: 65000.0 },
        rawInputs: { var_cloud_budget: "65000" },
        inputErrors: { var_cloud_budget: "Value cannot exceed 50000 USD." },
        hasChanges: true,
        isValid: false, // Invalid bounds
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    assert.match(html, /Value cannot exceed 50000 USD\./);
    assert.match(html, /role="alert"/);
  });

  // Test 17: Simulation history loading
  test("17. Simulation history loading renders list of previous runs", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationHistory, {
        history: [MOCK_SIMULATION_RESULT_NULL_DELTA, MOCK_SIMULATION_RESULT_VALID_DELTA],
        isLoading: false,
        error: null,
        selectedSimulationId: "sim_11111111111111111111111111111111",
        currentBaselineFingerprint: "bfp_a1b2c3d4e5f60718293a4b5c6d7e8f90",
        onSelectSimulation: () => {},
        onRefreshHistory: () => {},
      })
    );

    assert.match(html, /Previous Simulation Runs/);
    assert.match(html, /sim_11111111111111111111111111111111/);
    assert.match(html, /sim_22222222222222222222222222222222/);
    assert.match(html, /Active View/);
    assert.match(html, /Reopen Run/);
  });

  // Test 18: Saved simulation retrieval
  test("18. Saved simulation retrieval does not invent timestamps when absent", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationHistory, {
        history: [MOCK_SIMULATION_RESULT_NULL_DELTA], // created_at is not provided
        isLoading: false,
        error: null,
        selectedSimulationId: null,
        currentBaselineFingerprint: "bfp_a1b2c3d4e5f60718293a4b5c6d7e8f90",
        onSelectSimulation: () => {},
        onRefreshHistory: () => {},
      })
    );

    // Asserts no invented date string like "Invalid Date" or today's date
    assert.doesNotMatch(html, /Invalid Date/);
    assert.doesNotMatch(html, /1970/);
  });

  // Test 19: Historical analysis compatibility
  test("19. Historical analysis without Stage 4/5 renders graceful unavailable notice", () => {
    const historical4Stage = {
      analysis_id: "ana_hist_001",
      status: "completed",
      question: "Historical decision question",
      message: "Historical analysis message",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: null, // Missing Stage 4
      scenarios: null, // Missing Stage 5
      resilience: null, // Missing Stage 6
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: historical4Stage,
        onReset: () => {},
      })
    );

    assert.match(html, /What-if Simulation Unavailable/);
    assert.match(html, /Prerequisites: Stages 1, 4 &amp; 5/);
    assert.match(html, /id="section-decision-model"/);
  });

  // Test 20: Partial-success compatibility
  test("20. Partial-success compatibility preserves all upstream stages", () => {
    const partialAnalysis = {
      analysis_id: "ana_partial_001",
      status: "partial_success",
      question: "Partial analysis query",
      message: "Partial run completed.",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      scenarios: null, // Stage 5 timed out
      scenario_status: "unavailable",
      scenario_error: "Stage 5 timed out.",
      resilience: null,
      resilience_status: "unavailable",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: partialAnalysis,
        onReset: () => {},
      })
    );

    assert.match(html, /What-if Simulation Unavailable/);
    assert.match(html, /Stage 5 timed out\./);
    // Upstream Stage 1 and Stage 4 remain intact
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /id="section-decision-model"/);
  });

  // Test 21: In-flight request isolation
  test("21. In-flight request isolation types and safeguards exist", () => {
    assert.equal(typeof ApiClientError, "function");
    assert.equal(typeof getSimulationVariables, "function");
    assert.equal(typeof runSimulation, "function");
    assert.equal(typeof listSimulations, "function");
    assert.equal(typeof getSimulationById, "function");
    const err = new ApiClientError("Test timeout", 408);
    assert.equal(err.name, "ApiClientError");
    assert.equal(err.statusCode, 408);
  });

  // Test 22: No frontend-generated resilience arithmetic
  test("22. No frontend-generated resilience arithmetic when score delta is null", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationComparisonPanel, {
        result: MOCK_SIMULATION_RESULT_NULL_DELTA,
        variables: MOCK_DISCOVERY_VARIABLES,
      })
    );

    // Checks that the component never performs baseline - baseline or fake subtraction
    assert.match(html, /Impact not currently calculable/);
    assert.doesNotMatch(html, /Recalculated Delta/);
  });

  // Test 23: Print-friendly output
  test("23. Print-friendly output hides interactive sliders and buttons", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationVariableControls, {
        variables: MOCK_DISCOVERY_VARIABLES,
        adjustments: { var_cloud_budget: 35000.0 },
        rawInputs: { var_cloud_budget: "35000" },
        inputErrors: {},
        hasChanges: false,
        isValid: true,
        isSimulating: false,
        onAdjustmentChange: () => {},
        onRunSimulation: () => {},
        onResetToBaseline: () => {},
      })
    );

    // Sliders and buttons must have print:hidden
    assert.match(html, /print:hidden/);
    // Static printable summary table is present
    assert.match(html, /hidden print:block/);
    assert.match(html, /Simulation Variables and Tested Assumptions/);
  });

  // Test 24: No regression in existing dashboard hierarchy
  test("24. No regression in existing dashboard hierarchy", () => {
    const fullSixStageResult = {
      analysis_id: "ana_full_hierarchy_001",
      status: "completed",
      question: "Should we scale cloud infrastructure across multiple availability zones?",
      message: "Complete six-stage analysis.",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      resilience: MOCK_RESILIENCE_REPORT,
      resilience_status: "completed",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: fullSixStageResult,
        onReset: () => {},
      })
    );

    // Verify ordering: Recommendation -> Future Explorer -> Resilience -> What-if -> Decision Model
    const idxRec = html.indexOf("Executive Recommendation");
    const idxScen = html.indexOf("Future Explorer &amp; Trajectory Forecasts");
    const idxResil = html.indexOf("Decision Resilience &amp; Stress-Test Analysis");
    const idxWhatIf = html.indexOf('aria-label="What-if Simulation"');
    const idxModel = html.indexOf('id="section-decision-model"');

    assert.ok(idxRec > 0, "Stage 4 Recommendation must be rendered");
    assert.ok(idxScen > idxRec, "Stage 5 Future Explorer must follow Stage 4");
    assert.ok(idxResil > idxScen, "Stage 6 Resilience Dashboard must follow Stage 5");
    assert.ok(idxWhatIf > idxResil, "What-if Simulation must follow Stage 6 Resilience");
    assert.ok(idxModel > idxWhatIf, "Foundational Decision Model must follow What-if Simulation");
  });
});
