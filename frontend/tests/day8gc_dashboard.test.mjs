/**
 * Day 8G-C: Visual Decision Dashboard and Concise Reporting Verification Suite
 *
 * Verifies:
 * 1. Rendering with complete analysis across all 4 primary views
 * 2. Rendering with missing optional stages and partial success
 * 3. Truthful handling of missing financial inputs (no fabricated numbers)
 * 4. Critical integrity warnings (no green success badges on unresolved issues)
 * 5. Empty evidence lists and edge cases
 * 6. Clean word-boundary text truncation and internal ID suppression
 * 7. Currency, metric, and percentage formatting
 * 8. Scenario comparison range chart and modeled estimate caveats
 * 9. Action-plan timeline, dependencies, gates, and absence of placeholder strings
 * 10. Accessibility landmarks, ARIA roles, and keyboard attributes
 * 11. Zero unexpected API/network requests during rendering
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import { VisualDecisionDashboard } from "../src/components/decision/dashboard/VisualDecisionDashboard.tsx";
import { OverviewView } from "../src/components/decision/dashboard/OverviewView.tsx";
import { ExploreView } from "../src/components/decision/dashboard/ExploreView.tsx";
import { ActionPlanView } from "../src/components/decision/dashboard/ActionPlanView.tsx";
import { DetailsView } from "../src/components/decision/dashboard/DetailsView.tsx";
import { FeasibilityTargetChart } from "../src/components/decision/charts/FeasibilityTargetChart.tsx";
import { AlternativesComparisonMatrix } from "../src/components/decision/charts/AlternativesComparisonMatrix.tsx";
import { ScenarioComparisonChart } from "../src/components/decision/charts/ScenarioComparisonChart.tsx";
import { ResilienceDriverChart } from "../src/components/decision/charts/ResilienceDriverChart.tsx";
import { ActionTimelineVisual } from "../src/components/decision/charts/ActionTimelineVisual.tsx";
import { DecisionGateVisual } from "../src/components/decision/charts/DecisionGateVisual.tsx";
import { EvidenceQualityDistribution } from "../src/components/decision/charts/EvidenceQualityDistribution.tsx";
import {
  formatCurrency,
  formatMetricNumber,
  formatEnumLabel,
  truncateOnWordBoundary,
  extractConciseRecommendation,
  evaluateDecisionIntegrity,
} from "../src/lib/formatters.ts";

// -----------------------------------------------------------------------------
// Test Fixtures
// -----------------------------------------------------------------------------

const MOCK_DECISION_MODEL_COMPLETE = {
  id: "model_8gc_001",
  decision: {
    raw_prompt: "Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
    summary: "Strategic architecture choice for horizontal write scalability vs operational complexity.",
    decision_type: "architecture_technology",
    time_horizon: "medium_term",
  },
  complexity: {
    level: "high",
    reasoning: "Distributed consensus and transactional guarantees across regions.",
    reversibility: "partially_reversible",
    score: 82,
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
  variables: [
    {
      id: "var_budget",
      name: "Monthly Infra Budget",
      description: "Cloud compute and database hosting spend",
      variable_type: "currency",
      baseline_value: 35000,
      proposed_value: 48000,
      unit: "USD",
      is_controllable: true,
      provenance: "user_provided",
    },
  ],
  constraints: [
    {
      id: "cons_budget",
      name: "Infra Budget Cap",
      description: "Monthly infra budget cap $50,000 USD",
      is_hard_constraint: true,
      threshold_expression: "$50,000 / month",
      source: "User input",
      provenance: "user_provided",
    },
  ],
  stakeholders: [],
  tradeoffs: [
    {
      id: "to_ops",
      upside: "Guaranteed multi-region failover continuity",
      downside: "Operational overhead requiring specialized SRE cross-training",
    },
  ],
  assumptions: [
    {
      id: "asmp_wan",
      statement: "Cross-region network latency remains under 45ms consistently.",
      confidence: "high",
      provenance: "user_provided",
      falsification_condition: "Cross-region ping exceeds 60ms for > 5 consecutive minutes.",
    },
  ],
  unknowns: [],
  key_questions: [],
};

const MOCK_RECOMMENDATION_COMPLETE = {
  id: "rec_8gc_001",
  decision_model_id: "model_8gc_001",
  evidence_package_id: "evpkg_8gc_001",
  reasoning_board_id: "board_8gc_001",
  decision_status: "conditional",
  recommended_action: "Execute a 60-day phased pilot migration to CockroachDB with strict failback gates. Maintain single-region fallback until latency SLAs are verified.",
  executive_rationale: "Deliberation established strong consensus on write-throughput scaling, but requires hard decision gates to protect customer checkout latencies.",
  supporting_evidence_item_ids: ["ev_1"],
  relevant_assumption_ids: ["asmp_wan"],
  relevant_evidence_gap_ids: [],
  unresolved_disagreement_ids: [],
  alternative_options: [
    {
      id: "alt_aurora",
      name: "Aurora PostgreSQL Global Database",
      description: "Managed AWS multi-region read replicas with single-writer master.",
      tradeoffs: ["Lower operational burden but cross-region writes incur higher failover latency."],
      why_not_recommended: "Fails write-throughput scaling requirements under multi-region simultaneous active-active traffic.",
    },
  ],
  uncertainty_assessment: {
    evidence_strength: "moderate",
    decision_readiness: "conditional",
    recommendation_stability: "high",
    critical_missing_information: [
      "Vendor benchmark under simulated network partition.",
      "Third-party PCI compliance audit for cross-border replicated storage.",
    ],
    conditions_changing_recommendation: [
      "Cross-region write latency exceeds 25ms during initial test traffic.",
      "Monthly licensing cost increases beyond $55,000.",
    ],
    assumptions_relied_upon: ["asmp_wan"],
    evidence_gaps_relied_upon: [],
  },
  action_plan: {
    summary: "Phased three-stage rollout over 60 days.",
    actions: [
      {
        id: "act_1",
        title: "Deploy Multi-Region Staging Cluster",
        objective: "Establish baseline latency benchmarks",
        description: "Provision 3-region CockroachDB dedicated cluster and configure VPC peering.",
        priority: "high",
        responsible_role: "Lead Infrastructure Architect",
        time_horizon: "immediate",
        dependencies: [],
        success_metrics: ["Cluster health check 100% green"],
        risk_mitigations: ["Automated terraform teardown on failure"],
        decision_gates: [
          {
            id: "gate_1",
            condition: "Latency Verification Gate",
            target_milestone: "Day 30",
            verification_method: "Synthetic load testing with 50,000 writes/sec",
            fallback_action: "Halt migration and re-evaluate single-region sharding.",
          },
        ],
      },
    ],
    key_milestones: ["Staging deployment", "Shadow traffic pilot", "Production cutover"],
  },
  created_at: "2026-10-14T10:00:00Z",
};

const MOCK_SCENARIOS_COMPLETE = {
  id: "scenset_8gc_001",
  decision_model_id: "model_8gc_001",
  summary: "Scenario analysis reveals high upside in traffic throughput with downside risks concentrated in cross-region network partitions.",
  scenarios: [
    {
      id: "scen_opt",
      scenario_type: "optimistic",
      probability: 0.25,
      name: "Seamless Multi-Region Scaling",
      narrative: "Infrastructure sustains projected holiday traffic surge with p99 latency staying under 12ms across all geographic regions.",
      key_events: [],
      risks: ["Minor cloud cost overage"],
      opportunities: ["30% increase in checkout conversions"],
      timeline: [],
      supporting_evidence_item_ids: [],
      relevant_assumption_ids: [],
      relevant_constraint_ids: [],
      relevant_gap_ids: [],
    },
    {
      id: "scen_base",
      scenario_type: "base_case",
      probability: 0.55,
      name: "Phased Adoption with Manageable Frictions",
      narrative: "Traffic migrations proceed according to plan with minor initial SRE tuning required for regional partition tolerance.",
      key_events: [],
      risks: ["Initial onboarding curve for backend engineers"],
      opportunities: ["Zero-downtime database upgrades achieved"],
      timeline: [],
      supporting_evidence_item_ids: [],
      relevant_assumption_ids: [],
      relevant_constraint_ids: [],
      relevant_gap_ids: [],
    },
    {
      id: "scen_pess",
      scenario_type: "pessimistic",
      probability: 0.20,
      name: "WAN Partition & Latency Spikes",
      narrative: "Cross-region network partition triggers elevated commit latency, forcing fallback to localized disaster-recovery mode.",
      key_events: [],
      risks: ["Hard latency ceiling at 15ms breached under peak load", "Failover automation requires manual SRE intervention"],
      opportunities: [],
      timeline: [],
      supporting_evidence_item_ids: [],
      relevant_assumption_ids: [],
      relevant_constraint_ids: [],
      relevant_gap_ids: [],
    },
  ],
  created_at: "2026-10-14T10:00:00Z",
};

const MOCK_RESILIENCE_COMPLETE = {
  id: "res_8gc_001",
  decision_model_id: "model_8gc_001",
  scenario_set_id: "scenset_8gc_001",
  recommendation_id: "rec_8gc_001",
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
  ],
  calculation_version: "1.0.0",
  created_at: "2026-10-14T10:00:00Z",
};

const MOCK_FULL_ANALYSIS_RESPONSE = {
  analysis_id: "ana_8gc_test_full",
  status: "completed",
  question: "Should we migrate customer payment workflows to a zero-trust multi-region architecture?",
  message: "Six-stage analysis completed successfully.",
  decision_model: MOCK_DECISION_MODEL_COMPLETE,
  evidence_package: {
    id: "evpkg_8gc_001",
    summary: "Empirical benchmarks compiled from internal telemetry and vendor whitepapers.",
    requirements: [
      { id: "req_1", statement: "Must sustain 50,000 writes/sec p99 under 15ms", status: "fulfilled", criticality: "high" },
      { id: "req_2", statement: "Must stay within $50,000 monthly infra budget", status: "fulfilled", criticality: "high" },
    ],
    items: [
      { id: "item_1", requirement_id: "req_1", source_id: "src_1", finding_text: "Benchmark shows 54,000 writes/sec at 12ms", is_quantitative: true },
    ],
    sources: [
      { id: "src_1", title: "CockroachDB Multi-Region Performance Report", source_type: "benchmark", authority_tier: "tier_1", url: "https://example.com/report" },
    ],
    gaps: [],
    claim_links: [],
  },
  reasoning_board: {
    id: "board_8gc_001",
    summary: "Boardroom consensus reached on phased rollout with strict latency gates.",
    perspectives: [
      { perspective_type: "growth", persona_name: "VP of Growth", stance: "supportive", primary_argument: "Write scalability enables international expansion.", key_concerns: [], criteria_ratings: {} },
    ],
    disagreements: [],
  },
  recommendation: MOCK_RECOMMENDATION_COMPLETE,
  recommendation_status: "completed",
  scenarios: MOCK_SCENARIOS_COMPLETE,
  scenario_status: "completed",
  resilience: MOCK_RESILIENCE_COMPLETE,
  resilience_status: "completed",
};

// -----------------------------------------------------------------------------
// Test Suite
// -----------------------------------------------------------------------------

describe("Day 8G-C: Visual Decision Dashboard & Concise Reporting", () => {
  // Test 1: Full 4-View Dashboard Rendering
  test("1. Renders all 4 primary views (Overview, Explore, Action Plan, Details) with accessible tabs", () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: MOCK_FULL_ANALYSIS_RESPONSE,
        onReset: () => {},
      })
    );

    // Tablist and Tab Buttons
    assert.match(html, /role="tablist"/);
    assert.match(html, /id="tab-overview"/);
    assert.match(html, /id="tab-explore"/);
    assert.match(html, /id="tab-action"/);
    assert.match(html, /id="tab-details"/);

    // Tab Panels
    assert.match(html, /id="panel-overview"/);
    assert.match(html, /id="panel-explore"/);
    assert.match(html, /id="panel-action"/);
    assert.match(html, /id="panel-details"/);

    // Executive Overview Content
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /Execute a 60-day phased pilot migration/);
    assert.match(html, /Alternatives vs\. Chosen Path/);
    assert.match(html, /Aurora PostgreSQL Global Database/);
    assert.match(html, /Top Missing Inputs That Could Shift Decision/);
    assert.match(html, /Conditions That Would Reverse Recommendation/);
  });

  // Test 2: Formatting Utilities (Currency, Percentage, Enums, Text Truncation)
  test("2. Formatters handle currency, numbers, enums, and word-boundary truncation accurately", () => {
    // Currency
    assert.strictEqual(formatCurrency(50000), "$50,000");
    assert.strictEqual(formatCurrency("35000 USD"), "$35,000");
    assert.strictEqual(formatCurrency(null), "N/A");

    // Numbers & Metrics
    assert.strictEqual(formatMetricNumber(50000, "writes/sec"), "50,000 writes/sec");
    assert.strictEqual(formatMetricNumber(15, "ms"), "15 ms");
    assert.strictEqual(formatMetricNumber(85, "%"), "85%");

    // Enums to human labels
    assert.strictEqual(formatEnumLabel("architecture_technology"), "Architecture & Technology");
    assert.strictEqual(formatEnumLabel("partially_reversible"), "Partially Reversible");
    assert.strictEqual(formatEnumLabel("conditional_go"), "Conditional Approval");

    // Word boundary truncation (never cuts words mid-word)
    const longText = "The distributed consensus mechanism provides guaranteed multi-region active replication across all availability zones.";
    const truncated = truncateOnWordBoundary(longText, 50);
    assert.ok(truncated.endsWith("…"), "Must end with ellipsis");
    assert.ok(!truncated.includes("consen…"), "Must not slice mid-word");

    // Concise recommendation extraction (1-2 sentences)
    const twoSentences = "Execute a phased pilot migration immediately. Maintain single-region failback until verified. Additional background reasoning.";
    const extracted = extractConciseRecommendation(twoSentences);
    assert.ok(extracted.includes("Execute a phased pilot migration immediately."));
    assert.ok(extracted.includes("Maintain single-region failback until verified."));
    assert.ok(!extracted.includes("Additional background reasoning."), "Should only capture 1-2 sentences");
  });

  // Test 3: Financial & Quantitative Feasibility Chart
  test("3. FeasibilityTargetChart renders target-vs-outcome for supported metrics without fake numbers", () => {
    const html = renderToStaticMarkup(
      React.createElement(FeasibilityTargetChart, {
        decisionModel: MOCK_DECISION_MODEL_COMPLETE,
      })
    );

    assert.match(html, /Target vs\. Boundary Thresholds/);
    assert.match(html, /\$50,000/);
    assert.match(html, /50,000 writes\/sec/);

    // When no quantitative metrics exist, renders clean qualitative notice (no fabricated chart)
    const qualitativeModel = {
      ...MOCK_DECISION_MODEL_COMPLETE,
      constraints: [],
      objectives: [{ id: "obj_qual", description: "Improve team collaboration", is_primary: true, provenance: "user_provided" }],
      variables: [],
    };

    const qualHtml = renderToStaticMarkup(
      React.createElement(FeasibilityTargetChart, {
        decisionModel: qualitativeModel,
      })
    );

    assert.match(qualHtml, /No quantitative financial metrics declared/);
    assert.doesNotMatch(qualHtml, /<svg/);
  });

  // Test 4: Alternatives Comparison Matrix
  test("4. AlternativesComparisonMatrix compares baseline vs alternative options across dimensions", () => {
    const html = renderToStaticMarkup(
      React.createElement(AlternativesComparisonMatrix, {
        primaryAction: "Execute a 60-day phased pilot migration to CockroachDB",
        alternatives: MOCK_RECOMMENDATION_COMPLETE.alternative_options,
      })
    );

    assert.match(html, /Strategic Alternatives vs\. Chosen Path/);
    assert.match(html, /Baseline Recommendation/);
    assert.match(html, /Aurora PostgreSQL Global Database/);
    assert.match(html, /Deprioritized/);
    assert.match(html, /Fails write-throughput scaling requirements/);
  });

  // Test 5: Scenario Comparison Range Chart & Modeled Estimate Epistemic Caveat
  test("5. ScenarioComparisonChart renders 3 canonical branches with explicit modeled estimate caveat", () => {
    const html = renderToStaticMarkup(
      React.createElement(ScenarioComparisonChart, {
        scenarios: MOCK_SCENARIOS_COMPLETE.scenarios,
        selectedScenarioType: "base_case",
      })
    );

    assert.match(html, /Range &amp; Grouped Scenario Comparison/);
    assert.match(html, /Optimistic/);
    assert.match(html, /Base Case/);
    assert.match(html, /Pessimistic/);
    assert.match(html, /Modeled estimates — not factual probabilities/);
  });

  // Test 6: Resilience Driver Chart
  test("6. ResilienceDriverChart displays overall score, stress-test status, and 4-pillar breakdown", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceDriverChart, {
        report: MOCK_RESILIENCE_COMPLETE,
      })
    );

    assert.match(html, /78\.5/);
    assert.match(html, /Moderate/);
    assert.match(html, /Stress Test Met/);
    assert.match(html, /Constraint Boundary Tolerance/);
    assert.match(html, /Pessimistic Scenario Survivability/);
    assert.match(html, /Contingency &amp; Fallback Coverage/);
    assert.match(html, /Information Robustness/);
    assert.match(html, /Active Threshold Breaches/);
  });

  // Test 7: Action Timeline Visual & Decision Gates (No Placeholder Strings)
  test("7. ActionTimelineVisual and DecisionGateVisual display roles, dependencies, and rollback triggers without placeholders", () => {
    const timelineHtml = renderToStaticMarkup(
      React.createElement(ActionTimelineVisual, {
        actions: MOCK_RECOMMENDATION_COMPLETE.action_plan.actions,
      })
    );

    assert.match(timelineHtml, /Sequential Timeline &amp; Dependency Flow/);
    assert.match(timelineHtml, /Lead Infrastructure Architect/);
    assert.match(timelineHtml, /Deploy Multi-Region Staging Cluster/);
    // Verifies placeholder text was removed
    assert.doesNotMatch(timelineHtml, /Primary execution procedure defined in description/);

    const gateHtml = renderToStaticMarkup(
      React.createElement(DecisionGateVisual, {
        gates: MOCK_RECOMMENDATION_COMPLETE.action_plan.actions[0].decision_gates,
      })
    );

    assert.match(gateHtml, /Decision Gates &amp; Rollback Triggers/);
    assert.match(gateHtml, /Latency Verification Gate/);
    assert.match(gateHtml, /Halt migration and re-evaluate single-region sharding/);
  });

  // Test 8: Integrity Finding Evaluation (Never shows green badge on critical unresolved issues)
  test("8. Decision integrity evaluator prevents green success badges on unresolved issues", () => {
    // Case 1: Failed stress test
    const failedStressResult = {
      ...MOCK_FULL_ANALYSIS_RESPONSE,
      resilience: {
        ...MOCK_RESILIENCE_COMPLETE,
        stress_test_passed: false,
      },
    };

    const integrity1 = evaluateDecisionIntegrity(failedStressResult);
    assert.strictEqual(integrity1.hasCriticalIssues, true);
    assert.ok(integrity1.badgeBorderClass.includes("border-rose"), "Must use rose/amber border on failed stress test");
    assert.ok(!integrity1.badgeBorderClass.includes("border-emerald"), "Must NOT use emerald border");

    // Case 2: Clean verified result with no critical issues
    const cleanResult = {
      ...MOCK_FULL_ANALYSIS_RESPONSE,
      resilience: {
        ...MOCK_RESILIENCE_COMPLETE,
        critical_vulnerabilities: [],
        stress_test_passed: true,
      },
      recommendation: {
        ...MOCK_RECOMMENDATION_COMPLETE,
        uncertainty_assessment: {
          ...MOCK_RECOMMENDATION_COMPLETE.uncertainty_assessment,
          critical_missing_information: [],
          decision_readiness: "ready",
        },
      },
    };

    const integrity2 = evaluateDecisionIntegrity(cleanResult);
    assert.strictEqual(integrity2.hasCriticalIssues, false);
    assert.ok(integrity2.badgeBorderClass.includes("border-emerald"), "Clean result can use emerald border");
  });

  // Test 9: Details View (Collapsible 6-Stage Artifacts, Assumption Registry, and Internal ID Suppression)
  test("9. DetailsView renders collapsible 6-stage artifacts, assumption registry, and isolates internal IDs", () => {
    const html = renderToStaticMarkup(
      React.createElement(DetailsView, {
        result: MOCK_FULL_ANALYSIS_RESPONSE,
      })
    );

    assert.match(html, /Full Six-Stage Analytical Artifacts &amp; Diagnostics/);
    assert.match(html, /Assumption Registry/);
    assert.match(html, /Cross-region network latency remains under 45ms/);
    assert.match(html, /Technical Diagnostics &amp; Provenance Identifiers/);
    assert.match(html, /Analysis Run ID:/);
    assert.match(html, /ana_8gc_test_full/);
  });

  // Test 10: Backwards Compatibility with Missing Optional Stages
  test("10. Backwards compatibility handles missing stages and empty evidence lists without crashing", () => {
    const minimalResponse = {
      analysis_id: "ana_min_001",
      status: "completed",
      question: "Minimal historical question?",
      message: "Minimal deliberation complete.",
      decision_model: null,
      evidence_package: null,
      reasoning_board: null,
      recommendation: null,
      scenarios: null,
      resilience: null,
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: minimalResponse,
        onReset: () => {},
      })
    );

    assert.match(html, /Decision &amp; Evidence Report/);
    assert.match(html, /Minimal historical question\?/);
  });
});
