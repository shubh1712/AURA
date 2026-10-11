import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components and helpers built for Phase 6C (Resilience Dashboard UI)
import { ResilienceDashboard } from "../src/components/decision/resilience/ResilienceDashboard.tsx";
import { ResilienceScoreGauge } from "../src/components/decision/resilience/ResilienceScoreGauge.tsx";
import { ResiliencePillarBreakdown } from "../src/components/decision/resilience/ResiliencePillarBreakdown.tsx";
import { ResilienceVulnerabilityPanel } from "../src/components/decision/resilience/ResilienceVulnerabilityPanel.tsx";
import { ResilienceHedgeActions } from "../src/components/decision/resilience/ResilienceHedgeActions.tsx";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import {
  getRatingMetadata,
  normalizeSubScores,
} from "../src/lib/resilienceHelpers.ts";

// ------------------------------------------------------------------------------
// Comprehensive Typed Test Fixtures matching backend schemas
// ------------------------------------------------------------------------------

const MOCK_DECISION_MODEL = {
  id: "dec_model_phase6c",
  decision: {
    raw_prompt: "Should we migrate from monolithic PostgreSQL to distributed CockroachDB?",
    summary: "Architecture choice for horizontal scalability vs operational complexity.",
    decision_type: "architecture_technology",
    time_horizon: "medium_term",
  },
  complexity: {
    level: "high",
    reasoning: "Distributed consensus and transactional guarantees across regions.",
    reversibility: "partially_reversible",
    score: 65.0,
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
  id: "rec_phase6c_01",
  decision_model_id: "dec_model_phase6c",
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
  alternative_options: [],
  supporting_evidence_item_ids: [],
  tested_assumption_ids: [],
  addressed_gap_ids: [],
  reconciled_disagreement_ids: [],
  created_at: "2026-10-11T12:00:00Z",
};

const MOCK_SCENARIO_SET = {
  id: "scenset_phase6c_01",
  decision_model_id: "dec_model_phase6c",
  recommendation_id: "rec_phase6c_01",
  summary: "Simulated optimistic, base-case, and pessimistic operational trajectories.",
  scenarios: [
    {
      id: "scen_opt_01",
      scenario_type: "optimistic",
      probability: 0.25,
      name: "Rapid Scalability",
      narrative: "Smooth adoption and linear scaling.",
      key_events: [],
      risks: [],
      opportunities: ["Zero bottlenecks"],
      timeline: [],
    },
    {
      id: "scen_base_01",
      scenario_type: "base_case",
      probability: 0.50,
      name: "Controlled Migration",
      narrative: "Standard operational transition.",
      key_events: [],
      risks: ["Cadence friction"],
      opportunities: [],
      timeline: [],
    },
    {
      id: "scen_pess_01",
      scenario_type: "pessimistic",
      probability: 0.25,
      name: "WAN Latency Spike",
      narrative: "Cross-region network partition increases write latency.",
      key_events: [],
      risks: ["Latency degradation"],
      opportunities: [],
      timeline: [],
    },
  ],
};

const MOCK_RESILIENCE_REPORT = {
  id: "res_a1b2c3d4e5f60718293a4b5c6d7e8f90",
  decision_model_id: "dec_model_phase6c",
  scenario_set_id: "scenset_phase6c_01",
  recommendation_id: "rec_phase6c_01",
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

// ------------------------------------------------------------------------------
// Test Suite
// ------------------------------------------------------------------------------

describe("Phase 6C: Resilience Dashboard UI", () => {
  // Test 1: Overall score formatting & gauge
  test("1. Overall score formatting renders clean values, gauge markup, and disclaimer", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceScoreGauge, {
        score: 78.5,
        rating: "moderate",
        stressTestPassed: true,
        calculationVersion: "1.0.0",
        reportId: "res_a1b2c3d4e5f60718293a4b5c6d7e8f90",
      })
    );

    // Score display
    assert.match(html, /78\.5/);
    assert.match(html, /\/ 100/);

    // SVG Circular progressbar accessibility
    assert.match(html, /role="progressbar"/);
    assert.match(html, /aria-valuenow="78\.5"/);
    assert.match(html, /aria-valuemin="0"/);
    assert.match(html, /aria-valuemax="100"/);

    // Calculation version
    assert.match(html, /Algorithm v1\.0\.0/);

    // Mandatory deterministic disclaimer
    assert.match(html, /Resilience is a deterministic heuristic score, not the probability of decision success\./);
  });

  // Test 2: Rating display across all four canonical bands
  test("2. Rating display correctly represents all four canonical rating bands", () => {
    const bands = [
      { score: 85.0, rating: "high", label: "High Robustness", bandText: "80–100" },
      { score: 72.0, rating: "moderate", label: "Moderate Robustness", bandText: "60–<80" },
      { score: 48.0, rating: "fragile", label: "Fragile", bandText: "40–<60" },
      { score: 25.0, rating: "vulnerable", label: "Vulnerable", bandText: "Below 40" },
    ];

    for (const b of bands) {
      const meta = getRatingMetadata(b.rating);
      assert.equal(meta.rating, b.rating);
      assert.equal(meta.label, b.label);
      assert.equal(meta.rangeText, b.bandText);

      const html = renderToStaticMarkup(
        React.createElement(ResilienceScoreGauge, {
          score: b.score,
          rating: b.rating,
          stressTestPassed: b.score >= 60,
        })
      );

      assert.match(html, new RegExp(b.label));
      const expectedBandRegex = new RegExp(`Band: ${b.bandText.replace('<', '(&lt;|<)')}`);
      assert.match(html, expectedBandRegex);
    }
  });

  // Test 3: Four-pillar breakdown ordering and values
  test("3. Four-pillar ordering and values are canonically sorted and displayed with progress bars", () => {
    // Pass shuffled sub_scores to verify canonical re-ordering
    const shuffledSubScores = [
      MOCK_RESILIENCE_REPORT.sub_scores[3], // Information Robustness
      MOCK_RESILIENCE_REPORT.sub_scores[0], // Constraint Boundary Tolerance
      MOCK_RESILIENCE_REPORT.sub_scores[2], // Contingency Coverage
      MOCK_RESILIENCE_REPORT.sub_scores[1], // Pessimistic Survivability
    ];

    const html = renderToStaticMarkup(
      React.createElement(ResiliencePillarBreakdown, {
        subScores: shuffledSubScores,
      })
    );

    // All four canonical pillar titles present
    assert.match(html, /Constraint Boundary Tolerance/);
    assert.match(html, /Pessimistic Scenario Survivability/);
    assert.match(html, /Contingency &amp; Fallback Coverage/);
    assert.match(html, /Information Robustness/);

    // Verify canonical order: Pillar 1, Pillar 2, Pillar 3, Pillar 4 in sequence
    const idxPillar1 = html.indexOf("Pillar 1");
    const idxPillar2 = html.indexOf("Pillar 2");
    const idxPillar3 = html.indexOf("Pillar 3");
    const idxPillar4 = html.indexOf("Pillar 4");

    assert.ok(idxPillar1 < idxPillar2, "Pillar 1 must precede Pillar 2");
    assert.ok(idxPillar2 < idxPillar3, "Pillar 2 must precede Pillar 3");
    assert.ok(idxPillar3 < idxPillar4, "Pillar 3 must precede Pillar 4");

    // Pillar scores and ceilings
    assert.match(html, /21 \/ 25 pts/);
    assert.match(html, /18\.5 \/ 25 pts/);
    assert.match(html, /20 \/ 25 pts/);
    assert.match(html, /19 \/ 25 pts/);
  });

  // Test 4: Rationale and vulnerability rendering in pillars
  test("4. Rationale and vulnerability rendering shows explainable breakdown and findings", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResiliencePillarBreakdown, {
        subScores: MOCK_RESILIENCE_REPORT.sub_scores,
      })
    );

    // Rationale strings
    assert.match(html, /Partially reversible decision with 35% cost buffer under budget constraint\./);
    assert.match(html, /Pessimistic scenario mitigated by pre-configured shadow cluster cutback\./);

    // Specific pillar vulnerabilities
    assert.match(html, /Hard latency ceiling at 15ms leaves little headroom under cross-region failover\./);
    assert.match(html, /One untested operational assumption regarding SRE team cross-training\./);

    // Empty vulnerability pillar note
    assert.match(html, /No structural vulnerabilities identified in this pillar\./);
  });

  // Test 5: Stress-test status pass/fail rendering
  test("5. Stress-test pass/fail renders authoritative status and threshold explanation", () => {
    // Passed case
    const htmlPassed = renderToStaticMarkup(
      React.createElement(ResilienceScoreGauge, {
        score: 78.5,
        rating: "moderate",
        stressTestPassed: true,
      })
    );
    assert.match(htmlPassed, /Heuristic stress threshold met/);
    assert.match(htmlPassed, /Stress Test Met/);
    assert.match(htmlPassed, /overall score &gt;= 60\.0 and pessimistic survivability &gt;= 12\.5 \/ 25\.0/);

    // Failed case
    const htmlFailed = renderToStaticMarkup(
      React.createElement(ResilienceScoreGauge, {
        score: 45.0,
        rating: "fragile",
        stressTestPassed: false,
      })
    );
    assert.match(htmlFailed, /Heuristic stress threshold not met/);
    assert.match(htmlFailed, /Stress Threshold Not Met/);
    assert.doesNotMatch(htmlFailed, /Heuristic stress threshold met</);
  });

  // Test 6: Critical vulnerabilities panel
  test("6. Critical vulnerabilities renders prioritized list, deduplicates, and handles empty state", () => {
    // With vulnerabilities including a duplicate
    const vulnsWithDuplicate = [
      "Hard latency ceiling at 15ms leaves little headroom under cross-region failover.",
      "Downside partition risk requires automated failback tooling.",
      "Hard latency ceiling at 15ms leaves little headroom under cross-region failover.", // duplicate
    ];

    const html = renderToStaticMarkup(
      React.createElement(ResilienceVulnerabilityPanel, {
        criticalVulnerabilities: vulnsWithDuplicate,
      })
    );

    assert.match(html, /Critical Structural Vulnerabilities/);
    assert.match(html, /2 Identified/); // Deduplicated to 2
    assert.match(html, /VULN-01/);
    assert.match(html, /VULN-02/);
    assert.doesNotMatch(html, /VULN-03/);
    assert.match(html, /Hard latency ceiling at 15ms/);

    // Empty state
    const htmlEmpty = renderToStaticMarkup(
      React.createElement(ResilienceVulnerabilityPanel, {
        criticalVulnerabilities: [],
      })
    );
    assert.match(htmlEmpty, /0 Vulnerabilities/);
    assert.match(htmlEmpty, /No Critical Vulnerabilities Detected/);
  });

  // Test 7: Recommended hedges actionable items
  test("7. Recommended hedges distinguishes from Stage 4 actions and displays actionable items", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceHedgeActions, {
        recommendedHedges: MOCK_RESILIENCE_REPORT.recommended_hedges,
        recommendationActionCount: 3,
      })
    );

    assert.match(html, /Recommended Resilience Hedges/);
    assert.match(html, /3 Hedges Suggested/);
    assert.match(html, /Distinction from Baseline Recommendation Actions:/);
    assert.match(html, /complement the 3 primary execution actions in Stage 4/);
    assert.match(html, /HEDGE-01/);
    assert.match(html, /HEDGE-02/);
    assert.match(html, /HEDGE-03/);
    assert.match(html, /Suggested Action/);

    // Verify it NEVER labels hedges as verified or completed
    assert.doesNotMatch(html, /Action Completed/);
    assert.doesNotMatch(html, /Action Verified/);
  });

  // Test 8: Unavailable resilience state banner and artifact preservation
  test("8. Unavailable resilience state renders graceful notice and preserves Stages 1-5", () => {
    const partialResilienceResult = {
      analysis_id: "ana_resil_fail_123",
      status: "partial_success",
      question: "Should we migrate to CockroachDB?",
      message: "Stages 1-5 completed; Stage 6 unavailable.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: null,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      recommendation_error: null,
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      scenario_error: null,
      resilience: null,
      resilience_status: "unavailable",
      resilience_error: "Stage 6 resilience evaluation skipped: global analysis deadline expired.",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: partialResilienceResult,
        onReset: () => {},
      })
    );

    // Partial analysis notice in header
    assert.match(html, /Partial Analysis Complete/);
    assert.match(html, /partial_success/);

    // Resilience unavailable banner
    assert.match(html, /Stage 6: Decision Resilience Evaluation Unavailable/);
    assert.match(html, /Stage 6 resilience evaluation skipped: global analysis deadline expired\./);
    assert.match(html, /Decision Foundation \(Stages 1–5\) Intact/);

    // Upstream artifacts remain fully rendered!
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /Future Explorer &amp; Trajectory Forecasts/);
    assert.match(html, /id="section-decision-model"/);
  });

  // Test 9: Historical responses without resilience fields render smoothly
  test("9. Historical 5-stage and 4-stage responses render without resilience errors", () => {
    const historicalResult = {
      analysis_id: "ana_hist_5stage_123",
      status: "completed",
      question: "Should we migrate to CockroachDB?",
      message: "Five-stage analysis completed.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: null,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      recommendation_error: null,
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      scenario_error: null,
      // Resilience fields omitted entirely (historical response)
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: historicalResult,
        onReset: () => {},
      })
    );

    // Complete status
    assert.match(html, /Analysis Complete/);
    assert.match(html, /completed/);

    // No resilience error or broken state
    assert.doesNotMatch(html, /Stage 6: Decision Resilience Evaluation Unavailable/);
    assert.doesNotMatch(html, /Inconsistent Resilience State/);

    // Recommendation and Scenarios render smoothly
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /Future Explorer &amp; Trajectory Forecasts/);
  });

  // Test 10: Inconsistent and malformed optional data handled defensively
  test("10. Malformed or inconsistent optional data is handled defensively without crashing", () => {
    // Case 1: Inconsistent state (status completed but resilience payload null)
    const inconsistentResult = {
      analysis_id: "ana_inconsistent_resil",
      status: "completed",
      question: "Should we migrate to CockroachDB?",
      message: "Analysis completed.",
      decision_model: MOCK_DECISION_MODEL,
      recommendation: MOCK_RECOMMENDATION,
      scenarios: MOCK_SCENARIO_SET,
      resilience: null,
      resilience_status: "completed",
    };

    const htmlInconsistent = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: inconsistentResult,
        onReset: () => {},
      })
    );

    assert.match(htmlInconsistent, /Inconsistent Resilience State Detected/);

    // Case 2: Mapping / Dictionary structure instead of array for sub_scores
    const dictionarySubScores = {
      constraint_boundary_tolerance: {
        score: 22,
        rationale: "Dictionary constraint breakdown",
      },
      pessimistic_scenario_survivability: {
        score: 16,
        rationale: "Dictionary pessimistic breakdown",
      },
    };

    const normalized = normalizeSubScores(dictionarySubScores);
    assert.equal(normalized.length, 4);
    assert.equal(normalized[0].score, 22);
    assert.equal(normalized[1].score, 16);
  });

  // Test 11: Full ResilienceDashboard component integration
  test("11. ResilienceDashboard renders complete gauge, pillars, vulnerabilities, and hedges", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceDashboard, {
        report: MOCK_RESILIENCE_REPORT,
        decisionModel: MOCK_DECISION_MODEL,
        recommendation: MOCK_RECOMMENDATION,
        scenarioSet: MOCK_SCENARIO_SET,
        decisionTitle: "Evaluate migrating to CockroachDB",
      })
    );

    // Header
    assert.match(html, /Stage 6: Resilience Engine/);
    assert.match(html, /Decision Resilience &amp; Stress-Test Analysis/);
    assert.match(html, /Moderate Robustness/);
    assert.match(html, /Stress Test Met/);
    assert.match(html, /Decision Context:.*Evaluate migrating to CockroachDB/);

    // Sections
    assert.match(html, /Composite Decision Resilience Score/);
    assert.match(html, /Four Canonical Resilience Pillars/);
    assert.match(html, /Critical Structural Vulnerabilities/);
    assert.match(html, /Recommended Resilience Hedges/);
  });

  // Test 12: Print/PDF styling compatibility
  test("12. Print/PDF export compatibility provides print classes and avoids page break clipping", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceDashboard, {
        report: MOCK_RESILIENCE_REPORT,
      })
    );

    assert.match(html, /print:bg-white/);
    assert.match(html, /print:border-zinc-300/);
    assert.match(html, /print:text-black/);
    assert.match(html, /print:space-y-6/);
  });

  // Test 13: AnalysisResultCard six-stage integration harmony
  test("13. AnalysisResultCard integrates all 6 stages harmoniously in full complete state", () => {
    const fullSixStageResult = {
      analysis_id: "ana_six_stage_full",
      status: "completed",
      question: "Should we migrate to CockroachDB?",
      message: "Six-stage analysis completed successfully.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: null,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      recommendation_error: null,
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      scenario_error: null,
      resilience: MOCK_RESILIENCE_REPORT,
      resilience_status: "completed",
      resilience_error: null,
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: fullSixStageResult,
        onReset: () => {},
      })
    );

    // Header
    assert.match(html, /Analysis Complete/);
    assert.match(html, /completed/);

    // Stages 4, 5, and 6 all present in exact order
    const idxRec = html.indexOf("Executive Recommendation");
    const idxScen = html.indexOf("Future Explorer &amp; Trajectory Forecasts");
    const idxResil = html.indexOf("Decision Resilience &amp; Stress-Test Analysis");

    assert.ok(idxRec > 0, "Stage 4 Recommendation must be rendered");
    assert.ok(idxScen > idxRec, "Stage 5 Future Explorer must follow Stage 4");
    assert.ok(idxResil > idxScen, "Stage 6 Resilience Dashboard must follow Stage 5");
  });
});
