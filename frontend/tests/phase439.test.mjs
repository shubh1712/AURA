import { test, describe, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components built for Phase 4.39
import { StageAwareProgress } from "../src/components/decision/StageAwareProgress.tsx";
import { PerspectiveCard } from "../src/components/decision/boardroom/PerspectiveCard.tsx";
import { DisagreementsSection } from "../src/components/decision/boardroom/DisagreementsSection.tsx";
import { BoardSynthesisSection } from "../src/components/decision/boardroom/BoardSynthesisSection.tsx";
import { ReasoningBoardSection } from "../src/components/decision/boardroom/ReasoningBoardSection.tsx";
import {
  createAnalysisJob,
  getAnalysisJobStatus,
  getAnalysisJobResult,
  ApiClientError,
} from "../src/lib/api.ts";

// ------------------------------------------------------------------------------
// Canonical Test Fixtures derived strictly from backend app.schemas
// ------------------------------------------------------------------------------

const MOCK_DECISION_MODEL = {
  id: "model_test_123",
  decision: {
    raw_prompt: "Should we migrate from PostgreSQL to a distributed SQL cluster?",
    summary: "Evaluation of distributed SQL cluster migration versus optimizing PostgreSQL.",
    decision_type: "architecture_technology",
    time_horizon: "medium_term",
  },
  complexity: {
    level: "high",
    reasoning: "Complex distributed transactional requirements.",
    reversibility: "partially_reversible",
  },
  objectives: [
    {
      id: "obj_perf",
      description: "Support 50k write ops/sec",
      is_primary: true,
      target_metric: "50,000 writes/sec",
      provenance: "user_provided",
    },
  ],
  variables: [
    {
      id: "var_write_throughput",
      name: "Write Throughput",
      description: "Peak peak transactional writes per second",
      variable_type: "numeric",
      unit: "ops/sec",
      is_controllable: false,
      provenance: "user_provided",
    },
  ],
  constraints: [
    {
      id: "cons_budget",
      name: "Infra Budget",
      description: "Monthly infrastructure budget capped at $40,000",
      is_hard_constraint: true,
      source: "User input",
      provenance: "user_provided",
    },
  ],
  stakeholders: [],
  tradeoffs: [],
  assumptions: [
    {
      id: "assump_cluster_scale",
      statement: "Distributed cluster horizontally scales write IOPS linearly.",
      confidence: "high",
      falsification_condition: "Benchmarking reveals Raft consensus bottleneck.",
      provenance: "inferred",
    },
    {
      id: "assump_staff_skill",
      statement: "Internal DevOps team can maintain distributed consensus without additional hires.",
      confidence: "medium",
      provenance: "inferred",
    },
  ],
  unknowns: [
    {
      id: "unk_cross_region_lat",
      question: "What is the cross-region p99 write latency under network degradation?",
      criticality: "high",
      potential_sources: ["Benchmarking harness", "Cloud vendor SLAs"],
      provenance: "inferred",
    },
  ],
  key_questions: [],
};

const MOCK_EVIDENCE_PACKAGE = {
  id: "pkg_test_456",
  decision_model_id: "model_test_123",
  requirements: [
    {
      id: "req_perf_benchmark",
      target_entity_id: "var_write_throughput",
      target_entity_type: "variable",
      kind: "external_research",
      description: "Empirical write throughput benchmarks for distributed SQL engines.",
      priority: "high",
      status: "fulfilled",
      suggested_queries: ["distributed sql write benchmark 50k"],
    },
  ],
  sources: [
    {
      id: "src_vldb_paper",
      title: "Distributed Transaction Benchmarks at Hyperscale (VLDB 2024)",
      url: "https://example.org/vldb-distributed-sql-2024",
      publisher: "VLDB Endowment",
      source_type: "academic",
      retrieval_timestamp: "2026-10-09T18:00:00Z",
    },
  ],
  items: [
    {
      id: "ev_item_raft_perf",
      source_id: "src_vldb_paper",
      content: "Distributed SQL multi-Raft groups achieve 65,000 write ops/sec across 5 storage nodes.",
      summary: "Evaluates multi-Raft write throughput.",
      numeric_data: [
        {
          metric_name: "Write IOPS",
          value: 65000,
          unit: "ops/sec",
        },
      ],
      extraction_confidence: "high",
      retrieval_timestamp: "2026-10-09T18:00:00Z",
    },
  ],
  claim_links: [],
  gaps: [
    {
      id: "gap_cluster_cost",
      gap_type: "insufficient_evidence",
      target_entity_id: "cons_budget",
      target_entity_type: "constraint",
      description: "Lack of public pricing data for enterprise 24/7 support contracts.",
      impact: "high",
      conflicting_evidence_ids: [],
    },
  ],
  summary: "Comprehensive evidence package covering distributed cluster performance.",
  created_at: "2026-10-09T18:00:00Z",
};

const MOCK_CANONICAL_PERSPECTIVES = [
  {
    id: "persp_growth",
    perspective_type: "growth",
    summary: "Horizontal scaling unlocks market expansion into multi-region enterprise tiers.",
    arguments: [
      {
        id: "arg_growth_01",
        claim: "Distributed cluster eliminates transactional write throughput limits for 10x growth.",
        direction: "favorable",
        basis: "evidence",
        reasoning: "Empirical benchmarks demonstrate 65k writes/sec, well beyond the 50k threshold.",
        evidence_item_ids: ["ev_item_raft_perf"],
        requirement_ids: ["req_perf_benchmark"],
        assumption_ids: ["assump_cluster_scale"],
        unknown_ids: [],
        evidence_gap_ids: [],
        related_entity_ids: ["var_write_throughput"],
        caveat: "Requires dedicated partition management.",
      },
    ],
    critical_assumption_ids: ["assump_cluster_scale"],
    evidence_gap_ids: [],
    unresolved_questions: ["How quickly can new regional shards be provisioned?"],
    limitations: ["Does not evaluate ongoing infrastructure run rates."],
    opportunities: ["Enables frictionless onboarding of global multi-tenant accounts."],
    concerns: ["Operational ramp-up could delay product feature delivery."],
  },
  {
    id: "persp_finance",
    perspective_type: "finance",
    summary: "Significant enterprise license and compute overhead threatens unit economics.",
    arguments: [
      {
        id: "arg_finance_01",
        claim: "Managed distributed SQL cluster expenses likely exceed the $40,000 monthly ceiling.",
        direction: "unfavorable",
        basis: "unresolved",
        reasoning: "Support contract quotes are currently missing from verified vendor filings.",
        evidence_item_ids: [],
        requirement_ids: [],
        assumption_ids: [],
        unknown_ids: [],
        evidence_gap_ids: ["gap_cluster_cost"],
        related_entity_ids: ["cons_budget"],
      },
    ],
    critical_assumption_ids: [],
    evidence_gap_ids: ["gap_cluster_cost"],
    unresolved_questions: ["What is the total multi-year license and enterprise SLA cost?"],
    limitations: ["Omits potential revenue upside from new high-tier customer SLAs."],
    opportunities: ["Consolidation of analytical and transactional clusters could offset costs."],
    concerns: ["Overcommitting capital before reaching product-market scale."],
  },
  {
    id: "persp_customer",
    perspective_type: "customer",
    summary: "Global user experience improves with geo-partitioned reads, but schema migration risks downtime.",
    arguments: [
      {
        id: "arg_customer_01",
        claim: "Geo-distributed nodes deliver sub-50ms latency to overseas users.",
        direction: "favorable",
        basis: "inference",
        reasoning: "Proximity to edge gateways consistently lowers user-perceived interactive latency.",
        evidence_item_ids: [],
        requirement_ids: [],
        assumption_ids: [],
        unknown_ids: [],
        evidence_gap_ids: [],
        related_entity_ids: [],
      },
    ],
    critical_assumption_ids: [],
    evidence_gap_ids: [],
    unresolved_questions: ["Will users experience read-after-write replication lags?"],
    limitations: ["Relies on theoretical network topology without customer telemetry."],
    opportunities: ["Near-zero latency for international customer expansion."],
    concerns: ["Migration maintenance windows could cause customer trust erosion."],
  },
  {
    id: "persp_risk",
    perspective_type: "risk",
    summary: "High architectural complexity, split-brain failure modes, and low migration reversibility.",
    arguments: [
      {
        id: "arg_risk_01",
        claim: "Distributed transaction rollback is difficult once schemas diverge from single-node PostgreSQL.",
        direction: "unfavorable",
        basis: "assumption",
        reasoning: "Proprietary distributed extensions prevent seamless failback to standard PostgreSQL.",
        evidence_item_ids: [],
        requirement_ids: [],
        assumption_ids: ["assump_staff_skill"],
        unknown_ids: ["unk_cross_region_lat"],
        evidence_gap_ids: [],
        related_entity_ids: [],
        caveat: "Contingent on dual-write synchronization architecture.",
      },
    ],
    critical_assumption_ids: ["assump_staff_skill"],
    evidence_gap_ids: [],
    unresolved_questions: ["What is the audited recovery time objective (RTO) during network partition?"],
    limitations: ["Assumes worst-case infrastructure disruption scenarios."],
    opportunities: ["Forces establishment of rigorous automated disaster recovery drills."],
    concerns: ["Severe blast radius during split-brain quorum failure."],
  },
];

const MOCK_REASONING_BOARD = {
  id: "board_test_789",
  decision_model_id: "model_test_123",
  evidence_package_id: "pkg_test_456",
  perspectives: MOCK_CANONICAL_PERSPECTIVES,
  disagreements: [
    {
      id: "dis_growth_vs_finance_01",
      topic: "Scaling Velocity vs. Capital Commitment",
      perspective_ids: ["growth", "finance"],
      argument_ids: ["arg_growth_01", "arg_finance_01"],
      positions: {
        growth: "Prioritize 10x throughput scalability to prevent revenue plateaus.",
        finance: "Constrain infrastructure expenditure within $40k/month to protect operating margins.",
      },
      evidence_item_ids: ["ev_item_raft_perf"],
      assumption_ids: ["assump_cluster_scale"],
      evidence_gap_ids: ["gap_cluster_cost"],
      nature: "evidence_dependent",
    },
  ],
  synthesis: {
    summary: "The boardroom converges on the technical feasibility of distributed scaling, but sharp tensions remain between top-line expansion and unverified managed run rates.",
    areas_of_agreement: [
      "Current single-node PostgreSQL will reach saturated write limits at 50,000 writes/sec.",
      "A distributed cluster satisfies long-term multi-region architecture requirements.",
    ],
    disagreement_ids: ["dis_growth_vs_finance_01"],
    critical_assumption_ids: ["assump_cluster_scale", "assump_staff_skill"],
    critical_evidence_gap_ids: ["gap_cluster_cost"],
    evidence_sensitive_points: [
      "Binding enterprise quote for managed distributed cluster support contracts.",
      "Direct benchmark of cross-region Raft quorum latency under simulated link degradation.",
    ],
    unresolved_questions: [
      "Can the existing team operate the cluster without adding $200k+ in payroll overhead?",
      "Does the projected revenue growth rate justify immediate cluster migration in Q4?",
    ],
  },
  created_at: "2026-10-09T18:00:00Z",
};

const MOCK_ANALYSIS_RESPONSE = {
  analysis_id: "analysis_test_999",
  decision_model_id: "model_test_123",
  question: "Should we migrate from PostgreSQL to a distributed SQL cluster?",
  status: "completed",
  message: "Analysis and boardroom deliberation successfully completed.",
  decision_model: MOCK_DECISION_MODEL,
  evidence_package: MOCK_EVIDENCE_PACKAGE,
  reasoning_board: MOCK_REASONING_BOARD,
};

// ------------------------------------------------------------------------------
// Test Suite Execution
// ------------------------------------------------------------------------------

describe("Phase 4.39: AI Boardroom & Async Job Integration", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  // 1. API Client: Job Creation
  test("1. createAnalysisJob successfully posts request and returns 202 job metadata", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url.toString(), /\/api\/analysis\/jobs$/);
      assert.equal(options.method, "POST");
      const body = JSON.parse(options.body);
      assert.equal(body.question, "Should we migrate?");
      return new Response(
        JSON.stringify({
          job_id: "job_uuid_123",
          status: "queued",
          stage: "queued",
          created_at: "2026-10-09T18:00:00Z",
          timeout_seconds: 180,
          progress_message: "Job queued for processing",
        }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      );
    };

    const res = await createAnalysisJob({ question: "Should we migrate?" });
    assert.equal(res.job_id, "job_uuid_123");
    assert.equal(res.status, "queued");
    assert.equal(res.stage, "queued");
  });

  // 2. API Client: Polling Status & Stage Transitions
  test("2. getAnalysisJobStatus polls pipeline stages correctly", async () => {
    const stages = [
      "queued",
      "stage1_decision_framer",
      "stage2_evidence_engine",
      "stage3_ai_boardroom",
      "completed",
    ];

    for (const stage of stages) {
      globalThis.fetch = async (url) => {
        assert.match(url.toString(), /\/api\/analysis\/jobs\/job_uuid_123$/);
        return new Response(
          JSON.stringify({
            job_id: "job_uuid_123",
            status: stage === "completed" ? "succeeded" : stage === "queued" ? "queued" : "running",
            stage: stage,
            created_at: "2026-10-09T18:00:00Z",
            timeout_seconds: 180,
            progress_message: `Active stage: ${stage}`,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const res = await getAnalysisJobStatus("job_uuid_123");
      assert.equal(res.stage, stage);
      if (stage === "completed") {
        assert.equal(res.status, "succeeded");
      }
    }
  });

  // 3. API Client: Result Retrieval
  test("3. getAnalysisJobResult retrieves validated AnalysisResponse", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url.toString(), /\/api\/analysis\/jobs\/job_uuid_123\/result$/);
      return new Response(JSON.stringify(MOCK_ANALYSIS_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const result = await getAnalysisJobResult("job_uuid_123");
    assert.equal(result.analysis_id, "analysis_test_999");
    assert.ok(result.reasoning_board);
    assert.equal(result.reasoning_board.perspectives.length, 4);
  });

  // 4. API Client: Error Handling (504 Timeout, 409 Conflict, 500)
  test("4. API client handles HTTP 504 timeout and HTTP 409 conflict appropriately", async () => {
    // 504 Timeout
    globalThis.fetch = async () => {
      return new Response(
        JSON.stringify({
          detail: {
            message: "Decision analysis deadline exceeded",
            job_id: "job_uuid_123",
          },
        }),
        { status: 504, headers: { "Content-Type": "application/json" } }
      );
    };

    await assert.rejects(
      async () => await getAnalysisJobResult("job_uuid_123"),
      (err) => {
        assert.ok(err instanceof ApiClientError);
        assert.equal(err.statusCode, 504);
        assert.match(err.message, /processing time/i);
        return true;
      }
    );

    // 409 Job Still In Progress
    globalThis.fetch = async () => {
      return new Response(
        JSON.stringify({
          detail: "Analysis job is still running",
        }),
        { status: 409, headers: { "Content-Type": "application/json" } }
      );
    };

    await assert.rejects(
      async () => await getAnalysisJobResult("job_uuid_123"),
      (err) => {
        assert.ok(err instanceof ApiClientError);
        assert.equal(err.statusCode, 409);
        assert.match(err.message, /still running/i);
        return true;
      }
    );
  });

  // 5. API Client: Malformed Response Handling
  test("5. API client handles malformed non-JSON responses safely", async () => {
    globalThis.fetch = async () => {
      return new Response("<html>Gateway 502 Bad Gateway</html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      });
    };

    await assert.rejects(
      async () => await getAnalysisJobStatus("job_uuid_123"),
      (err) => {
        assert.ok(err instanceof ApiClientError);
        assert.equal(err.statusCode, 502);
        return true;
      }
    );
  });

  // 6. UI: Stage-Aware Progress Component (Truthful loading, no fake percentages, retry on failure)
  test("6. StageAwareProgress displays correct stages and accessible landmarks without fake percentages", () => {
    const htmlRunning = renderToStaticMarkup(
      React.createElement(StageAwareProgress, {
        status: "running",
        stage: "stage2_evidence_engine",
        progressMessage: "Retrieving sources and mapping findings",
        jobId: "job-abc-123",
      })
    );

    assert.ok(htmlRunning.includes("role=\"status\""));
    assert.ok(htmlRunning.includes("aria-live=\"polite\""));
    assert.ok(htmlRunning.includes("Analysis in Progress"));
    assert.ok(htmlRunning.includes("job-abc-123"));
    assert.ok(htmlRunning.includes("Gathering and evaluating evidence"));
    assert.ok(htmlRunning.includes("Retrieving sources and mapping findings"));
    // Ensure no invented percentage metrics
    assert.ok(!htmlRunning.includes("%"));

    // Test Failure with Retry
    const htmlFailed = renderToStaticMarkup(
      React.createElement(StageAwareProgress, {
        status: "failed",
        stage: "stage2_evidence_engine",
        error: "Failed to map empirical evidence",
        errorStatusCode: 500,
        jobId: "job-abc-123",
        onRetry: () => {},
      })
    );

    assert.ok(htmlFailed.includes("Analysis Interrupted"));
    assert.ok(htmlFailed.includes("Failed to map empirical evidence"));
    assert.ok(htmlFailed.includes("Retry Analysis"));
  });

  // 7. UI: Four Canonical Perspective Cards
  test("7. PerspectiveCard renders all canonical perspective fields and distinguishes lenses", () => {
    for (const persp of MOCK_CANONICAL_PERSPECTIVES) {
      const html = renderToStaticMarkup(
        React.createElement(PerspectiveCard, {
          perspective: persp,
          evidencePackage: MOCK_EVIDENCE_PACKAGE,
          decisionModel: MOCK_DECISION_MODEL,
        })
      );

      // Must display perspective name and role
      assert.ok(html.includes(persp.perspective_type.toUpperCase()) || html.includes(persp.perspective_type));
      assert.ok(html.includes(persp.summary));

      // Must display arguments
      for (const arg of persp.arguments) {
        assert.ok(html.includes(arg.claim));
        assert.ok(html.includes(arg.reasoning));
      }

      // Must verify NO voting, synthetic score, or recommendation widgets
      assert.ok(!html.includes("Vote"));
      assert.ok(!html.includes("Consensus:"));
      assert.ok(!html.includes("Final Recommendation"));
      assert.ok(!html.includes("Resilience Score"));
    }
  });

  // 8. UI: Disagreement Section Rendering
  test("8. DisagreementsSection renders dialectical tensions, stances, and root causes", () => {
    const html = renderToStaticMarkup(
      React.createElement(DisagreementsSection, {
        disagreements: MOCK_REASONING_BOARD.disagreements,
      })
    );

    assert.ok(html.includes("Where the Perspectives Disagree"));
    assert.ok(html.includes("Scaling Velocity vs. Capital Commitment"));
    assert.ok(html.includes("Evidence-Dependent"));
    assert.ok(html.includes("Prioritize 10x throughput scalability"));
    assert.ok(html.includes("Constrain infrastructure expenditure"));
    assert.ok(html.includes("ev_item_raft_perf"));
    assert.ok(html.includes("assump_cluster_scale"));
    assert.ok(html.includes("gap_cluster_cost"));
  });

  // 9. UI: Board Synthesis Section Rendering
  test("9. BoardSynthesisSection renders reconciliation narrative, agreements, dependencies, and questions", () => {
    const html = renderToStaticMarkup(
      React.createElement(BoardSynthesisSection, {
        synthesis: MOCK_REASONING_BOARD.synthesis,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
      })
    );

    assert.ok(html.includes("Board Synthesis &amp; Strategic Alignment"));
    assert.ok(html.includes("The boardroom converges on the technical feasibility"));
    assert.ok(html.includes("Areas of Agreement"));
    assert.ok(html.includes("Current single-node PostgreSQL will reach saturated write limits"));
    assert.ok(html.includes("Evidence-Sensitive Points"));
    assert.ok(html.includes("Binding enterprise quote for managed distributed cluster"));
    assert.ok(html.includes("Critical Assumptions"));
    assert.ok(html.includes("assump_cluster_scale"));
    assert.ok(html.includes("Distributed cluster horizontally scales write IOPS linearly."));
    assert.ok(html.includes("Critical Evidence Gaps"));
    assert.ok(html.includes("gap_cluster_cost"));
    assert.ok(html.includes("Lack of public pricing data for enterprise 24/7 support contracts."));
    assert.ok(html.includes("Unresolved Strategic Questions"));
    assert.ok(html.includes("Can the existing team operate the cluster without adding $200k+"));
  });

  // 10. UI: Evidence Provenance & Missing Reference Handling
  test("10. PerspectiveCard and Synthesis correctly resolve valid references and cleanly indicate missing references", () => {
    // Construct perspective with a valid evidence ID and an invalid unmapped ID
    const perspWithMissingRef = {
      ...MOCK_CANONICAL_PERSPECTIVES[0],
      arguments: [
        {
          id: "arg_test_unmapped",
          claim: "Unmapped reference test argument",
          direction: "favorable",
          basis: "evidence",
          reasoning: "Reasoning with both real and unmapped evidence IDs.",
          evidence_item_ids: ["ev_item_raft_perf", "ev_item_nonexistent_999"],
          requirement_ids: [],
          assumption_ids: ["assump_nonexistent_888"],
          unknown_ids: [],
          evidence_gap_ids: [],
          related_entity_ids: [],
        },
      ],
    };

    const html = renderToStaticMarkup(
      React.createElement(PerspectiveCard, {
        perspective: perspWithMissingRef,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
      })
    );

    // Valid reference should resolve item content / details
    assert.ok(html.includes("ev_item_raft_perf"));
    assert.ok(html.includes("Distributed SQL multi-Raft groups achieve 65,000 write ops/sec"));

    // Missing reference should preserve the exact ID and indicate not found in package without crashing or fabricating
    assert.ok(html.includes("ev_item_nonexistent_999"));
    assert.ok(html.includes("assump_nonexistent_888"));
  });

  // 11. UI: Full ReasoningBoardSection Layout and Accessibility
  test("11. ReasoningBoardSection renders complete boardroom hierarchy with accessible landmarks", () => {
    const html = renderToStaticMarkup(
      React.createElement(ReasoningBoardSection, {
        board: MOCK_REASONING_BOARD,
        evidencePackage: MOCK_EVIDENCE_PACKAGE,
        decisionModel: MOCK_DECISION_MODEL,
      })
    );

    assert.ok(html.includes("AI Boardroom Deliberation"));
    assert.ok(html.includes("4 Canonical Perspectives"));
    assert.ok(html.includes("board_test_789"));
    assert.ok(html.includes("All 4 Perspectives"));

    // Check presence of all 4 perspectives
    assert.ok(html.includes("Growth Perspective"));
    assert.ok(html.includes("Finance Perspective"));
    assert.ok(html.includes("Customer Perspective"));
    assert.ok(html.includes("Risk Perspective"));

    // Check semantic headings
    assert.ok(html.includes("h2"));
    assert.ok(html.includes("h3"));
    assert.ok(html.includes("h4"));
    assert.ok(html.includes("aria-label=\"AI Boardroom Deliberation\""));
  });
});
