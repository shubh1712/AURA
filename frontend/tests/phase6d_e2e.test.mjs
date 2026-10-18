/**
 * Phase 6D End-to-End Frontend Integration Verification Test Suite.
 *
 * Comprehensive component integration and lifecycle verification for all 6 analysis stages:
 * 1. Stage 1: Decision Framer
 * 2. Stage 2: Evidence Package
 * 3. Stage 3: AI Boardroom
 * 4. Stage 4: Recommendation Engine
 * 5. Stage 5: Scenario Generator (3 canonical future trajectories)
 * 6. Stage 6: Deterministic Resilience Engine (0–100 score, 4 pillars, stress test)
 *
 * Verifies:
 * - Complete 6-stage rendering sequence and anchor landmarks
 * - Three-branch scenario tree & scenario detail inspection
 * - Resilience score, rating, 4 pillars, and authoritative stress-test flag
 * - Critical vulnerabilities and resilience hedges
 * - Historical backwards compatibility (4-stage and 5-stage)
 * - Partial-success banners and upstream preservation
 * - Print/PDF export layout, styling, and static fallbacks
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import { FutureExplorerTree } from "../src/components/decision/scenario/FutureExplorerTree.tsx";
import { ScenarioDetailPanel } from "../src/components/decision/scenario/ScenarioDetailPanel.tsx";
import { ResilienceDashboard } from "../src/components/decision/resilience/ResilienceDashboard.tsx";
import { ResilienceScoreGauge } from "../src/components/decision/resilience/ResilienceScoreGauge.tsx";
import { ResiliencePillarBreakdown } from "../src/components/decision/resilience/ResiliencePillarBreakdown.tsx";

// -----------------------------------------------------------------------------
// Mock Data Fixtures
// -----------------------------------------------------------------------------

const MOCK_DECISION_MODEL = {
  id: "dec_e2e_verify_001",
  decision: {
    raw_prompt: "Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
    summary: "Architecture choice for horizontal scalability vs operational complexity.",
    decision_type: "architecture_technology",
    time_horizon: "medium_term",
  },
  complexity: {
    level: "high",
    reasoning: "Distributed consensus and transactional guarantees across regions.",
    reversibility: "partially_reversible",
  },
  objectives: [
    {
      id: "obj_perf",
      description: "Support 50,000 writes/sec p99 under 15ms",
      is_primary: true,
      target_metric: "50,000 writes/sec",
      provenance: "user_provided",
    },
  ],
  variables: [],
  constraints: [
    {
      id: "cons_budget",
      name: "Infra Budget",
      description: "Monthly infra budget cap $35,000",
      is_hard_constraint: true,
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
  id: "rec_e2e_verify_001",
  decision_model_id: "dec_e2e_verify_001",
  decision_status: "conditional_go",
  summary: "Execute a 60-day phased pilot migration to CockroachDB with strict failback gates.",
  recommended_action: "Execute a 60-day phased pilot migration to CockroachDB with strict failback gates.",
  executive_summary: "Phased pilot migration to CockroachDB with strict failback gates.",
  primary_rationale: "Deliberation established strong consensus on write-throughput scaling.",
  decision_readiness: "actionable",
  evidence_strength: "moderate",
  recommendation_stability: "stable",
  key_reasons: ["Meets write throughput scaling goals."],
  tradeoffs_accepted: ["Operational complexity for write scalability."],
  uncertainty_assessment: {
    evidence_strength: "moderate",
    decision_readiness: "actionable",
    recommendation_stability: "stable",
    critical_vulnerabilities: [],
    epistemic_caveats: [],
  },
  action_plan: {
    overview: "Three-phase execution strategy.",
    actions: [
      {
        id: "act_01",
        title: "Pilot Dual-Writing",
        description: "Mirror writes to shadow cluster.",
        priority: "immediate",
        time_horizon: "immediate",
        decision_gates: [],
      },
    ],
    total_actions: 1,
    hard_gate_count: 0,
  },
  contingencies: [],
  alternative_options: [],
  supporting_evidence_item_ids: [],
  tested_assumption_ids: [],
  addressed_gap_ids: [],
  reconciled_disagreement_ids: [],
  created_at: "2026-10-11T12:00:00Z",
};

const MOCK_SCENARIO_SET = {
  id: "scenset_e2e_verify_001",
  decision_model_id: "dec_e2e_verify_001",
  recommendation_id: "rec_e2e_verify_001",
  summary: "Simulated optimistic, base-case, and pessimistic operational trajectories.",
  scenarios: [
    {
      id: "scen_opt_01",
      scenario_type: "optimistic",
      probability: 0.25,
      name: "Accelerated Multi-Region Expansion",
      narrative: "Canary rollout executes smoothly; transaction routing auto-balances within 8ms with zero downtime.",
      key_events: [
        {
          id: "ke_opt_1",
          title: "Secondary Region Parity",
          description: "Secondary region passes all compliance and latency gates.",
          timeframe: "Month 1",
          trigger_condition: "All tests green",
          impact_on_decision: "Accelerates general production deployment",
        },
      ],
      risks: [],
      opportunities: ["Zero bottlenecks", "Sub-10ms global latency"],
      timeline: [
        {
          id: "ms_opt_1",
          title: "Shadow Traffic Certification",
          description: "Full production traffic mirrored successfully.",
          time_horizon: "immediate",
          expected_outcome: "100% data consistency verified",
        },
      ],
    },
    {
      id: "scen_base_01",
      scenario_type: "base_case",
      probability: 0.55,
      name: "Managed Phased Transition",
      narrative: "Standard operational migration across three quarters with anticipated configuration adjustments.",
      key_events: [],
      risks: ["Cadence friction"],
      opportunities: ["Predictable cost curve"],
      timeline: [],
    },
    {
      id: "scen_pess_01",
      scenario_type: "pessimistic",
      probability: 0.20,
      name: "WAN Consensus Bottleneck",
      narrative: "Cross-region network partition increases write latency beyond acceptable tolerance.",
      key_events: [
        {
          id: "ke_pess_1",
          title: "Decision Gate Failover Activated",
          description: "Transatlantic WAN commit latency breaches 25ms threshold.",
          timeframe: "Month 2",
          trigger_condition: "p99 commit latency > 25ms",
          impact_on_decision: "Triggers mandatory fallback protocol",
        },
      ],
      risks: ["Latency degradation", "Retry queue exhaustion"],
      opportunities: [],
      timeline: [
        {
          id: "ms_pess_1",
          title: "Automated Rollback Activation",
          description: "Traffic reverts to primary region.",
          time_horizon: "immediate",
          expected_outcome: "Single-region continuity sustained",
        },
      ],
    },
  ],
};

const MOCK_RESILIENCE_REPORT = {
  id: "res_a1b2c3d4e5f60718293a4b5c6d7e8f90",
  decision_model_id: "dec_e2e_verify_001",
  scenario_set_id: "scenset_e2e_verify_001",
  recommendation_id: "rec_e2e_verify_001",
  overall_score: 78.5,
  rating: "moderate",
  sub_scores: [
    {
      category: "constraint_boundary_tolerance",
      score: 21.0,
      max_score: 25.0,
      rationale: "Partially reversible decision with 35% cost buffer under budget constraint.",
      vulnerabilities_detected: ["Hard latency ceiling at 15ms leaves little headroom under cross-region failover."],
    },
    {
      category: "pessimistic_scenario_survivability",
      score: 18.5,
      max_score: 25.0,
      rationale: "Pessimistic scenario mitigated by pre-configured shadow cluster cutback.",
      vulnerabilities_detected: ["Downside partition risk requires automated failback tooling."],
    },
    {
      category: "contingency_and_fallback_coverage",
      score: 20.0,
      max_score: 25.0,
      rationale: "Two formal decision gates and explicit rollback criteria defined in pilot plan.",
      vulnerabilities_detected: [],
    },
    {
      category: "information_robustness",
      score: 19.0,
      max_score: 25.0,
      rationale: "Moderate evidence backing with low assumption falsification exposure.",
      vulnerabilities_detected: ["One untested operational assumption regarding SRE team cross-training."],
    },
  ],
  critical_vulnerabilities: [
    "Hard latency ceiling at 15ms leaves little headroom under cross-region failover.",
    "Downside partition risk requires automated failback tooling.",
  ],
  stress_test_passed: true,
  recommended_hedges: [
    "Implement automated telemetry monitoring and alert thresholds for operational constraints.",
    "Formulate pre-authorized contingency rollback procedures for unmitigated pessimistic scenario risks.",
    "Establish formal decision gates with quantitative verification criteria prior to cutover.",
  ],
  calculation_version: "1.0.0",
  created_at: "2026-10-11T12:00:00Z",
};

describe("Phase 6D: Full Six-Stage End-to-End Frontend Verification", () => {
  // Test 1: Full Six-Stage Complete Result Rendering
  test("1. AnalysisResultCard renders all six stages in exact sequential order with anchor landmarks", () => {
    const fullResult = {
      analysis_id: "ana_e2e_full_001",
      status: "completed",
      question: "Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
      message: "Six-stage analysis completed successfully.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: null,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      resilience: MOCK_RESILIENCE_REPORT,
      resilience_status: "completed",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: fullResult,
        onReset: () => {},
      })
    );

    // Verify all stage sections exist
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /Future Explorer &amp; Trajectory Forecasts/);
    assert.match(html, /id="section-future-explorer"/);
    assert.match(html, /Decision Resilience &amp; Stress-Test Analysis/);
    assert.match(html, /id="section-resilience-dashboard"/);

    // Verify strict sequential ordering in executive-first report hierarchy:
    // Executive tier: Stage 4 -> Stage 5 -> Stage 6
    const idxRec = html.indexOf("Executive Recommendation");
    const idxScen = html.indexOf("Future Explorer &amp; Trajectory Forecasts");
    const idxResil = html.indexOf("Decision Resilience &amp; Stress-Test Analysis");

    assert.ok(idxRec > 0, "Stage 4 Recommendation must be rendered");
    assert.ok(idxScen > idxRec, "Stage 5 Future Explorer must follow Stage 4");
    assert.ok(idxResil > idxScen, "Stage 6 Resilience Dashboard must follow Stage 5");

    // Foundational tier: Stage 1 Decision Model
    const idxModel = html.indexOf('id="section-decision-model"');
    assert.ok(idxModel > idxResil, "Foundational Stage 1 Decision Model must follow Executive Resilience");
  });

  // Test 2: Scenario Tree Three Canonical Branches
  test("2. FutureExplorerTree displays all three canonical branches with exact modeled probabilities", () => {
    const html = renderToStaticMarkup(
      React.createElement(FutureExplorerTree, {
        decisionTitle: "Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
        scenarios: MOCK_SCENARIO_SET.scenarios,
        selectedScenarioType: "base_case",
        onSelectScenario: () => {},
      })
    );

    // Verify root decision node
    assert.match(html, /Decision Root/);
    assert.match(html, /Stages 1–4 Deliberation Base/);

    // Verify all 3 branches
    assert.match(html, /Accelerated Multi-Region Expansion/);
    assert.match(html, /Managed Phased Transition/);
    assert.match(html, /WAN Consensus Bottleneck/);

    // Verify probability badges
    assert.match(html, /25%/);
    assert.match(html, /55%/);
    assert.match(html, /20%/);

    // Verify type tags
    assert.match(html, /OPTIMISTIC/);
    assert.match(html, /BASE CASE/);
    assert.match(html, /PESSIMISTIC/);
  });

  // Test 3: Scenario Detail Panel Rendering & Epistemic Grounding
  test("3. ScenarioDetailPanel renders narrative, triggers, milestones, and epistemic IDs", () => {
    const html = renderToStaticMarkup(
      React.createElement(ScenarioDetailPanel, {
        scenario: MOCK_SCENARIO_SET.scenarios[2], // Pessimistic
        decisionModel: MOCK_DECISION_MODEL,
        recommendation: MOCK_RECOMMENDATION,
      })
    );

    assert.match(html, /WAN Consensus Bottleneck/);
    assert.match(html, /Cross-region network partition increases write latency/);
    assert.match(html, /Decision Gate Failover Activated/);
    assert.match(html, /Automated Rollback Activation/);
    assert.match(html, /Single-region continuity sustained/);
    assert.match(html, /Modeled Probability/);
    assert.match(html, /20%/);
  });

  // Test 4: Resilience Score Gauge & Authoritative Stress-Test Verification
  test("4. ResilienceScoreGauge displays 78.5 score, Moderate rating, authoritative stress test, and disclaimer", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceScoreGauge, {
        score: MOCK_RESILIENCE_REPORT.overall_score,
        rating: MOCK_RESILIENCE_REPORT.rating,
        stressTestPassed: MOCK_RESILIENCE_REPORT.stress_test_passed,
        calculationVersion: MOCK_RESILIENCE_REPORT.calculation_version,
        reportId: MOCK_RESILIENCE_REPORT.id,
      })
    );

    // Numerical score
    assert.match(html, /78\.5/);
    assert.match(html, /\/ 100/);

    // Rating metadata
    assert.match(html, /Moderate Robustness/);

    // Authoritative stress-test result
    assert.match(html, /Heuristic stress threshold met/);
    assert.match(html, /Stress Test Met/);

    // Version
    assert.match(html, /Algorithm v1\.0\.0/);

    // Non-probability disclaimer
    assert.match(html, /Resilience is a deterministic heuristic score, not the probability of decision success\./);
  });

  // Test 5: Four Pillar Scores Match Backend Response
  test("5. ResiliencePillarBreakdown renders 4 canonical pillars matching exact backend sub-scores", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResiliencePillarBreakdown, {
        subScores: MOCK_RESILIENCE_REPORT.sub_scores,
      })
    );

    assert.match(html, /Constraint Boundary Tolerance/);
    assert.match(html, /21 \/ 25 pts/);

    assert.match(html, /Pessimistic Scenario Survivability/);
    assert.match(html, /18\.5 \/ 25 pts/);

    assert.match(html, /Contingency &amp; Fallback Coverage/);
    assert.match(html, /20 \/ 25 pts/);

    assert.match(html, /Information Robustness/);
    assert.match(html, /19 \/ 25 pts/);

    // Verify total pillar ceiling
    assert.match(html, /Max Total: 100\.0 Pts/);
  });

  // Test 6: Critical Vulnerabilities and Recommended Hedges
  test("6. ResilienceDashboard renders critical vulnerabilities and recommended resilience hedges", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceDashboard, {
        report: MOCK_RESILIENCE_REPORT,
        decisionModel: MOCK_DECISION_MODEL,
        recommendation: MOCK_RECOMMENDATION,
        scenarioSet: MOCK_SCENARIO_SET,
      })
    );

    // Vulnerabilities
    assert.match(html, /Critical Structural Vulnerabilities/);
    assert.match(html, /Hard latency ceiling at 15ms leaves little headroom under cross-region failover\./);
    assert.match(html, /Downside partition risk requires automated failback tooling\./);
    assert.match(html, /VULN-01/);
    assert.match(html, /VULN-02/);

    // Hedges
    assert.match(html, /Recommended Resilience Hedges/);
    assert.match(html, /Implement automated telemetry monitoring/);
    assert.match(html, /Formulate pre-authorized contingency rollback procedures/);
    assert.match(html, /HEDGE-01/);
    assert.match(html, /HEDGE-02/);
  });

  // Test 7: Historical 4-stage and 5-stage Compatibility
  test("7. Historical 4-stage and 5-stage responses render cleanly without errors", () => {
    // 4-stage legacy response
    const legacy4Stage = {
      analysis_id: "ana_legacy_4",
      status: "completed",
      question: "Historical 4-stage query",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
    };

    const html4 = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: legacy4Stage,
        onReset: () => {},
      })
    );
    assert.match(html4, /Executive Recommendation/);
    assert.doesNotMatch(html4, /id="section-future-explorer"/);
    assert.doesNotMatch(html4, /id="section-resilience-dashboard"/);

    // 5-stage legacy response
    const legacy5Stage = {
      analysis_id: "ana_legacy_5",
      status: "completed",
      question: "Historical 5-stage query",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
    };

    const html5 = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: legacy5Stage,
        onReset: () => {},
      })
    );
    assert.match(html5, /Executive Recommendation/);
    assert.match(html5, /id="section-future-explorer"/);
    assert.doesNotMatch(html5, /id="section-resilience-dashboard"/);
  });

  // Test 8: Partial-Success Banners and Upstream Preservation
  test("8. Partial success renders appropriate banner and preserves all upstream stages", () => {
    // Case: Stage 6 timed out, Stages 1-5 completed
    const partialStage6 = {
      analysis_id: "ana_part_s6",
      status: "partial_success",
      question: "Multi-region migration inquiry",
      message: "Stages 1-5 completed; Stage 6 unavailable.",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      resilience: null,
      resilience_status: "unavailable",
      resilience_error: "Stage 6 resilience evaluation skipped: global analysis deadline expired.",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: partialStage6,
        onReset: () => {},
      })
    );

    // Header indicates partial success
    assert.match(html, /Partial Analysis Complete/);

    // Stage 6 banner displayed
    assert.match(html, /Stage 6: Decision Resilience Evaluation Unavailable/);
    assert.match(html, /global analysis deadline expired/);

    // Upstream stages 1, 4, 5 completely intact
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /id="section-future-explorer"/);
  });

  // Test 9: Print and PDF Export Classes
  test("9. Print/PDF styling compatibility across all six stages avoids page-break clipping", () => {
    const fullResult = {
      analysis_id: "ana_e2e_full_print",
      status: "completed",
      question: "Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
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
        result: fullResult,
        onReset: () => {},
      })
    );

    // Print utility classes in place
    assert.match(html, /print:bg-white/);
    assert.match(html, /print:text-black/);
    assert.match(html, /print:border-zinc-300/);
    assert.match(html, /print:hidden/); // interactive-only buttons hidden in print
  });
});
