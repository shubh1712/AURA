import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components built for Phase 5.3 (Executive Recommendation Dashboard)
import { RecommendationDashboard } from "../src/components/decision/recommendation/RecommendationDashboard.tsx";
import { ExecutiveRecommendationHero } from "../src/components/decision/recommendation/ExecutiveRecommendationHero.tsx";
import { UncertaintyReadinessSection } from "../src/components/decision/recommendation/UncertaintyReadinessSection.tsx";
import { ActionRoadmapSection } from "../src/components/decision/recommendation/ActionRoadmapSection.tsx";
import { DecisionGateCard } from "../src/components/decision/recommendation/DecisionGateCard.tsx";
import { AlternativeOptionsSection } from "../src/components/decision/recommendation/AlternativeOptionsSection.tsx";
import { EvidenceTraceabilitySection } from "../src/components/decision/recommendation/EvidenceTraceabilitySection.tsx";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import { StageAwareProgress } from "../src/components/decision/StageAwareProgress.tsx";
import {
  getStatusConfig,
  resolveEvidenceItem,
  resolveAssumption,
  resolveEvidenceGap,
  resolveDisagreement,
} from "../src/lib/recommendationHelpers.ts";

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
  unknowns: [
    {
      id: "unk_wan_lat",
      question: "What is cross-region p99 commit latency during 10% packet drop?",
      criticality: "high",
      potential_sources: ["Benchmarking harness"],
      provenance: "inferred",
    },
  ],
  key_questions: [],
};

const MOCK_EVIDENCE_PACKAGE = {
  id: "pkg_rec_456",
  decision_model_id: "model_rec_123",
  requirements: [
    {
      id: "req_bench_perf",
      target_entity_id: "obj_perf",
      target_entity_type: "objective",
      kind: "deterministic_calculation",
      description: "Verify write throughput across 5 distributed nodes.",
      priority: "high",
      status: "fulfilled",
      suggested_queries: [],
    },
  ],
  sources: [
    {
      id: "src_cloud_bench",
      url: "https://benchmarks.internal/cockroach-v23",
      title: "Distributed Database Benchmark 2026",
      publisher: "Database Platform Engineering",
      source_type: "internal_data",
      publication_date: "2026-03-01",
      retrieval_timestamp: "2026-03-05T10:00:00Z",
      reliability_score: 0.95,
    },
  ],
  items: [
    {
      id: "item_write_iops",
      source_id: "src_cloud_bench",
      content: "5-node CockroachDB cluster demonstrated 54,200 writes/sec at p99 12.4ms under synthetic OLTP workload.",
      summary: "Write throughput objective verified empirically.",
      numeric_data: [
        {
          metric_name: "write_throughput",
          value: 54200,
          unit: "writes/sec",
        },
      ],
      extraction_confidence: "high",
      retrieval_timestamp: "2026-03-05T10:05:00Z",
    },
    {
      id: "item_wan_latency",
      source_id: "src_cloud_bench",
      content: "Cross-region commit latency spiked to 48ms during 10% WAN packet loss injection.",
      summary: "Degraded WAN latency exceeds 15ms target.",
      numeric_data: [],
      extraction_confidence: "high",
      retrieval_timestamp: "2026-03-05T10:06:00Z",
    },
  ],
  claim_links: [
    {
      id: "link_perf_obj",
      evidence_item_id: "item_write_iops",
      target_entity_id: "obj_perf",
      target_entity_type: "objective",
      stance: "supports",
      reasoning: "Observed 54k IOPS satisfies the 50k target.",
      relationship_confidence: "high",
      requirement_id: "req_bench_perf",
    },
  ],
  gaps: [
    {
      id: "gap_wan_chaos",
      gap_type: "insufficient_evidence",
      target_entity_id: "unk_wan_lat",
      target_entity_type: "unknown",
      requirement_id: "req_bench_perf",
      description: "Lack of 72-hour sustained chaos telemetry for multi-region failover under heavy network partition.",
      impact: "high",
      conflicting_evidence_ids: [],
      resolution_guidance: "Run 72h chaos mesh testing in staging environment before production cutover.",
    },
  ],
  summary: "Comprehensive benchmarking data confirms baseline write throughput, with caution regarding WAN degradation.",
  created_at: "2026-03-05T10:15:00Z",
};

const MOCK_REASONING_BOARD = {
  id: "board_rec_789",
  perspectives: [],
  disagreements: [
    {
      id: "dis_wan_cost_risk",
      topic: "Cross-region operational risk vs performance headroom",
      nature: "evidence_dependent",
      positions: {
        persp_growth: "Prioritize 50k writes/sec to unlock global market expansion.",
        persp_risk: "Cross-region failover packet degradation introduces unmitigated SLA breach hazard.",
      },
      evidence_item_ids: ["item_wan_latency"],
      assumption_ids: ["assump_raft_scale"],
      evidence_gap_ids: ["gap_wan_chaos"],
    },
  ],
  synthesis: {
    reconciled_narrative: "Balanced consensus suggests a conditional pilot deployment before full database migration.",
    areas_of_agreement: ["Monolithic PostgreSQL cannot sustainably meet 50k writes/sec."],
    unresolved_tensions: ["Tolerance for cross-region latency spikes during network anomalies."],
    key_assumptions_dependencies: ["Internal SRE capability to troubleshoot Raft splits."],
    critical_questions_for_decision_maker: ["Is 15ms p99 an inflexible hard constraint across all geographic regions?"],
  },
};

const MOCK_RECOMMENDATION = {
  id: "rec_exec_001",
  decision_model_id: "model_rec_123",
  evidence_package_id: "pkg_rec_456",
  reasoning_board_id: "board_rec_789",
  decision_status: "conditional",
  recommended_action: "Execute a 60-day phased pilot migration of read-heavy microservices to a 5-node CockroachDB cluster with strict latency decision gates.",
  executive_rationale: "Empirical benchmarking confirms CockroachDB sustains 54,200 writes/sec exceeding our 50,000 threshold. However, cross-region WAN anomalies create latency spikes. A conditional pilot insulates primary revenue transactions while testing consensus under actual traffic.",
  supporting_evidence_item_ids: ["item_write_iops", "item_wan_latency"],
  relevant_assumption_ids: ["assump_raft_scale", "assump_ops_skills"],
  relevant_evidence_gap_ids: ["gap_wan_chaos"],
  unresolved_disagreement_ids: ["dis_wan_cost_risk"],
  alternative_options: [
    {
      id: "alt_vert_scale_pg",
      name: "Scale PostgreSQL Vertically with Read Replicas",
      description: "Upgrade PostgreSQL to 128 vCPU primary instance with connection pooling and 4 read replicas.",
      tradeoffs: [
        "Lower operational risk and no distributed consensus complexity.",
        "Hard ceiling on single-node transactional write IOPS capped at ~28,000.",
      ],
      why_not_recommended: "Fails to meet primary objective of 50,000 writes/sec by year end, forcing another architectural rewrite within 9 months.",
    },
    {
      id: "alt_defer_migration",
      name: "Defer Migration to Next Fiscal Year",
      description: "Postpone database re-architecture until cloud vendor releases managed multi-region multi-master service.",
      tradeoffs: [
        "Avoids near-term SRE resource reallocation.",
        "Risks catastrophic database saturation during Q4 traffic spike.",
      ],
      why_not_recommended: "Telemetry trends project 98% write buffer utilization within 4 months; deferral poses unacceptable outage risk.",
    },
  ],
  uncertainty_assessment: {
    evidence_strength: "strong",
    decision_readiness: "conditional",
    recommendation_stability: "high",
    critical_missing_information: [
      "72-hour sustained chaos telemetry for multi-region failover under packet degradation",
      "Exact pricing model for cross-region egress traffic under full transactional replication",
    ],
    conditions_changing_recommendation: [
      "If cross-region p99 latency consistently exceeds 30ms during staging chaos testing",
      "If managed cloud hosting costs exceed the $35,000 monthly hard constraint",
    ],
    assumptions_relied_upon: ["assump_raft_scale", "assump_ops_skills"],
    evidence_gaps_relied_upon: ["gap_wan_chaos"],
  },
  action_plan: {
    summary: "A 4-phase rollout commencing with staging chaos validation, moving to canary telemetry, and culminating in full microservice cutover.",
    key_milestones: [
      "Stage 1: Multi-Region Staging Benchmark & Chaos Audit",
      "Stage 2: Non-Critical Microservice Canary Cutover",
      "Stage 3: Full Core Service Cluster Migration",
    ],
    actions: [
      {
        id: "act_chaos_test",
        title: "Execute 72h WAN Partition Chaos Test in Staging",
        objective: "Validate Raft leader re-election and commit latency under simulated 10% packet drop.",
        description: "Deploy chaos mesh agents in staging to inject latency between US-East and EU-West regions while pushing 50k write requests.",
        priority: "critical",
        responsible_role: "Staff Infrastructure Engineer",
        time_horizon: "immediate",
        dependencies: ["Provisioning of staging cluster", "Synthetic traffic generator deployment"],
        success_metrics: [
          "Zero lost transactions during node failure",
          "Leader election completes in under 2.5 seconds",
          "p99 write latency stabilizes under 20ms",
        ],
        risk_mitigations: [
          "Automated test kill-switch if staging error rate exceeds 0.5%",
          "Isolated VPC with dedicated transit gateways",
        ],
        fallback_action: "If latency exceeds 25ms, halt migration plan and re-evaluate vertical PostgreSQL scaling option.",
        decision_gates: [
          {
            id: "gate_chaos_pass",
            condition: "Cross-region commit latency under 10% packet drop must remain <= 20ms p99 across 72 continuous hours.",
            target_milestone: "Stage 1: Staging Chaos Audit",
            verification_method: "Automated Prometheus latency histogram export audited by Infrastructure Lead.",
            fallback_action: "Abort CockroachDB cutover; activate vertical PostgreSQL read-replica optimization plan.",
          },
        ],
      },
      {
        id: "act_canary_rollout",
        title: "Canary Rollout for Non-Critical Read/Write Services",
        objective: "Direct 5% of production analytics and audit log writes to CockroachDB cluster.",
        description: "Deploy dual-write proxy with shadow validation to test real-world database behavior without risking core billing data.",
        priority: "high",
        responsible_role: "Backend Platform Lead",
        time_horizon: "near_term",
        dependencies: ["act_chaos_test"],
        success_metrics: [
          "Data consistency between PostgreSQL and CockroachDB shadow tables matches 100%",
          "Error rate on canary writes < 0.001%",
        ],
        risk_mitigations: [
          "Instant dual-write bypass switch to revert to PostgreSQL within 100ms",
        ],
        fallback_action: "Flip dual-write proxy toggle to route 100% of traffic back to PostgreSQL.",
        decision_gates: [
          {
            id: "gate_canary_integrity",
            condition: "Zero data drift detected between primary PostgreSQL and CockroachDB shadow replicas over 14 consecutive days.",
            target_milestone: "Stage 2: Canary Cutover",
            verification_method: "Hourly cryptographic checksum diff run by automated validation worker.",
            fallback_action: "Drain canary traffic immediately back to PostgreSQL and file P1 bug with database provider.",
          },
        ],
      },
    ],
  },
  created_at: "2026-03-05T10:30:00Z",
};

// ------------------------------------------------------------------------------
// Test Suite Execution
// ------------------------------------------------------------------------------

describe("Phase 5.3: Executive Recommendation Dashboard", () => {
  // Test 1: Full Recommendation Dashboard Rendering
  test("1. Full recommendation dashboard renders all 5 primary sections", () => {
    const html = renderToStaticMarkup(
      React.createElement(RecommendationDashboard, {
        recommendation: MOCK_RECOMMENDATION,
        decisionModel: MOCK_DECISION_MODEL,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        reasoningBoard: MOCK_REASONING_BOARD,
      })
    );

    // Section 1: Executive Hero
    assert.match(html, /Recommended Course of Action/);
    assert.match(html, /Execute a 60-day phased pilot migration/);
    assert.match(html, /Conditional Approval/);
    assert.match(html, /Executive Rationale &amp; Strategic Alignment/);

    // Section 2: Uncertainty & Decision Readiness
    assert.match(html, /Uncertainty &amp; Decision Readiness/);
    assert.match(html, /Strong Evidence/);
    assert.match(html, /Conditional Readiness/);
    assert.match(html, /High Stability/);

    // Section 3: Action Roadmap & Decision Gates
    assert.match(html, /Action Roadmap &amp; Execution Plan/);
    assert.match(html, /Execute 72h WAN Partition Chaos Test in Staging/);
    assert.match(html, /Canary Rollout for Non-Critical Read\/Write Services/);

    // Section 4: Alternative Courses
    assert.match(html, /Alternative Courses of Action Evaluated/);
    assert.match(html, /Scale PostgreSQL Vertically with Read Replicas/);
    assert.match(html, /Defer Migration to Next Fiscal Year/);

    // Section 5: Evidence Traceability
    assert.match(html, /Evidence Traceability &amp; Deliberative Linkages/);
    assert.match(html, /item_write_iops/);
    assert.match(html, /dis_wan_cost_risk/);
  });

  // Test 2: All 6 Decision Statuses Render Correctly with Human-Readable Labels
  test("2. All six decision statuses render with correct badges and text", () => {
    const statuses = [
      { status: "proceed", label: "Proceed", isApproval: true },
      { status: "conditional", label: "Conditional Approval", isApproval: true },
      { status: "pilot", label: "Pilot / Phased Rollout", isApproval: true },
      { status: "defer", label: "Defer Decision", isApproval: false },
      { status: "reject", label: "Do Not Proceed", isApproval: false },
      { status: "insufficient_evidence", label: "Insufficient Evidence", isApproval: false },
    ];

    for (const item of statuses) {
      const cfg = getStatusConfig(item.status);
      assert.equal(cfg.label, item.label);
      assert.equal(cfg.isApproval, item.isApproval);

      const modifiedRec = {
        ...MOCK_RECOMMENDATION,
        decision_status: item.status,
      };

      const html = renderToStaticMarkup(
        React.createElement(ExecutiveRecommendationHero, {
          recommendation: modifiedRec,
        })
      );

      assert.match(html, new RegExp(item.label));
    }
  });

  // Test 3: Insufficient-Evidence Displays Prominent Warning & High Strategic Caution
  test("3. Insufficient evidence displays prominent warning and explanation", () => {
    const insufficientRec = {
      ...MOCK_RECOMMENDATION,
      decision_status: "insufficient_evidence",
    };

    const html = renderToStaticMarkup(
      React.createElement(ExecutiveRecommendationHero, {
        recommendation: insufficientRec,
      })
    );

    assert.match(html, /Insufficient Evidence/);
    assert.match(html, /Evidence Inconclusive — High Strategic Caution Required/);
    assert.match(html, /The available evidence gathered across consulted sources does not justify a confident/);
  });

  // Test 4: Uncertainty Assessment Displays Categorical Enums Without Fake Numbers
  test("4. Uncertainty assessment renders categorical values without fabricated numbers", () => {
    const html = renderToStaticMarkup(
      React.createElement(UncertaintyReadinessSection, {
        uncertainty: MOCK_RECOMMENDATION.uncertainty_assessment,
        decisionModel: MOCK_DECISION_MODEL,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
      })
    );

    // Categorical checks
    assert.match(html, /Strong Evidence/);
    assert.match(html, /Conditional Readiness/);
    assert.match(html, /High Stability/);

    // Explanations of difference
    assert.match(html, /Measures empirical backing across requirements and sources/);
    assert.match(html, /Measures operational and stakeholder clearance to execute now/);
    assert.match(html, /Sensitivity to shifts in baseline assumptions or new findings/);
    assert.match(html, /A recommendation can be actionable while still conditional/);

    // Conditions changing recommendation
    assert.match(html, /Conditions That Would Change the Recommendation/);
    assert.match(html, /If cross-region p99 latency consistently exceeds 30ms/);

    // Critical missing info
    assert.match(html, /Critical Missing Information/);
    assert.match(html, /72-hour sustained chaos telemetry for multi-region failover/);

    // Resolved assumptions & gaps
    assert.match(html, /assump_raft_scale/);
    assert.match(html, /gap_wan_chaos/);

    // No fabricated confidence percentage (e.g. "87% confidence")
    assert.doesNotMatch(html, /\b\d{1,3}% confidence\b/i);
    assert.doesNotMatch(html, /\brisk score:\s*\d+/i);
  });

  // Test 5: Action Roadmap Renders Time Horizons, Roles, Dependencies & Metrics
  test("5. Action roadmap renders structured sequence, roles, dependencies and metrics", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionRoadmapSection, {
        actionPlan: MOCK_RECOMMENDATION.action_plan,
      })
    );

    // Plan summary & milestones
    assert.match(html, /A 4-phase rollout commencing with staging chaos validation/);
    assert.match(html, /Stage 1: Multi-Region Staging Benchmark &amp; Chaos Audit/);
    assert.match(html, /Stage 2: Non-Critical Microservice Canary Cutover/);

    // Action 1 details
    assert.match(html, /Execute 72h WAN Partition Chaos Test in Staging/);
    assert.match(html, /Staff Infrastructure Engineer/);
    assert.match(html, /Critical Priority/);
    assert.match(html, /Immediate/);
    assert.match(html, /Provisioning of staging cluster/);
    assert.match(html, /Zero lost transactions during node failure/);
    assert.match(html, /Fallback \/ Contingency Action/);

    // Action 2 details
    assert.match(html, /Canary Rollout for Non-Critical Read\/Write Services/);
    assert.match(html, /Backend Platform Lead/);
    assert.match(html, /High Priority/);
    assert.match(html, /Near-Term/);
    assert.match(html, /act_chaos_test/);
  });

  // Test 6: Decision Gates Render Prerequisite Conditions and Fallbacks
  test("6. DecisionGateCard renders condition, milestone, verification and fallback", () => {
    const gate = MOCK_RECOMMENDATION.action_plan.actions[0].decision_gates[0];
    const html = renderToStaticMarkup(
      React.createElement(DecisionGateCard, {
        gate,
        index: 0,
      })
    );

    assert.match(html, /DECISION GATE #1/);
    assert.match(html, /Milestone:.*Stage 1: Staging Chaos Audit/);
    assert.match(html, /Gate Prerequisite Condition/);
    assert.match(html, /Cross-region commit latency under 10% packet drop must remain &lt;= 20ms p99/);
    assert.match(html, /Verification &amp; Audit Method/);
    assert.match(html, /Automated Prometheus latency histogram export/);
    assert.match(html, /Fallback if Condition Fails/);
    assert.match(html, /Abort CockroachDB cutover; activate vertical PostgreSQL/);
  });

  // Test 7: Alternative Options Section Distinguishes Primary from Rejected Paths
  test("7. AlternativeOptionsSection displays tradeoffs and why not recommended", () => {
    const html = renderToStaticMarkup(
      React.createElement(AlternativeOptionsSection, {
        alternatives: MOCK_RECOMMENDATION.alternative_options,
        primaryRecommendedAction: MOCK_RECOMMENDATION.recommended_action,
      })
    );

    // Primary baseline context
    assert.match(html, /Primary Chosen Course/);
    assert.match(html, /Execute a 60-day phased pilot migration/);

    // Alternative 1
    assert.match(html, /Scale PostgreSQL Vertically with Read Replicas/);
    assert.match(html, /Hard ceiling on single-node transactional write IOPS capped at ~28,000/);
    assert.match(html, /Why Deprioritized \/ Not Recommended/);
    assert.match(html, /Fails to meet primary objective of 50,000 writes\/sec by year end/);

    // Alternative 2
    assert.match(html, /Defer Migration to Next Fiscal Year/);
    assert.match(html, /Telemetry trends project 98% write buffer utilization within 4 months/);
  });

  // Test 8: Evidence Traceability Resolves IDs to Real Data and Handles Unknown IDs Safely
  test("8. Evidence traceability resolves known IDs and gracefully handles unknown IDs", () => {
    // 8a. Resolvers with existing package
    const resolvedItem = resolveEvidenceItem("item_write_iops", MOCK_EVIDENCE_PACKAGE);
    assert.equal(resolvedItem.found, true);
    assert.match(resolvedItem.content, /54,200 writes\/sec/);
    assert.equal(resolvedItem.sourceTitle, "Distributed Database Benchmark 2026");

    const resolvedAssump = resolveAssumption("assump_raft_scale", MOCK_DECISION_MODEL);
    assert.equal(resolvedAssump.found, true);
    assert.match(resolvedAssump.statement, /Raft consensus horizontally scales/);

    const resolvedGap = resolveEvidenceGap("gap_wan_chaos", MOCK_EVIDENCE_PACKAGE);
    assert.equal(resolvedGap.found, true);
    assert.match(resolvedGap.description, /Lack of 72-hour sustained chaos telemetry/);

    const resolvedDis = resolveDisagreement("dis_wan_cost_risk", MOCK_REASONING_BOARD);
    assert.equal(resolvedDis.found, true);
    assert.match(resolvedDis.topic, /Cross-region operational risk vs performance headroom/);

    // 8b. Resolvers with unknown IDs
    const unknownItem = resolveEvidenceItem("item_nonexistent", MOCK_EVIDENCE_PACKAGE);
    assert.equal(unknownItem.found, false);
    assert.equal(unknownItem.id, "item_nonexistent");

    const unknownAssump = resolveAssumption("assump_nonexistent", MOCK_DECISION_MODEL);
    assert.equal(unknownAssump.found, false);
    assert.equal(unknownAssump.id, "assump_nonexistent");

    // 8c. Component rendering
    const html = renderToStaticMarkup(
      React.createElement(EvidenceTraceabilitySection, {
        recommendation: MOCK_RECOMMENDATION,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
        reasoningBoard: MOCK_REASONING_BOARD,
      })
    );

    assert.match(html, /item_write_iops/);
    assert.match(html, /54,200 writes\/sec/);
    assert.match(html, /dis_wan_cost_risk/);
    assert.match(html, /Cross-region operational risk vs performance headroom/);
    assert.match(html, /assump_raft_scale/);
    assert.match(html, /gap_wan_chaos/);
  });

  // Test 9: Partial-Success State Shows Clear Message and Preserves Stages 1-3
  test("9. Partial-success state shows exact required message and preserves Days 1-3 sections", () => {
    const partialResult = {
      analysis_id: "ana_part_123",
      status: "partial_success",
      question: "Should we migrate to CockroachDB?",
      message: "Partial execution summary.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: MOCK_REASONING_BOARD,
      recommendation: null,
      recommendation_status: "unavailable",
      recommendation_error: "LLM recommendation generation exceeded operation timeout ceiling.",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: partialResult,
        onReset: () => {},
      })
    );

    // Required exact wording
    assert.match(
      html,
      /The Decision Framer, Evidence Engine, and AI Boardroom completed successfully, but the recommendation could not be generated\./
    );

    // Header says Partial Analysis Complete, not "Analysis Complete"
    assert.match(html, /Partial Analysis Complete/);
    assert.match(html, /partial_success/);

    // Preserved Days 1-3 sections are rendered
    assert.match(html, /Decision &amp; Evidence Report/);
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /id="section-evidence-engine"/);
    assert.match(html, /id="section-ai-boardroom"/);

    // Error context is displayed
    assert.match(html, /LLM recommendation generation exceeded operation timeout ceiling\./);

    // No fake recommendation is shown
    assert.doesNotMatch(html, /Recommended Course of Action/);
  });

  // Test 10: Historical Day 4 Analysis Renders Cleanly Without Error
  test("10. Historical Day 4 analysis without recommendation fields renders smoothly", () => {
    const historicalResult = {
      analysis_id: "ana_hist_456",
      status: "completed",
      question: "Historical Day 4 question?",
      message: "Historical Day 4 synthesis.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: MOCK_REASONING_BOARD,
      recommendation: null,
      recommendation_status: null,
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: historicalResult,
        onReset: () => {},
      })
    );

    // Completed status
    assert.match(html, /Analysis Complete/);
    assert.match(html, /completed/);

    // Day 4 sections rendered
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /id="section-evidence-engine"/);
    assert.match(html, /id="section-ai-boardroom"/);

    // No false Stage 4 failure banner
    assert.doesNotMatch(
      html,
      /The Decision Framer, Evidence Engine, and AI Boardroom completed successfully, but the recommendation could not be generated/
    );
    assert.doesNotMatch(html, /Partial Analysis Complete/);
  });

  // Test 11: Unexpected Inconsistent Data Handled Gracefully Without Crash
  test("11. Inconsistent data (recommendation_status completed but null object) is handled safely", () => {
    const inconsistentResult = {
      analysis_id: "ana_incon_789",
      status: "completed",
      question: "Inconsistent state test question?",
      message: "Synthesis present.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: MOCK_REASONING_BOARD,
      recommendation: null,
      recommendation_status: "completed",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: inconsistentResult,
        onReset: () => {},
      })
    );

    assert.match(html, /Inconsistent Recommendation State Detected/);
    assert.match(html, /recommendation payload was missing from the response/);
    // Preserves Day 4 sections
    assert.match(html, /id="section-decision-model"/);
  });

  // Test 12: StageAwareProgress Shows Stage 4 Recommendation Progress
  test("12. StageAwareProgress displays stage4_recommendation progress step", () => {
    const html = renderToStaticMarkup(
      React.createElement(StageAwareProgress, {
        status: "running",
        stage: "stage4_recommendation",
        progressMessage: "Formulating evidence-linked recommendation and action plan...",
        jobId: "job_rec_999",
      })
    );

    assert.match(html, /Recommending course of action/);
    assert.match(html, /Formulating evidence-linked recommendation and action plan/);
    assert.match(html, /job_rec_999/);
    assert.match(html, /Analysis in Progress/);
  });

  // Test 13: Export & Print Compatibility and Anchor Links
  test("13. AnalysisResultCard provides Export / Print action and traceability anchor IDs", () => {
    const fullResult = {
      analysis_id: "ana_full_001",
      status: "completed",
      question: "Full result test question?",
      message: "Synthesis message.",
      decision_model: MOCK_DECISION_MODEL,
      evidence_package: MOCK_EVIDENCE_PACKAGE,
      reasoning_board: MOCK_REASONING_BOARD,
      recommendation: MOCK_RECOMMENDATION,
      recommendation_status: "completed",
    };

    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: fullResult,
        onReset: () => {},
      })
    );

    // Print button exists
    assert.match(html, /Export \/ Print/);

    // Traceability anchor IDs exist on target sections
    assert.match(html, /id="section-uncertainty-readiness"/);
    assert.match(html, /id="section-action-roadmap"/);
    assert.match(html, /id="section-alternative-options"/);
    assert.match(html, /id="section-evidence-traceability"/);
    assert.match(html, /id="section-decision-model"/);
    assert.match(html, /id="section-evidence-engine"/);
    assert.match(html, /id="section-evidence-requirements"/);
    assert.match(html, /id="section-evidence-gaps"/);
    assert.match(html, /id="section-ai-boardroom"/);
  });

  // Test 14: Accessibility and ARIA Attributes
  test("14. Accessible landmarks, headings, and ARIA attributes are strictly maintained", () => {
    const html = renderToStaticMarkup(
      React.createElement(RecommendationDashboard, {
        recommendation: MOCK_RECOMMENDATION,
        decisionModel: MOCK_DECISION_MODEL,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        reasoningBoard: MOCK_REASONING_BOARD,
      })
    );

    // Regions and landmarks
    assert.match(html, /aria-label="Executive Recommendation Dashboard"/);
    assert.match(html, /aria-labelledby="executive-recommendation-heading"/);
    assert.match(html, /aria-labelledby="uncertainty-readiness-heading"/);
    assert.match(html, /aria-labelledby="action-roadmap-heading"/);
    assert.match(html, /aria-labelledby="alternative-options-heading"/);
    assert.match(html, /aria-labelledby="evidence-traceability-heading"/);
    assert.match(html, /role="region"/);
    assert.match(html, /aria-expanded="false"/);

    // Headings structure (h2 for recommended action, h3 for sections, h4 for items)
    assert.match(html, /<h2 id="executive-recommendation-heading"/);
    assert.match(html, /<h3 id="uncertainty-readiness-heading"/);
    assert.match(html, /<h3 id="action-roadmap-heading"/);
    assert.match(html, /<h3 id="alternative-options-heading"/);
    assert.match(html, /<h3 id="evidence-traceability-heading"/);
  });
});
