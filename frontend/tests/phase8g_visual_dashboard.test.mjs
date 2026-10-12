import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import Day 8G Visual Dashboard Components
import { DecisionOverviewCard } from "../src/components/decision/integrity/DecisionOverviewCard.tsx";
import { OptionComparisonMatrix } from "../src/components/decision/integrity/OptionComparisonMatrix.tsx";
import { FinancialFeasibilityCard } from "../src/components/decision/integrity/FinancialFeasibilityCard.tsx";
import { ScenarioMatrixVisualizer } from "../src/components/decision/integrity/ScenarioMatrixVisualizer.tsx";
import { ResilienceScorecard } from "../src/components/decision/integrity/ResilienceScorecard.tsx";
import { IntegrityFindingsCard } from "../src/components/decision/integrity/IntegrityFindingsCard.tsx";
import { EvidenceQualityCard } from "../src/components/decision/integrity/EvidenceQualityCard.tsx";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import { getSummaryPdfUrl, getDetailedPdfUrl } from "../src/lib/api.ts";

// ------------------------------------------------------------------------------
// Test Fixtures
// ------------------------------------------------------------------------------

const MOCK_INTEGRITY_FINDINGS = [
  {
    finding_id: "f_01",
    rule_code: "R001_NET_SAVINGS_UNRESOLVED",
    severity: "critical",
    status: "unresolved",
    affected_stages: [1, 4],
    title: "Net Savings Unresolved",
    description: "Net savings calculation unresolved due to missing recurring cloud infrastructure cost.",
    relevant_values: { annual_baseline_support_cost: 1200000 },
    units: "USD",
    provenance: "Stage 1 variables",
    suggested_resolution: "Provide explicit monthly or annual cloud infrastructure cost estimates.",
  },
  {
    finding_id: "f_02",
    rule_code: "R003_SCENARIO_GATE_CONFLICT",
    severity: "high",
    status: "requires_review",
    affected_stages: [4, 5],
    title: "Scenario Gate Conflict",
    description: "Pessimistic scenario deflection (18%) falls below Phase 2 expansion gate threshold (25%).",
    relevant_values: { pessimistic_deflection: 0.18, phase2_gate: 0.25 },
    units: "fraction",
    provenance: "Stage 4 decision gates vs Stage 5 scenario projections",
    suggested_resolution: "Align stage 4 expansion criteria or adjust scenario assumptions.",
  },
];

const MOCK_CALCULATIONS = [
  {
    id: "calc_net_savings",
    title: "Annual Net Savings",
    category: "annual_net_savings",
    formula: "annual_gross_savings - annual_cloud_cost - other_incremental_costs",
    value: 236000,
    unit: "USD",
    currency: "$",
    status: "feasible",
    provenance: ["Stage 1 variables", "Deterministic Calculator"],
    explanation: "Realized deflection of 35% on $1.2M baseline minus $184k total operating costs.",
    missing_inputs: [],
    explicit_assumptions: ["35% deflection rate", "15% avoidable labor cost fraction"],
  },
];

const MOCK_EVIDENCE_QUALITY = {
  total_sources: 12,
  duplicate_sources_detected: 1,
  category_breakdown: {
    primary_empirical: 4,
    independent_secondary: 5,
    official_standard: 1,
    vendor_produced: 2,
  },
  classifications: [
    {
      source_id: "s1",
      title: "Vendor Technical Brief",
      url: "https://example-vendor.com/case-study",
      category: "vendor_produced",
      is_independent: false,
      is_duplicate: true,
      credibility_notes: "Vendor marketing document",
      limitations: ["Self-reported customer benchmarks"],
    },
  ],
  independence_ratio: 0.75,
};

const MOCK_OPTION_COMPARISON_REPORT = {
  evaluated_criteria: ["Operational Reversibility", "Customer CSAT Protection", "Implementation Risk"],
  comparison_matrix_note: "Qualitative trade-off matrix without manufactured scores",
  is_conclusive: true,
  options: [
    {
      option_id: "opt_pilot",
      title: "Controlled Phased Pilot",
      description: "Canary routing deployment for 60 days.",
      is_recommended: true,
      strengths: ["Low initial capital outlay", "Preserves rollback options", "Validates assumptions"],
      weaknesses: ["Delayed full-scale efficiency", "Requires dual operational monitoring"],
      constraint_compatibility: "Fully satisfies all technical and financial constraints",
      supporting_evidence_count: 3,
      missing_evidence: ["Long-term churn metrics under pilot conditions"],
      key_tradeoffs: ["Trades rapid total cost reduction for operational reversibility"],
      feasibility_status: "feasible",
    },
    {
      option_id: "opt_full_cutover",
      title: "Immediate Full Deployment",
      description: "Direct cutover of entire customer support queue.",
      is_recommended: false,
      strengths: ["Maximum theoretical annual savings"],
      weaknesses: ["Irreversible customer failure risk", "Violates 90% CSAT floor in pessimistic branch"],
      constraint_compatibility: "Violates customer satisfaction hard constraint",
      supporting_evidence_count: 0,
      missing_evidence: ["Zero-trust security compliance clearance"],
      key_tradeoffs: ["High financial upside with catastrophic downside vulnerability"],
      feasibility_status: "infeasible",
    },
  ],
};

const MOCK_ANALYSIS_FOR_VISUALS = {
  analysis_id: "ana_8g_test_001",
  status: "completed",
  question: "Should we migrate support operations to an agentic automation workflow?",
  message: "Analysis completed successfully.",
  decision_model: {
    decision: {
      summary: "Customer Support Automation Architecture",
      decision_type: "operations_workflow",
      time_horizon: "medium_term",
    },
    objectives: [
      { id: "obj_cost", description: "Reduce tier-1 support costs by 25%", is_primary: true },
    ],
    constraints: [
      { id: "cons_csat", name: "CSAT Floor", description: "Maintain CSAT above 90%", is_hard_constraint: true },
    ],
    tradeoffs: [
      { id: "to_1", name: "Reversibility vs Speed", upside: "Controlled rollout", downside: "Delayed cost savings" },
    ],
    unknowns: [],
    complexity: { level: "medium", reversibility: "reversible", score: 50, reasoning: "Phased deployment" },
    variables: [
      { name: "Annual Baseline Support Cost", proposed_value: 1200000, unit: "USD" },
      { name: "Realized Deflection Rate", proposed_value: 0.35, unit: "fraction" },
    ],
    assumptions: [
      {
        assumption: "Deflection stabilizes within 60 days",
        statement: "Deflection stabilizes within 60 days",
        falsification_condition: "Support ticket backlog increases by more than 20% during trial",
      },
    ],
  },
  evidence_package: {
    id: "pkg_test_001",
    total_sources: 12,
    sources: [
      { id: "s1", title: "Empirical Automation Study", url: "https://ieee.org/study" },
    ],
    requirements: [],
    items: [],
    gaps: [],
  },
  reasoning_board: {
    perspectives: [
      {
        id: "p_fin",
        perspective_type: "finance",
        summary: "High ROI potential and positive net savings.",
        arguments: [],
      },
    ],
    synthesis: { narrative: "Consensus on controlled phased approach." },
  },
  recommendation: {
    recommended_action: "Execute a 60-day phased pilot deployment with canary routing.",
    executive_rationale: "Maximizes optionality and verifies 35% deflection before full capital commitment.",
    action_plan: {
      overview: "Controlled pilot rollout strategy.",
      actions: [
        {
          id: "act_01",
          title: "Pilot Canary Setup",
          description: "Initialize canary routing configuration.",
          priority: "high",
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
    uncertainty_assessment: {
      evidence_strength: "moderate",
      decision_readiness: "conditional",
      recommendation_stability: "stable",
      conditions_changing_recommendation: [
        "Cloud inference costs exceed $22,000 monthly during initial canary phase",
      ],
    },
  },
  recommendation_status: "completed",
  scenarios: {
    scenarios: [
      { id: "scen_base", scenario_type: "base_case", name: "Steady Deflection", narrative: "35% deflection achieved smoothly." },
      { id: "scen_opt", scenario_type: "optimistic", name: "High Adoption", narrative: "45% deflection with positive CSAT lift." },
      { id: "scen_pess", scenario_type: "pessimistic", name: "Inference Lag", narrative: "Latency causes customer churn risk." },
    ],
  },
  scenario_status: "completed",
  resilience: {
    overall_score: 78.5,
    rating: "robust",
    is_viable: true,
    sub_scores: [
      { category: "constraint_boundary_tolerance", score: 21, max_score: 25, rationale: "Within CSAT limits", vulnerabilities_detected: [] },
      { category: "pessimistic_scenario_survivability", score: 18, max_score: 25, rationale: "Survives latency spike", vulnerabilities_detected: [] },
      { category: "contingency_and_fallback_coverage", score: 20, max_score: 25, rationale: "Bounded dependencies", vulnerabilities_detected: [] },
      { category: "information_robustness", score: 19.5, max_score: 25, rationale: "GDPR compliant", vulnerabilities_detected: [] },
    ],
    critical_vulnerabilities: [
      "Inference latency spike degrades customer retention under load",
    ],
    recommended_hedges: [
      "Implement canary fallback routing for immediate human agent cutback",
    ],
  },
  resilience_status: "completed",
};

// ------------------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------------------

describe("Phase 8G: Executive Decision Visual Dashboard & Reports", () => {
  // Test 1: Persistent Decision Overview Card
  test("1. DecisionOverviewCard displays persistent executive summary, readiness, integrity, and falsification condition", () => {
    const html = renderToStaticMarkup(
      React.createElement(DecisionOverviewCard, {
        decisionTitle: "Customer Support Automation Architecture",
        recommendedDirection: "Execute a 60-day phased pilot deployment with canary routing.",
        shortRationale: "Maximizes optionality and verifies 35% deflection before full capital commitment.",
        decisionReadiness: "conditional",
        integrityStatus: "warnings_present",
        criticalWarningCount: 2,
        topFalsificationCondition: "Cloud inference costs exceed $22,000 monthly during initial canary phase",
        keyMetrics: { "Net Annual Savings": "$236,000" },
        analysisStatus: "completed",
        analysisId: "ana_8g_test_001",
      })
    );

    // Landmarks and Accessible Header
    assert.match(html, /aria-label="Executive Decision Overview"/);
    assert.match(html, /Customer Support Automation Architecture/);
    assert.match(html, /Execute a 60-day phased pilot deployment with canary routing/);
    assert.match(html, /Conditional Approval/);
    assert.match(html, /2 Cross-Stage Warnings/);
    assert.match(html, /Cloud inference costs exceed \$22,000 monthly during initial canary phase/);
    assert.match(html, /\$236,000/);
    assert.match(html, /Pipeline:.*Analysis Complete/);
  });

  // Test 2: Qualitative Option Comparison Matrix (No Fabricated Scores)
  test("2. OptionComparisonMatrix renders qualitative trade-offs without manufactured weighted scores", () => {
    const html = renderToStaticMarkup(
      React.createElement(OptionComparisonMatrix, {
        report: MOCK_OPTION_COMPARISON_REPORT,
      })
    );

    // Header & Qualitative Matrix
    assert.match(html, /Strategic Options Comparison Matrix/);
    assert.match(html, /2 Viable Strategic Pathways Evaluated/);
    assert.doesNotMatch(html, /Weighted Score/);
    assert.doesNotMatch(html, /Composite Score: 98/);

    // Options and criteria
    assert.match(html, /Controlled Phased Pilot/);
    assert.match(html, /Immediate Full Deployment/);
    assert.match(html, /AI Consensus Recommendation/);
    assert.match(html, /Trades rapid total cost reduction for operational reversibility/);
    assert.match(html, /Violates customer satisfaction hard constraint/);
  });

  // Test 3: Financial Feasibility Breakdown
  test("3. FinancialFeasibilityCard renders precision-safe calculations and explicit assumptions", () => {
    const html = renderToStaticMarkup(
      React.createElement(FinancialFeasibilityCard, {
        calculations: MOCK_CALCULATIONS,
      })
    );

    assert.match(html, /Financial &amp; Quantitative Feasibility/);
    assert.match(html, /Annual Net Savings/);
    assert.match(html, /\$236,000/);
    assert.match(html, /annual_gross_savings - annual_cloud_cost - other_incremental_costs/);
    assert.match(html, /35% deflection rate/);
  });

  // Test 4: Scenario Matrix Visualizer
  test("4. ScenarioMatrixVisualizer renders future pathways with explicit uncalibrated disclaimer", () => {
    const html = renderToStaticMarkup(
      React.createElement(ScenarioMatrixVisualizer, {
        scenarioSet: MOCK_ANALYSIS_FOR_VISUALS.scenarios,
        decisionTitle: "Support Automation Workflow",
      })
    );

    assert.match(html, /Future Scenarios &amp; Stress-Testing/);
    assert.match(html, /Epistemic Uncertainty Calibration/);
    assert.match(html, /Steady Deflection/);
    assert.match(html, /High Adoption/);
    assert.match(html, /Inference Lag/);
  });

  // Test 5: Resilience Scorecard
  test("5. ResilienceScorecard displays 0-100 score, pillars, and disclaimer that resilience is not success probability", () => {
    const html = renderToStaticMarkup(
      React.createElement(ResilienceScorecard, {
        report: MOCK_ANALYSIS_FOR_VISUALS.resilience,
      })
    );

    assert.match(html, /Decision Resilience Scorecard/);
    assert.match(html, /78\.5/);
    assert.match(html, /does not represent an empirical probability of strategic success/);
    assert.match(html, /constraint_boundary_tolerance/);
    assert.match(html, /Inference latency spike degrades customer retention under load/);
    assert.match(html, /Implement canary fallback routing for immediate human agent cutback/);
  });

  // Test 6: Cross-Stage Decision Integrity Findings
  test("6. IntegrityFindingsCard displays cross-stage findings with severities and suggested resolutions", () => {
    const html = renderToStaticMarkup(
      React.createElement(IntegrityFindingsCard, {
        findings: MOCK_INTEGRITY_FINDINGS,
      })
    );

    assert.match(html, /Cross-Stage Decision Integrity/);
    assert.match(html, /R001_NET_SAVINGS_UNRESOLVED/);
    assert.match(html, /Net savings calculation unresolved due to missing recurring cloud infrastructure cost\./);
    assert.match(html, /R003_SCENARIO_GATE_CONFLICT/);
    assert.match(html, /Provide explicit monthly or annual cloud infrastructure cost estimates\./);
  });

  // Test 7: Transparent Evidence Quality Classification
  test("7. EvidenceQualityCard displays evidence categories, independence ratio, and duplicate detection", () => {
    const html = renderToStaticMarkup(
      React.createElement(EvidenceQualityCard, {
        report: MOCK_EVIDENCE_QUALITY,
      })
    );

    assert.match(html, /Evidence Quality &amp; Source Provenance/);
    assert.match(html, /Independent Sources/);
    assert.match(html, /75%/);
    assert.match(html, /1 Duplicate Citation/);
    assert.match(html, /https:\/\/example-vendor\.com\/case-study/);
  });

  // Test 8: AnalysisResultCard Three Collapsible Sections Behavior
  test("8. AnalysisResultCard provides exactly 3 collapsible sections with default open/collapsed states", () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: MOCK_ANALYSIS_FOR_VISUALS,
        onReset: () => {},
      })
    );

    // Section 1: Interactive Decision Visualizations (EXPANDED by default)
    assert.match(html, /Interactive Decision Visualizations/);
    assert.match(html, /aria-controls="section-1-content"/);
    assert.match(html, /id="section-1-content"/);

    // Section 2: Summarized Report (COLLAPSED by default)
    assert.match(html, /Summarized Report/);
    assert.match(html, /Executive Synthesis \(2–4 Pages\)/);
    assert.match(html, /aria-controls="section-2-content"/);
    assert.match(html, /id="section-2-content"/);
    assert.match(html, /View Summary Online/);
    assert.match(html, /Download Summary PDF/);

    // Section 3: Detailed Report (COLLAPSED by default)
    assert.match(html, /Detailed Report/);
    assert.match(html, /Comprehensive Analytical Audit/);
    assert.match(html, /aria-controls="section-3-content"/);
    assert.match(html, /id="section-3-content"/);
    assert.match(html, /View Detailed Report Online/);
    assert.match(html, /Download Detailed PDF/);
  });

  // Test 9: PDF Endpoint URL Helpers
  test("9. PDF helpers generate correct API routes with encoded analysis ID and owner scope", () => {
    const summaryUrl = getSummaryPdfUrl("ana_test_123", "owner_alice");
    assert.match(summaryUrl, /\/api\/analysis\/ana_test_123\/report\/summary\/pdf\?owner_id=owner_alice/);

    const detailedUrl = getDetailedPdfUrl("ana_test_123", "owner_alice");
    assert.match(detailedUrl, /\/api\/analysis\/ana_test_123\/report\/detailed\/pdf\?owner_id=owner_alice/);
  });
});
