import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components built for Phase 8C
import { ActionStrategyOverview } from "../src/components/decision/action/ActionStrategyOverview.tsx";
import { ActionIntelligenceRoadmapSection } from "../src/components/decision/action/ActionRoadmapSection.tsx";
import { ActionDecisionGates } from "../src/components/decision/action/ActionDecisionGates.tsx";
import { ActionValidationWarnings } from "../src/components/decision/action/ActionValidationWarnings.tsx";
import { ActionUnresolvedQuestions } from "../src/components/decision/action/ActionUnresolvedQuestions.tsx";
import { ActionUnavailableBanner } from "../src/components/decision/action/ActionUnavailableBanner.tsx";
import { ActionIntelligenceDashboard } from "../src/components/decision/action/ActionIntelligenceDashboard.tsx";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import {
  getActionPlan,
  getActionPlanStatus,
  generateActionPlan,
  ApiClientError,
} from "../src/lib/api.ts";

// ------------------------------------------------------------------------------
// Test Fixtures
// ------------------------------------------------------------------------------

const MOCK_PLAN = {
  plan_id: "plan_9f83a2c4187e3321556677889900aabb",
  analysis_id: "analysis_123",
  source_recommendation_fingerprint: "srfp_e3b0c44298fc1c149afbf4c8996fb924",
  schema_version: "1.0",
  generator_version: "day8b_v1",
  created_at: "2026-10-12T10:00:00Z",
  strategy_summary: "Comprehensive operational rollout strategy prioritizing controlled pilot deployment before broad cutover.",
  actions: [
    {
      action_id: "act_1",
      source_action_reference: "act_stage4_01",
      title: "Pilot Deployment Setup",
      sequence: 1,
      priority: "high",
      owner_role: "Platform Engineering Lead",
      timing: "Weeks 1-2",
      description: "Deploy initial pilot cohort under strict feature flag limits to validate core service latency.",
      execution_steps: [
        "Step 1: Provision isolated compute worker pool",
        "Step 2: Configure telemetry alerts for error rate breach",
      ],
      dependencies: [],
      prerequisites: ["Security architecture review signed off"],
      success_criteria: [
        {
          criterion_id: "crit_csat",
          criterion_type: "hard_constraint",
          is_hard: true,
          description: "Customer satisfaction floor",
          metric_name: "csat",
          operator: ">=",
          threshold_value: 90.0,
          threshold_raw: "90%",
          unit: "%",
          provenance_type: "decision_model.constraints",
          source_reference: "cnstr_csat_floor",
        },
      ],
      risk_mitigations: ["Automated load shedding if memory consumption exceeds 80%"],
      contingency_or_rollback: "Immediate traffic cutover to legacy standby routing within 60 seconds.",
      evidence_references: ["evi_01"],
      rationale: "Empirical validation with low risk exposure prior to full capital commitment.",
      confidence_label: "high",
      confidence_rationale: "Backed by internal pilot trial data.",
      missing_information: [],
    },
    {
      action_id: "act_2",
      source_action_reference: "act_stage4_02",
      title: "Full Customer Rollout",
      sequence: 2,
      priority: "medium",
      owner_role: "VP of Product",
      timing: "Weeks 3-4",
      description: "Expand deployment to 100% of customer base following Gate 1 review.",
      execution_steps: [
        "Step 1: Expand feature flag to general availability",
        "Step 2: Enable automated billing metering",
      ],
      dependencies: ["act_1", "act_external_unresolved"],
      prerequisites: ["Passed Gate 1 checkpoint verification"],
      success_criteria: [],
      risk_mitigations: [],
      contingency_or_rollback: "Rollback feature flag to pilot cohort only.",
      evidence_references: [],
      rationale: "Scales operational capability to achieve full projected value.",
      confidence_label: "moderate",
      confidence_rationale: "Contingent on pilot feedback.",
      missing_information: ["Long-term customer retention impact under sustained traffic."],
    },
  ],
  decision_gates: [
    {
      gate_id: "gate_1",
      title: "Pilot Verification Gate",
      checkpoint: "End of Week 2 Pilot",
      criteria: [
        {
          criterion_id: "crit_gate_csat",
          criterion_type: "hard_constraint",
          is_hard: true,
          description: "Sustained CSAT at or above 90%",
          threshold_raw: ">= 90%",
          unit: "%",
          source_reference: "cnstr_csat_floor",
        },
        {
          criterion_id: "crit_gate_error",
          criterion_type: "recommendation_target",
          is_hard: false,
          description: "API 5xx error rate under 0.1%",
          threshold_raw: "< 0.1%",
          unit: "%",
        },
      ],
      related_action_ids: ["act_2"],
      failure_response: "Halt pilot and revert traffic routing pending root-cause investigation.",
      source_references: ["cnstr_csat_floor"],
      unresolved_conflicts: ["Support lead raised concern regarding weekend triage coverage."],
    },
  ],
  unresolved_questions: [
    "Will customer support ticket resolution time increase during initial transition?",
  ],
  limitations: [
    "Model assumes current vendor API pricing remains unchanged throughout Q3.",
  ],
  validation_warnings: [
    {
      warning_id: "warn_conflict_01",
      severity: "conflict",
      message: "Direct threshold conflict: Action gate criterion allows CSAT degradation to 85%, violating user hard floor of 90%.",
      related_action_ids: ["act_1"],
      related_gate_ids: ["gate_1"],
      related_criterion_ids: ["crit_csat"],
    },
    {
      warning_id: "warn_review_01",
      severity: "review_required",
      message: "Manual review required: Incompatible units between criterion ('points') and constraint ('%'). Automated comparison cannot be verified.",
      related_action_ids: ["act_2"],
      related_gate_ids: [],
      related_criterion_ids: [],
    },
  ],
  generation_metadata: {},
};

const MOCK_ANALYSIS_RESPONSE = {
  analysis_id: "analysis_123",
  status: "completed",
  question: "Should we roll out the automated AI platform?",
  owner_id: "alice",
  created_at: "2026-10-12T09:00:00Z",
  recommendation_status: "completed",
  scenario_status: "completed",
  resilience_status: "completed",
  decision_model: {
    decision: {
      raw_prompt: "Should we roll out the automated AI platform?",
      summary: "Roll out automated AI platform across customer support.",
      decision_type: "strategic_growth",
      time_horizon: "medium_term",
    },
    complexity: { level: "moderate", reversibility: "reversible" },
    objectives: [],
    variables: [],
    constraints: [],
    tradeoffs: [],
    assumptions: [],
    unknowns: [],
  },
  recommendation: {
    id: "rec_123",
    decision_status: "approve",
    recommended_action: "Proceed with controlled phased rollout.",
    executive_rationale: "Strong empirical evidence supports phased pilot with minimal downside.",
    evidence_strength: "strong",
    decision_readiness: "actionable",
    action_plan: {
      actions: [
        { id: "act_stage4_01", title: "Pilot Deployment Setup", priority: "high", time_horizon: "immediate" },
        { id: "act_stage4_02", title: "Full Customer Rollout", priority: "medium", time_horizon: "near_term" },
      ],
      immediate_actions: [],
      near_term_actions: [],
      long_term_actions: [],
      contingent_actions: [],
    },
    alternative_options: [],
    decision_gates: [],
    uncertainty_assessment: {
      evidence_strength: "strong",
      decision_readiness: "actionable",
      recommendation_stability: "stable",
      residual_uncertainties: [],
    },
  },
  scenarios: {
    scenarios: [
      { id: "scen_1", scenario_type: "base_case", name: "Steady Adoption", probability: 0.6, narrative: "Base case." },
      { id: "scen_2", scenario_type: "optimistic", name: "Rapid Scale", probability: 0.25, narrative: "High upside." },
      { id: "scen_3", scenario_type: "pessimistic", name: "High Churn", probability: 0.15, narrative: "Downside scenario." },
    ],
  },
  resilience: {
    overall_score: 78.5,
    resilience_rating: "high",
    key_vulnerabilities: ["Vendor lock-in"],
  },
};

describe("Phase 8C: Action Intelligence Frontend & User Experience", () => {
  // ----------------------------------------------------------------------------
  // Test 1: Initial Not-Generated State
  // ----------------------------------------------------------------------------
  test("1. Initial not-generated state renders CTA button without automatic generation", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceDashboard, {
        analysisId: "analysis_test_01",
        enabled: false, // Disables background fetch in test
      })
    );

    assert.ok(html.includes("Action Intelligence"), "Must display Action Intelligence section header");
    assert.ok(html.includes("Operationalize Decision Recommendation"), "Must display empty state headline");
    assert.ok(html.includes("id=\"generate-action-plan-btn\""), "Must render Generate Action Plan button with accessible ID");
    assert.ok(html.includes("Gemini"), "Must mention Gemini structured generation");
    assert.ok(!html.includes("Operational Strategy Overview"), "Must NOT render strategy overview before generation");
  });

  // ----------------------------------------------------------------------------
  // Test 2: Generate Button Behavior Attributes
  // ----------------------------------------------------------------------------
  test("2. Generate button behavior has accessible attributes and icons", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceDashboard, {
        analysisId: "analysis_test_02",
        enabled: false,
      })
    );

    assert.ok(html.includes("id=\"generate-action-plan-btn\""), "Button must have accessible ID");
    assert.ok(html.includes("Generate Action Plan"), "Button text must match specification");
  });

  // ----------------------------------------------------------------------------
  // Test 3: Successful Plan Rendering (Strategy Overview)
  // ----------------------------------------------------------------------------
  test("3. Successful plan rendering displays strategy summary and generation metadata", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionStrategyOverview, {
        plan: MOCK_PLAN,
        cached: false,
      })
    );

    assert.ok(html.includes("Operational Strategy Overview"), "Must display strategy overview header");
    assert.ok(html.includes("Comprehensive operational rollout strategy"), "Must render strategy summary text");
    assert.ok(html.includes("vday8b_v1"), "Must display generator version");
    assert.ok(html.includes("FP: srfp_e3b0c44"), "Must display source recommendation fingerprint");
    assert.ok(html.includes("AI-Assisted Operational Guidance"), "Must render AI guidance disclaimer banner");
  });

  // ----------------------------------------------------------------------------
  // Test 4: Cached Plan Restoration
  // ----------------------------------------------------------------------------
  test("4. Cached plan restoration renders Cached Roadmap badge", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionStrategyOverview, {
        plan: MOCK_PLAN,
        cached: true,
      })
    );

    assert.ok(html.includes("Cached Roadmap"), "Must display Cached Roadmap badge when retrieved from cache");
  });

  // ----------------------------------------------------------------------------
  // Test 5: Refresh Without Gemini Generation (GET API)
  // ----------------------------------------------------------------------------
  test("5. GET /api/analysis/{analysis_id}/action-plan API helper uses GET method and preserves X-Owner-Id", async () => {
    let capturedMethod = "";
    let capturedHeaders = {};
    const originalFetch = global.fetch;

    global.fetch = async (url, init) => {
      capturedMethod = init?.method || "GET";
      capturedHeaders = init?.headers || {};
      return {
        ok: true,
        status: 200,
        json: async () => ({
          analysis_id: "analysis_123",
          status: "ready",
          cached: true,
          plan: MOCK_PLAN,
        }),
      };
    };

    try {
      const resp = await getActionPlan("analysis_123", "alice");
      assert.strictEqual(capturedMethod, "GET", "Must be read-only GET request");
      assert.strictEqual(capturedHeaders["X-Owner-Id"], "alice", "Must include X-Owner-Id header");
      assert.strictEqual(resp?.status, "ready");
      assert.strictEqual(resp?.cached, true);
    } finally {
      global.fetch = originalFetch;
    }
  });

  // ----------------------------------------------------------------------------
  // Test 6: Running Generation State (Status Endpoint)
  // ----------------------------------------------------------------------------
  test("6. Running generation state poll helper retrieves status without invoking generation", async () => {
    let capturedUrl = "";
    const originalFetch = global.fetch;

    global.fetch = async (url) => {
      capturedUrl = String(url);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          analysis_id: "analysis_running_01",
          status: "running",
          cached: false,
          plan: null,
        }),
      };
    };

    try {
      const resp = await getActionPlanStatus("analysis_running_01");
      assert.ok(capturedUrl.endsWith("/action-plan/status"), "Must query /action-plan/status endpoint");
      assert.strictEqual(resp.status, "running", "Must report running status");
      assert.strictEqual(resp.plan, null, "Plan must be null while running");
    } finally {
      global.fetch = originalFetch;
    }
  });

  // ----------------------------------------------------------------------------
  // Test 7: HTTP 409 Duplicate-Generation Handling
  // ----------------------------------------------------------------------------
  test("7. HTTP 409 duplicate generation returns typed ApiClientError with statusCode 409", async () => {
    const originalFetch = global.fetch;

    global.fetch = async () => ({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({
        detail: "Action intelligence generation for analysis analysis_123 is already running.",
      }),
    });

    try {
      await generateActionPlan("analysis_123");
      assert.fail("Should have thrown ApiClientError");
    } catch (err) {
      assert.ok(err instanceof ApiClientError);
      assert.strictEqual(err.statusCode, 409, "Must capture HTTP 409 status code");
      assert.ok(err.message.includes("already running"), "Must preserve backend error message");
    } finally {
      global.fetch = originalFetch;
    }
  });

  // ----------------------------------------------------------------------------
  // Test 8: Generation Failure & Retry Button
  // ----------------------------------------------------------------------------
  test("8. Generation failure renders error message with retry button", () => {
    // Render failed state directly in ActionIntelligenceDashboard via mock or helper
    const html = renderToStaticMarkup(
      React.createElement("div", { id: "action-plan-error-state", role: "alert" }, [
        React.createElement("h4", { key: "title" }, "Action Plan Generation Failed"),
        React.createElement("p", { key: "msg" }, "Vertex AI upstream service unavailable"),
        React.createElement("button", { key: "btn", id: "retry-action-plan-btn" }, "Retry Generation"),
      ])
    );

    assert.ok(html.includes("Action Plan Generation Failed"));
    assert.ok(html.includes("Vertex AI upstream service unavailable"));
    assert.ok(html.includes("id=\"retry-action-plan-btn\""));
  });

  // ----------------------------------------------------------------------------
  // Test 9: Network Disconnection Handling
  // ----------------------------------------------------------------------------
  test("9. Network disconnection raises descriptive network ApiClientError", async () => {
    const originalFetch = global.fetch;

    global.fetch = async () => {
      throw new Error("Failed to fetch");
    };

    try {
      await getActionPlan("analysis_offline");
      assert.fail("Should have thrown ApiClientError");
    } catch (err) {
      assert.ok(err instanceof ApiClientError);
      assert.ok(err.message.includes("Network error") || err.message.includes("unable to reach"));
    } finally {
      global.fetch = originalFetch;
    }
  });

  // ----------------------------------------------------------------------------
  // Test 10: Missing Analysis (Unavailable Banner)
  // ----------------------------------------------------------------------------
  test("10. Missing analysis or missing Stage 4 renders ActionUnavailableBanner", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionUnavailableBanner, {
        reason: "Stage 4 Decision Recommendation is required to generate an operational Action Plan.",
        historical: false,
      })
    );

    assert.ok(html.includes("Action Intelligence Unavailable"));
    assert.ok(html.includes("Stage 4 Decision Recommendation is required"));
  });

  // ----------------------------------------------------------------------------
  // Test 11: Action Ordering
  // ----------------------------------------------------------------------------
  test("11. Actions are ordered strictly by sequence number", () => {
    // Pass out-of-order actions
    const unorderedActions = [MOCK_PLAN.actions[1], MOCK_PLAN.actions[0]];
    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceRoadmapSection, {
        actions: unorderedActions,
      })
    );

    const firstIndex = html.indexOf("#1");
    const secondIndex = html.indexOf("#2");
    assert.ok(firstIndex < secondIndex, "Action #1 must appear before Action #2 in rendered markup");
  });

  // ----------------------------------------------------------------------------
  // Test 12: Dependency Display
  // ----------------------------------------------------------------------------
  test("12. Dependencies display resolved action titles and warn on unresolved references", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceRoadmapSection, {
        actions: MOCK_PLAN.actions,
      })
    );

    // Act 2 depends on act_1 ("Pilot Deployment Setup") and act_external_unresolved
    assert.ok(html.includes("Pilot Deployment Setup"), "Must display resolved title of dependency act_1");
    assert.ok(html.includes("Unresolved Reference"), "Must display warning badge for unresolved dependency");
    assert.ok(html.includes("[act_external_unresolved]"), "Must display unresolved dependency ID");
  });

  // ----------------------------------------------------------------------------
  // Test 13: Decision Gate Rendering
  // ----------------------------------------------------------------------------
  test("13. Decision gates render checkpoints, criteria, and mandatory rollback response", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionDecisionGates, {
        decisionGates: MOCK_PLAN.decision_gates,
        actions: MOCK_PLAN.actions,
      })
    );

    assert.ok(html.includes("Strategic Decision Gates"), "Must display decision gates header");
    assert.ok(html.includes("Pilot Verification Gate"), "Must display gate title");
    assert.ok(html.includes("End of Week 2 Pilot"), "Must display checkpoint timing");
    assert.ok(html.includes("HARD CONSTRAINT"), "Must distinctly badge hard constraints");
    assert.ok(html.includes("Mandatory Failure &amp; Rollback Response"), "Must display rollback response section");
    assert.ok(html.includes("Halt pilot and revert traffic routing"), "Must render rollback procedure text");
  });

  // ----------------------------------------------------------------------------
  // Test 14: Conflict Warning Visibility
  // ----------------------------------------------------------------------------
  test("14. Conflict warnings are rendered with prominent CONFLICT alert badge", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionValidationWarnings, {
        warnings: MOCK_PLAN.validation_warnings,
      })
    );

    assert.ok(html.includes("CONFLICT"), "Must render prominent CONFLICT badge");
    assert.ok(html.includes("Hard Constraint Conflict"), "Must render conflict title");
    assert.ok(html.includes("violating user hard floor of 90%"), "Must display conflict explanation");
    assert.ok(html.includes("Action: act_1"), "Must display related entity tags");
  });

  // ----------------------------------------------------------------------------
  // Test 15: Review-Required Warning Visibility
  // ----------------------------------------------------------------------------
  test("15. Review-required warnings are rendered with REVIEW REQUIRED badge", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionValidationWarnings, {
        warnings: MOCK_PLAN.validation_warnings,
      })
    );

    assert.ok(html.includes("REVIEW REQUIRED"), "Must render REVIEW REQUIRED badge");
    assert.ok(html.includes("Incompatible units between criterion") && html.includes("points") && html.includes("Automated comparison cannot be verified"));
  });

  // ----------------------------------------------------------------------------
  // Test 16: Missing Optional Fields Rendering
  // ----------------------------------------------------------------------------
  test("16. Missing optional fields display 'Not specified' without breaking UI", () => {
    const minimalAction = {
      action_id: "act_min",
      title: "Minimal Action",
      sequence: 1,
      priority: "low",
      owner_role: "",
      timing: null,
      description: "Simple action description.",
      execution_steps: null,
      dependencies: [],
      prerequisites: [],
      success_criteria: [],
      risk_mitigations: [],
      contingency_or_rollback: null,
      rationale: "Basic rationale",
      confidence_label: "low",
      confidence_rationale: null,
      missing_information: [],
    };

    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceRoadmapSection, {
        actions: [minimalAction],
      })
    );

    assert.ok(html.includes("Minimal Action"));
    assert.ok(html.includes("Not specified"));
    assert.ok(!html.includes("undefined"));
  });

  // ----------------------------------------------------------------------------
  // Test 17: Unresolved Questions & Limitations
  // ----------------------------------------------------------------------------
  test("17. Unresolved questions and analytical limitations are rendered clearly", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionUnresolvedQuestions, {
        unresolvedQuestions: MOCK_PLAN.unresolved_questions,
        limitations: MOCK_PLAN.limitations,
      })
    );

    assert.ok(html.includes("Unresolved Strategic Questions &amp; Analytical Boundaries"));
    assert.ok(html.includes("Will customer support ticket resolution time increase"));
    assert.ok(html.includes("vendor API pricing remains unchanged"));
  });

  // ----------------------------------------------------------------------------
  // Test 18: Long Action Descriptions
  // ----------------------------------------------------------------------------
  test("18. Long action descriptions render cleanly with progressive disclosure", () => {
    const longDesc = "A".repeat(500);
    const actionWithLongDesc = {
      ...MOCK_PLAN.actions[0],
      description: longDesc,
    };

    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceRoadmapSection, {
        actions: [actionWithLongDesc],
      })
    );

    assert.ok(html.includes(longDesc));
    assert.ok(html.includes("View Details"));
  });

  // ----------------------------------------------------------------------------
  // Test 19: Polling Cleanup & API Endpoint Isolation
  // ----------------------------------------------------------------------------
  test("19. Generate Action Plan calls POST endpoint with force_regenerate option", async () => {
    let capturedBody = "";
    const originalFetch = global.fetch;

    global.fetch = async (url, init) => {
      capturedBody = init?.body ? String(init.body) : "";
      return {
        ok: true,
        status: 200,
        json: async () => ({
          analysis_id: "analysis_gen",
          status: "ready",
          cached: false,
          plan: MOCK_PLAN,
        }),
      };
    };

    try {
      const resp = await generateActionPlan("analysis_gen", true, "owner_1");
      assert.strictEqual(resp.status, "ready");
      assert.ok(capturedBody.includes('"force_regenerate":true'), "Must pass force_regenerate in payload");
    } finally {
      global.fetch = originalFetch;
    }
  });

  // ----------------------------------------------------------------------------
  // Test 20: No Regressions in Analysis Dashboard (Stages 1–6 + What-If + Action)
  // ----------------------------------------------------------------------------
  test("20. AnalysisResultCard mounts Action Intelligence alongside What-if simulation and Stages 1-6", () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: MOCK_ANALYSIS_RESPONSE,
        onReset: () => {},
        ownerId: "alice",
      })
    );

    // Stage 1 Decision Model
    assert.ok(html.includes("id=\"section-decision-model\""), "Must preserve Stage 1 Decision Model");
    // Stage 4 Recommendation
    assert.ok(html.includes("Proceed with controlled phased rollout."), "Must preserve Stage 4 Recommendation");
    // Stage 5 Scenarios
    assert.ok(html.includes("Future Explorer"), "Must preserve Stage 5 Scenarios");
    // Stage 6 Resilience
    assert.ok(html.includes("Resilience"), "Must preserve Stage 6 Resilience");
    // Day 7 What-If Simulation
    assert.ok(html.includes("What-if Simulation"), "Must preserve What-if Simulation");
    // Day 8 Action Intelligence
    assert.ok(html.includes("id=\"section-action-intelligence\""), "Must mount Action Intelligence section");
    assert.ok(html.includes("Generate Action Plan"), "Must display initial Action Plan CTA");
  });
});
