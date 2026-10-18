import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components and helpers built for Phase 5C (Future Explorer & Scenario Engine)
import { FutureExplorerDashboard } from "../src/components/decision/scenario/FutureExplorerDashboard.tsx";
import { FutureExplorerTree } from "../src/components/decision/scenario/FutureExplorerTree.tsx";
import { ScenarioDetailPanel } from "../src/components/decision/scenario/ScenarioDetailPanel.tsx";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import {
  getScenarioConfig,
  formatScenarioProbability,
  sortScenariosCanonical,
  resolveScenarioEvidenceItem,
  resolveScenarioAssumption,
  resolveScenarioConstraint,
  resolveScenarioGap,
} from "../src/lib/scenarioHelpers.ts";

// ------------------------------------------------------------------------------
// Comprehensive Typed Test Fixtures matching backend schemas
// ------------------------------------------------------------------------------

const MOCK_DECISION_MODEL = {
  id: "model_rec_123",
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
  assumptions: [
    {
      id: "assump_raft_scale",
      statement: "Raft consensus horizontally scales write IOPS linearly across 5 multi-region nodes.",
      confidence: "high",
      falsification_condition: "Benchmarking reveals WAN consensus latency bottleneck.",
      provenance: "inferred",
    },
    {
      id: "assump_ops_skills",
      statement: "Existing SRE staff can handle distributed cluster failover without additional headcount.",
      confidence: "medium",
      falsification_condition: "Chaos simulation requires external vendor escalation.",
      provenance: "inferred",
    },
  ],
  unknowns: [],
  key_questions: [],
};

const MOCK_EVIDENCE_PACKAGE = {
  id: "pkg_rec_456",
  decision_model_id: "model_rec_123",
  requirements: [],
  sources: [],
  items: [
    {
      id: "item_write_iops",
      source_id: "src_bench_1",
      content: "CockroachDB 5-node cluster achieved 54,200 writes/sec under 14ms p99.",
      summary: "Validated write throughput of 54,200 writes/sec.",
      numeric_data: [],
      extraction_confidence: "high",
      retrieval_timestamp: "2026-10-10T00:00:00Z",
    },
  ],
  claim_links: [],
  gaps: [
    {
      id: "gap_wan_chaos",
      gap_type: "insufficient_evidence",
      target_entity_id: "obj_perf",
      target_entity_type: "objective",
      description: "Lack of 72-hour sustained cross-region chaos telemetry under 10% packet drop.",
      criticality: "high",
      resolution_strategy: "Execute 72h chaos test before cutover",
    },
  ],
  synthesis: {
    total_requirements: 1,
    fulfilled_requirements: 1,
    unsupported_requirements: 0,
    contested_requirements: 0,
    inconclusive_requirements: 0,
    evidence_coverage_score: 0.85,
  },
};

const MOCK_RECOMMENDATION = {
  id: "rec_789",
  decision_model_id: "model_rec_123",
  recommended_action: "Execute a 60-day phased pilot migration to CockroachDB with canary routing.",
  decision_status: "pilot",
  executive_summary: "A phased pilot validates write scaling while bounding operational risk.",
  key_reasons: [
    "Meets write throughput target of 50,000 writes/sec.",
    "Binds blast radius via canary deployment.",
  ],
  tradeoffs_accepted: [
    "Operational complexity increases in exchange for horizontal scale.",
  ],
  uncertainty_assessment: {
    evidence_strength: "moderate",
    decision_readiness: "ready_with_conditions",
    recommendation_stability: "conditionally_stable",
    critical_vulnerabilities: [],
    epistemic_caveats: ["Requires chaos testing verification."],
  },
  action_plan: {
    actions: [],
    total_actions: 0,
    hard_gate_count: 0,
  },
  alternative_options: [],
  supporting_evidence_item_ids: ["item_write_iops"],
  tested_assumption_ids: ["assump_raft_scale"],
  addressed_gap_ids: ["gap_wan_chaos"],
  reconciled_disagreement_ids: [],
  created_at: "2026-10-10T12:00:00Z",
};

const MOCK_SCENARIO_SET = {
  id: "scenset_a1b2c3d4e5f678901234567890abcdef",
  decision_model_id: "model_rec_123",
  recommendation_id: "rec_789",
  reasoning_board_id: "board_123",
  evidence_package_id: "pkg_rec_456",
  summary:
    "Portfolio analysis synthesizes three distinct operating futures: the Optimistic case realizes rapid global write throughput past 75k writes/sec; the Base Case delivers stable 54k writes/sec with manageable SRE upskilling; and the Pessimistic stress-test models cross-region WAN latency spikes triggering an automated decision gate fallback to vertical PostgreSQL.",
  created_at: "2026-10-10T12:05:00Z",
  scenarios: [
    {
      id: "scen_opt_12345678abcdef",
      scenario_type: "optimistic",
      probability: 0.35,
      name: "Accelerated Multi-Region Expansion",
      narrative:
        "The distributed CockroachDB cluster scales horizontally across five global cloud regions with minimal operational friction. Inter-region Raft write consensus latency remains under 12ms p99. Transactional throughput exceeds 75,000 writes/second with zero downtime during automated node rebalancing.",
      key_events: [
        {
          id: "ke_opt_1",
          title: "72-Hour Chaos Latency Verification",
          description:
            "Chaos engineering harness injects 10% packet drop across transatlantic links; Raft quorum maintains consensus without transaction timeouts.",
          timeframe: "Month 1",
          trigger_condition: "Packet drop injection < 15ms p99 latency",
          impact_on_decision: "Confirms horizontal scalability hypothesis and clears Decision Gate #1",
        },
        {
          id: "ke_opt_2",
          title: "Full Production Write Cutover",
          description: "All critical write workloads migrated to distributed cluster with zero data loss.",
          timeframe: "Month 2",
          trigger_condition: "Staging error rate < 0.001%",
          impact_on_decision: "Fulfills primary architectural objective of 50,000 writes/sec",
        },
      ],
      risks: [
        "Cloud egress cost increase during high-volume regional cross-sync",
      ],
      opportunities: [
        "Linear write scalability past 75,000 writes/sec headroom",
        "Active-active multi-cloud disaster recovery capability",
      ],
      timeline: [
        {
          id: "ms_opt_1",
          title: "Pilot Canary Validation",
          description: "10% live read/write traffic routed to staging CockroachDB nodes.",
          time_horizon: "immediate",
          expected_outcome: "Zero transactional deadlocks; p99 latency under 15ms",
        },
        {
          id: "ms_opt_2",
          title: "Global Production Rollout",
          description: "100% traffic migration complete across US, EU, and APAC regions.",
          time_horizon: "near_term",
          expected_outcome: "Sustained write throughput > 60,000 writes/sec",
        },
      ],
      supporting_evidence_item_ids: ["item_write_iops"],
      relevant_assumption_ids: ["assump_raft_scale"],
      relevant_constraint_ids: ["cons_budget"],
      relevant_gap_ids: ["gap_wan_chaos"],
    },
    {
      id: "scen_base_12345678abcdef",
      scenario_type: "base_case",
      probability: 0.50,
      name: "Managed Phased Transition with Dedicated SRE Upskilling",
      narrative:
        "Migration progresses smoothly through staged canary milestones. SRE team encounters manageable operational learning curve with Raft consensus rebalancing, successfully resolved through vendor escalation and runbook development. Write throughput stabilizes at 54,000 writes/sec within infrastructure budget constraints.",
      key_events: [
        {
          id: "ke_base_1",
          title: "SRE Chaos Drill Completion",
          description: "Team resolves simulated cluster partition drill within 15 minutes.",
          timeframe: "Month 2",
          trigger_condition: "Controlled node failover exercise",
          impact_on_decision: "Validates internal operations readiness assumption",
        },
      ],
      risks: [
        "Slight initial latency jitter during peak backup snapshots",
        "Temporary duplicate infrastructure cost during 30-day dual-run period",
      ],
      opportunities: [
        "Achieves 50,000 writes/sec objective within $35,000 monthly budget",
        "Establishes mature distributed systems operational capability",
      ],
      timeline: [
        {
          id: "ms_base_1",
          title: "Staging Cluster Benchmark Validation",
          description: "Staging cluster benchmarked at 52,000 writes/sec under synthetic load.",
          time_horizon: "immediate",
          expected_outcome: "Sustained throughput >= 50,000 writes/sec for 48 hours",
        },
        {
          id: "ms_base_2",
          title: "Phased Dual-Run Verification",
          description: "Production read traffic mirrored to CockroachDB with output comparison.",
          time_horizon: "near_term",
          expected_outcome: "Zero divergence between PostgreSQL and CockroachDB reads",
        },
      ],
      supporting_evidence_item_ids: ["item_write_iops"],
      relevant_assumption_ids: ["assump_ops_skills"],
      relevant_constraint_ids: ["cons_budget"],
      relevant_gap_ids: [],
    },
    {
      id: "scen_pess_12345678abcdef",
      scenario_type: "pessimistic",
      probability: 0.15,
      name: "WAN Consensus Bottleneck & Fallback Execution",
      narrative:
        "Cross-region network jitter consistently spikes Raft consensus write latency beyond 45ms. Diagnostic chaos tests fail Decision Gate #1. The engineering organization cleanly aborts CockroachDB cutover and activates the pre-planned fallback to vertical PostgreSQL scaling, bounding monetary and operational loss.",
      key_events: [
        {
          id: "ke_pess_1",
          title: "Decision Gate #1 Latency Threshold Breach",
          description: "Transatlantic WAN commit latency breaches 25ms threshold during chaos audit.",
          timeframe: "Month 1-2",
          trigger_condition: "p99 commit latency > 20ms under 10% packet drop",
          impact_on_decision: "Triggers mandatory fallback protocol; halts broad production cutover",
        },
      ],
      risks: [
        "PostgreSQL vertical scaling reaches hard throughput limit within 9 months",
        "Sunk licensing cost from aborted CockroachDB pilot phase (~$12,000)",
      ],
      opportunities: [
        "Avoids catastrophic production outage and data corruption risk",
        "Preserves existing proven PostgreSQL operational toolchains",
      ],
      timeline: [
        {
          id: "ms_pess_1",
          title: "Gate Verification Failure & Abort",
          description: "Automated Prometheus telemetry detects latency SLA violation; cutover aborted.",
          time_horizon: "immediate",
          expected_outcome: "Fallback to vertical PostgreSQL activated within 2 hours",
        },
      ],
      supporting_evidence_item_ids: [],
      relevant_assumption_ids: ["assump_raft_scale"],
      relevant_constraint_ids: ["cons_budget"],
      relevant_gap_ids: ["gap_wan_chaos"],
    },
  ],
};

// ------------------------------------------------------------------------------
// Test Suite: Phase 5C Interactive Future Explorer UI
// ------------------------------------------------------------------------------

describe("Phase 5C: Interactive Future Explorer UI", () => {
  // Test 1: Helper Utilities - Probability Formatting and Configs
  test("1. Probability formatting and canonical scenario configs work correctly", () => {
    // Normal finite probabilities
    assert.equal(formatScenarioProbability(0.35), "35%");
    assert.equal(formatScenarioProbability(0.5), "50%");
    assert.equal(formatScenarioProbability(0.15), "15%");
    assert.equal(formatScenarioProbability(1.0), "100%");
    assert.equal(formatScenarioProbability(0.0), "0%");

    // Edge cases / NaNs / nulls
    assert.equal(formatScenarioProbability(null), "—");
    assert.equal(formatScenarioProbability(undefined), "—");
    assert.equal(formatScenarioProbability(NaN), "—");

    // Canonical configs
    const optCfg = getScenarioConfig("optimistic");
    assert.equal(optCfg.label, "Optimistic");
    assert.match(optCfg.textClass, /emerald/);

    const baseCfg = getScenarioConfig("base_case");
    assert.equal(baseCfg.label, "Base Case");
    assert.match(baseCfg.textClass, /sky/);

    const pessCfg = getScenarioConfig("pessimistic");
    assert.equal(pessCfg.label, "Pessimistic");
    assert.match(pessCfg.textClass, /rose/);

    // Canonical sorting
    const sorted = sortScenariosCanonical(MOCK_SCENARIO_SET.scenarios);
    assert.equal(sorted[0].scenario_type, "optimistic");
    assert.equal(sorted[1].scenario_type, "base_case");
    assert.equal(sorted[2].scenario_type, "pessimistic");
  });

  // Test 2: All Three Canonical Scenarios Render in FutureExplorerTree
  test("2. FutureExplorerTree renders root decision anchor and all three scenario branches", () => {
    const html = renderToStaticMarkup(
      React.createElement(FutureExplorerTree, {
        decisionTitle: "Should we migrate to CockroachDB?",
        scenarios: MOCK_SCENARIO_SET.scenarios,
        selectedScenarioType: "base_case",
        onSelectScenario: () => {},
      })
    );

    // Root node
    assert.match(html, /Decision Root/);
    assert.match(html, /Should we migrate to CockroachDB\?/);
    assert.match(html, /Stages 1–4 Deliberation Base/);

    // All 3 branch badges and labels
    assert.match(html, /OPTIMISTIC/);
    assert.match(html, /35%/);
    assert.match(html, /Accelerated Multi-Region Expansion/);

    assert.match(html, /BASE CASE/);
    assert.match(html, /50%/);
    assert.match(html, /Managed Phased Transition with Dedicated SRE Upskilling/);

    assert.match(html, /PESSIMISTIC/);
    assert.match(html, /15%/);
    assert.match(html, /WAN Consensus Bottleneck &amp; Fallback Execution/);

    // Accessible trajectory tablist
    assert.match(html, /role="tablist"/);
    assert.match(html, /aria-label="Future Scenario Trajectories"/);
    assert.match(html, /role="tab"/);
  });

  // Test 3: ScenarioDetailPanel Renders Full Narrative, Probabilities and Disclaimer
  test("3. ScenarioDetailPanel displays narrative, modeled probability estimate, and disclaimer", () => {
    const baseScenario = MOCK_SCENARIO_SET.scenarios[1];
    const html = renderToStaticMarkup(
      React.createElement(ScenarioDetailPanel, {
        scenario: baseScenario,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
      })
    );

    // Header & Narrative
    assert.match(html, /BASE CASE TRAJECTORY/);
    assert.match(html, /Managed Phased Transition with Dedicated SRE Upskilling/);
    assert.match(html, /50%/);
    assert.match(html, /Modeled Probability/);
    assert.match(html, /\*Modeled scenario estimate, not a statistical guarantee\./);
    assert.match(html, /Migration progresses smoothly through staged canary milestones/);

    // Opportunities & Risks
    assert.match(html, /Strategic Opportunities \(2\)/);
    assert.match(html, /Achieves 50,000 writes\/sec objective within \$35,000 monthly budget/);
    assert.match(html, /Operational &amp; Strategic Risks \(2\)/);
    assert.match(html, /Slight initial latency jitter during peak backup snapshots/);
  });

  // Test 4: Key Events and Milestones Render in ScenarioDetailPanel
  test("4. ScenarioDetailPanel renders key trigger events and timeline milestones with expected outcomes", () => {
    const optScenario = MOCK_SCENARIO_SET.scenarios[0];
    const html = renderToStaticMarkup(
      React.createElement(ScenarioDetailPanel, {
        scenario: optScenario,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
      })
    );

    // Key event details
    assert.match(html, /ke_opt_1/);
    assert.match(html, /72-Hour Chaos Latency Verification/);
    assert.match(html, /Month 1/);
    assert.match(html, /Packet drop injection &lt; 15ms p99 latency/);
    assert.match(html, /Confirms horizontal scalability hypothesis and clears Decision Gate #1/);

    // Milestone details
    assert.match(html, /ms_opt_1/);
    assert.match(html, /Pilot Canary Validation/);
    assert.match(html, /immediate/);
    assert.match(html, /Zero transactional deadlocks; p99 latency under 15ms/);
  });

  // Test 5: Epistemic Grounding Resolves Known Evidence, Assumptions, Constraints, and Gaps
  test("5. Epistemic grounding resolves known IDs and displays fallbacks for unknown IDs", () => {
    // 5a. Resolver functions
    const resolvedItem = resolveScenarioEvidenceItem(MOCK_EVIDENCE_PACKAGE, "item_write_iops");
    assert.ok(resolvedItem);
    assert.match(resolvedItem.summary, /54,200 writes\/sec/);

    const unknownItem = resolveScenarioEvidenceItem(MOCK_EVIDENCE_PACKAGE, "item_nonexistent");
    assert.equal(unknownItem, null);

    const resolvedAssump = resolveScenarioAssumption(MOCK_DECISION_MODEL, "assump_raft_scale");
    assert.ok(resolvedAssump);
    assert.match(resolvedAssump.statement, /Raft consensus horizontally scales/);

    const resolvedConstraint = resolveScenarioConstraint(MOCK_DECISION_MODEL, "cons_budget");
    assert.ok(resolvedConstraint);
    assert.match(resolvedConstraint.description, /\$35,000/);

    const resolvedGap = resolveScenarioGap(MOCK_EVIDENCE_PACKAGE, "gap_wan_chaos");
    assert.ok(resolvedGap);
    assert.match(resolvedGap.description, /Lack of 72-hour sustained cross-region chaos telemetry/);

    // 5b. Component markup
    const html = renderToStaticMarkup(
      React.createElement(ScenarioDetailPanel, {
        scenario: MOCK_SCENARIO_SET.scenarios[0],
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
      })
    );

    assert.match(html, /item_write_iops/);
    assert.match(html, /Validated write throughput of 54,200 writes\/sec/);
    assert.match(html, /assump_raft_scale/);
    assert.match(html, /Raft consensus horizontally scales/);
    assert.match(html, /cons_budget/);
    assert.match(html, /Infra Budget: Monthly infra budget cap \$35,000/);
    assert.match(html, /gap_wan_chaos/);
  });

  // Test 6: Empty or Missing Optional Fields Render Gracefully Without Crashing
  test("6. Empty or missing optional scenario fields render safely without crashing", () => {
    const minimalScenario = {
      id: "scen_min_12345678",
      scenario_type: "base_case",
      probability: 0.5,
      name: "Minimal Trajectory",
      narrative: "Minimal baseline scenario narrative for edge case testing.",
      key_events: [
        {
          id: "ke_min_1",
          title: "Simple Event",
          description: "Simple event description.",
          timeframe: "Immediate",
          trigger_condition: null,
          impact_on_decision: null,
        },
      ],
      risks: [],
      opportunities: [],
      timeline: [
        {
          id: "ms_min_1",
          title: "Simple Milestone",
          description: "Simple milestone checkpoint.",
          time_horizon: "immediate",
          expected_outcome: "Baseline achieved",
        },
      ],
      supporting_evidence_item_ids: [],
      relevant_assumption_ids: [],
      relevant_constraint_ids: [],
      relevant_gap_ids: [],
    };

    const html = renderToStaticMarkup(
      React.createElement(ScenarioDetailPanel, {
        scenario: minimalScenario,
        evidencePackage: null,
        decisionModel: null,
      })
    );

    assert.match(html, /Minimal Trajectory/);
    assert.match(html, /No specific upside opportunities projected for this trajectory\./);
    assert.match(html, /No specific acute risks projected for this trajectory\./);
    assert.match(html, /No upstream evidence items or model assumptions explicitly linked to this scenario\./);
  });

  // Test 7: Full FutureExplorerDashboard Renders Executive Synthesis and Comparison Matrix
  test("7. FutureExplorerDashboard renders executive summary, view toggle, and comparison matrix", () => {
    const html = renderToStaticMarkup(
      React.createElement(FutureExplorerDashboard, {
        scenarioSet: MOCK_SCENARIO_SET,
        decisionModel: MOCK_DECISION_MODEL,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionTitle: "Should we migrate to CockroachDB?",
      })
    );

    // Executive synthesis header
    assert.match(html, /Stage 5: Scenario Engine/);
    assert.match(html, /Future Explorer &amp; Trajectory Forecasts/);
    assert.match(html, /Portfolio analysis synthesizes three distinct operating futures/);
    assert.match(html, /Modeled Scenario Estimates:/);

    // View toggle buttons
    assert.match(html, /Tree View/);
    assert.match(html, /Comparison Matrix/);

    // Side-by-side comparative matrix
    assert.match(html, /Three-Scenario Comparative Matrix/);
    assert.match(html, /Canonical Trajectories/);
    assert.match(html, /Accelerated Multi-Region Expansion/);
    assert.match(html, /Managed Phased Transition with Dedicated SRE Upskilling/);
    assert.match(html, /WAN Consensus Bottleneck &amp; Fallback Execution/);
  });

  // Test 8: Unavailable Scenario State Renders Graceful Notice and Preserves Stages 1-4
  test("8. Unavailable scenario state renders safe notice and preserves upstream artifacts", () => {
    const partialScenarioResult = {
      analysis_id: "ana_scen_fail_123",
      status: "partial_success",
      question: "Should we migrate to CockroachDB?",
      message: "Stages 1-4 completed; Stage 5 timed out.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      recommendation_error: null,
      scenarios: null,
      scenario_status: "unavailable",
      scenario_error: "Stage 5 scenario generation timed out after 45.00s.",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: partialScenarioResult,
        onReset: () => {},
      })
    );

    // Partial analysis notice in header
    assert.match(html, /Partial Analysis Complete/);
    assert.match(html, /partial_success/);

    // Scenario unavailable banner
    assert.match(html, /Stage 5: Future Scenarios Unavailable/);
    assert.match(html, /Stage 5 scenario generation timed out after 45\.00s\./);
    assert.match(html, /Decision Foundation \(Stages 1–4\) Intact/);

    // Upstream artifacts remain fully rendered!
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /Execute a 60-day phased pilot migration to CockroachDB/);
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /id="section-evidence-engine"/);
  });

  // Test 9: Historical 4-Stage Response Renders Cleanly Without Stage 5 Error
  test("9. Historical 4-stage response without Stage 5 renders smoothly without errors", () => {
    const historicalResult = {
      analysis_id: "ana_hist_123",
      status: "completed",
      question: "Should we migrate to CockroachDB?",
      message: "Four-stage analysis completed.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      recommendation_error: null,
      // Stage 5 omitted entirely (historical response)
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: historicalResult,
        onReset: () => {},
      })
    );

    // Analysis is complete
    assert.match(html, /Analysis Complete/);
    assert.match(html, /completed/);

    // No Stage 5 error or broken scenario section
    assert.doesNotMatch(html, /Stage 5: Future Scenarios Unavailable/);
    assert.doesNotMatch(html, /Inconsistent Scenario State/);

    // Recommendation and model render properly
    assert.match(html, /Execute a 60-day phased pilot migration to CockroachDB/);
    assert.match(html, /id="section-decision-model"/);
  });

  // Test 10: Complete 5-Stage Analysis Renders Both Recommendation and Future Explorer
  test("10. Complete 5-stage analysis integrates Stage 4 recommendation and Stage 5 scenarios harmoniously", () => {
    const completeResult = {
      analysis_id: "ana_full_5stage_123",
      status: "completed",
      question: "Should we migrate to CockroachDB?",
      message: "All 5 stages completed successfully.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: null,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
      recommendation_error: null,
      scenarios: MOCK_SCENARIO_SET,
      scenario_status: "completed",
      scenario_error: null,
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: completeResult,
        onReset: () => {},
      })
    );

    // Top status
    assert.match(html, /Analysis Complete/);
    assert.match(html, /completed/);

    // Stage 4 Recommendation is present
    assert.match(html, /Executive Recommendation/);
    assert.match(html, /Execute a 60-day phased pilot migration to CockroachDB/);

    // Stage 5 Future Explorer is present
    assert.match(html, /Stage 5: Scenario Engine/);
    assert.match(html, /Future Explorer &amp; Trajectory Forecasts/);
    assert.match(html, /Three-Scenario Comparative Matrix/);
    assert.match(html, /Accelerated Multi-Region Expansion/);
    assert.match(html, /Managed Phased Transition with Dedicated SRE Upskilling/);
    assert.match(html, /WAN Consensus Bottleneck &amp; Fallback Execution/);

    // Stages 1 and 2 are present
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /id="section-evidence-engine"/);
  });

  // Test 11: Print and PDF Compatibility - Static Content Rendered Without Canvas Reliance
  test("11. Print and export compatibility: static comparative cards render for PDF printing", () => {
    const html = renderToStaticMarkup(
      React.createElement(FutureExplorerTree, {
        decisionTitle: "Should we migrate to CockroachDB?",
        scenarios: MOCK_SCENARIO_SET.scenarios,
        selectedScenarioType: "base_case",
        onSelectScenario: () => {},
      })
    );

    // Check for print fallback section
    assert.match(html, /hidden print:block/);
    assert.match(html, /Future Scenario Trajectories/);
    assert.match(html, /OPTIMISTIC/);
    assert.match(html, /BASE CASE/);
    assert.match(html, /PESSIMISTIC/);
  });
});
