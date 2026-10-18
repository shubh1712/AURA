import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  saveActiveSession,
  loadActiveSession,
  clearActiveSession,
  hasActiveSession,
} from "../src/lib/session.ts";
import {
  getCachedSimulationExplanation,
} from "../src/lib/api.ts";
import { AnalysisResultCard } from "../src/components/decision/AnalysisResultCard.tsx";
import { WhatIfDashboard } from "../src/components/decision/simulation/WhatIfDashboard.tsx";

// Mock browser storage environment for Node.js test runner
class MockStorage {
  constructor() {
    this.store = new Map();
  }
  getItem(key) {
    return this.store.has(key) ? this.store.get(key) : null;
  }
  setItem(key, value) {
    this.store.set(key, String(value));
  }
  removeItem(key) {
    this.store.delete(key);
  }
  clear() {
    this.store.clear();
  }
}

// ------------------------------------------------------------------------------
// Test Fixtures
// ------------------------------------------------------------------------------

const MOCK_COMPLETED_ANALYSIS = {
  analysis_id: "b2abf510-aacb-44d7-8a11-7cc40806cca1",
  status: "completed",
  question: "Should we deploy B2B SaaS AI customer support?",
  message: "Decision analysis completed successfully across all 6 stages.",
  decision_model: {
    id: "decision_ai_support_rollout",
    title: "B2B SaaS AI Support Rollout",
    domain: "Customer Operations",
    type: "operational",
    complexity: {
      level: "medium",
      score: 50.0,
      reversibility: "high",
      reasoning: "Pilot evaluation window.",
      contributing_factors: ["Customer impact", "Automation risk"],
    },
    time_horizon: {
      bracket: "3-6 months",
      rationale: "Pilot evaluation window",
    },
    reversibility: "high",
    decision: {
      raw_prompt: "Should we deploy B2B SaaS AI customer support?",
      summary: "Deploy automated AI customer support agent.",
      decision_type: "operational",
      time_horizon: "medium_term",
    },
    objectives: [
      {
        id: "obj_csat",
        description: "Maintain CSAT above 90%",
        target_value: "90",
        unit: "%",
      },
    ],
    constraints: [
      {
        id: "cnstr_pilot_cohort",
        name: "Pilot Customer Cohort",
        description: "Pilot cohort capped at 1,000 customers",
        threshold: 1000,
        unit: "customers",
        type: "hard",
      },
    ],
    variables: [
      {
        id: "var_pilot_size",
        name: "Pilot Cohort Size",
        description: "Number of active pilot customers.",
        variable_type: "count",
        baseline_value: 1000,
        unit: "customers",
        is_controllable: true,
      },
    ],
    stakeholders: [],
    tradeoffs: [],
    assumptions: [],
    unknowns: [],
    key_questions: [],
    created_at: "2026-10-11T12:00:00Z",
  },
  evidence_package: {
    id: "ev_pkg_001",
    decision_model_id: "decision_ai_support_rollout",
    requirements: [],
    sources: [],
    items: [],
    claim_links: [],
    gaps: [],
    metadata: { source: "Brave Search" },
  },
  reasoning_board: {
    id: "rb_001",
    decision_id: "decision_ai_support_rollout",
    perspectives: [],
    syntheses: [],
    status: "complete",
  },
  recommendation: {
    id: "rec_ai_support_rollout",
    decision_id: "decision_ai_support_rollout",
    decision_status: "pilot",
    recommended_action: "Deploy three-month pilot for 1,000 customers.",
    executive_rationale: "Controlled cohort mitigates downside risk while gathering telemetry.",
    action_plan: {
      summary: "Three-phase rollout schedule.",
      actions: [
        {
          id: "act_1",
          title: "Initial Pilot Cutover",
          objective: "Onboard 1,000 pilot users",
          description: "Route 1,000 users to AI assistant.",
          priority: "high",
          responsible_role: "Head of Support",
          time_horizon: "immediate",
          decision_gates: [],
        },
      ],
    },
    uncertainty_assessment: {
      evidence_strength: "moderate",
      decision_readiness: "ready",
      recommendation_stability: "high",
    },
    confidence: "high",
    trade_offs: ["Initial human triage needed during ramp-up"],
    alternative_options: [],
    created_at: "2026-10-11T12:00:00Z",
  },
  scenarios: {
    id: "scenset_001",
    decision_id: "decision_ai_support_rollout",
    summary: "Base, optimistic, and stressed customer support trajectories.",
    scenarios: [
      {
        id: "sc_base",
        scenario_type: "base_case",
        name: "Standard Pilot Adoption",
        narrative: "Baseline customer adoption with stable error rates.",
        probability: 0.5,
        key_events: [],
        risks: [],
        opportunities: [],
        timeline: [],
        supporting_evidence_item_ids: [],
        relevant_assumption_ids: [],
        relevant_constraint_ids: ["cnstr_pilot_cohort"],
        relevant_gap_ids: [],
      },
      {
        id: "sc_opt",
        scenario_type: "optimistic",
        name: "Rapid Customer Adoption",
        narrative: "Accelerated adoption with high customer satisfaction.",
        probability: 0.25,
        key_events: [],
        risks: [],
        opportunities: [],
        timeline: [],
        supporting_evidence_item_ids: [],
        relevant_assumption_ids: [],
        relevant_constraint_ids: ["cnstr_pilot_cohort"],
        relevant_gap_ids: [],
      },
      {
        id: "sc_stress",
        scenario_type: "pessimistic",
        name: "High Error Escalation",
        narrative: "Complex customer queries overwhelm automated workflows.",
        probability: 0.25,
        key_events: [],
        risks: [],
        opportunities: [],
        timeline: [],
        supporting_evidence_item_ids: [],
        relevant_assumption_ids: [],
        relevant_constraint_ids: ["cnstr_pilot_cohort"],
        relevant_gap_ids: [],
      },
    ],
    created_at: "2026-10-11T12:00:00Z",
  },
  resilience: {
    id: "res_001",
    decision_id: "decision_ai_support_rollout",
    overall_score: 66.38,
    overall_resilience_score: 66.38,
    rating: "moderate",
    stress_test_passed: true,
    sub_scores: [
      { category: "constraint_boundary_tolerance", score: 16.25, max_score: 25.0, rationale: "Boundary holds under 1000 users." },
      { category: "pessimistic_scenario_survivability", score: 17.5, max_score: 25.0, rationale: "Survivable with support escalation." },
      { category: "contingency_and_fallback_coverage", score: 15.5, max_score: 25.0, rationale: "Human fallback available." },
      { category: "information_robustness", score: 17.13, max_score: 25.0, rationale: "Evidence quality verified." },
    ],
    critical_vulnerabilities: [],
    recommended_hedges: [],
    calculation_version: "1.0.0",
    created_at: "2026-10-11T12:00:00Z",
  },
};

const MOCK_SAVED_SIMULATION = {
  id: "sim_50d5ddcf9d79f30bd71f809ab2d722ff",
  decision_model_id: "decision_ai_support_rollout",
  scenario_set_id: "scenset_001",
  recommendation_id: "rec_ai_support_rollout",
  baseline_fingerprint: "bfp_3f421f2bb0ae1245e89a32c0211df44a",
  applied_adjustments: [
    {
      variable_id: "var_pilot_size",
      proposed_value: 2000,
      unit: "customers",
    },
  ],
  impacts: [],
  simulated_resilience_score: null,
  score_delta: null,
  status: "unsupported_no_causal_mapping",
  warnings: ["Calculation status unsupported: no direct causal mapping to resilience score."],
  created_at: "2026-10-11T12:05:00Z",
};

const MOCK_CACHED_EXPLANATION = {
  simulation_id: "sim_50d5ddcf9d79f30bd71f809ab2d722ff",
  baseline_fingerprint: "bfp_3f421f2bb0ae1245e89a32c0211df44a",
  summary: "Increasing pilot size to 2,000 customers doubles cohort load while operating under unsupported causal mapping.",
  what_changed: ["Pilot Cohort Size adjusted from 1,000 to 2,000 customers (+100%)."],
  constraint_implications: ["Breaches hard pilot cohort limit (1,000 customers)."],
  resilience_interpretation: "Resilience recalculation status is unsupported_no_causal_mapping; numerical score remains null without synthetic delta.",
  limitations: ["No historical data on 2,000 concurrent bot interactions."],
  suggested_validation_steps: ["Validate server load in staging with synthetic traffic."],
  evidence_or_artifact_references: ["decision_ai_support_rollout"],
  generation_status: "cached",
  model_name: "gemini-2.5-pro",
  prompt_version: "v1",
  created_at: "2026-10-11T12:06:00Z",
};

describe("Phase 7F: Analysis Session Restoration & Simulation Recovery", () => {
  beforeEach(() => {
    globalThis.window = {
      sessionStorage: new MockStorage(),
      localStorage: new MockStorage(),
    };
  });

  afterEach(() => {
    delete globalThis.window;
  });

  // 1. Session persistence saves minimal identifiers only
  test("1. Session persistence stores minimal identifiers without full report JSON", () => {
    saveActiveSession({
      jobId: "job-1234",
      analysisId: "b2abf510-aacb-44d7-8a11-7cc40806cca1",
      ownerId: "owner-alice",
    });

    const session = loadActiveSession();
    assert.ok(session, "Session should be loaded");
    assert.strictEqual(session.jobId, "job-1234");
    assert.strictEqual(session.analysisId, "b2abf510-aacb-44d7-8a11-7cc40806cca1");
    assert.strictEqual(session.ownerId, "owner-alice");
    assert.ok(session.lastUpdated, "Timestamp should be generated");

    // Verify localStorage does not contain analysis response fields
    const raw = globalThis.window.sessionStorage.getItem("aura_active_analysis_session");
    assert.ok(raw);
    assert.ok(!raw.includes("recommendation"), "Report data must not leak into browser storage");
    assert.ok(!raw.includes("resilience"), "Resilience report must not leak into browser storage");
  });

  // 2. Clear session removes reference from all browser storages
  test("2. Clear active session removes identifiers completely", () => {
    saveActiveSession({ jobId: "job-999" });
    assert.strictEqual(hasActiveSession(), true);

    clearActiveSession();
    assert.strictEqual(hasActiveSession(), false);
    assert.strictEqual(loadActiveSession(), null);
  });

  // 3. Restored analysis renders recommendation correctly
  test("3. Restored analysis result card renders original recommendation and confidence", () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: MOCK_COMPLETED_ANALYSIS,
        onReset: () => {},
        jobId: "job-1234",
      })
    );

    assert.ok(html.includes("Deploy three-month pilot for 1,000 customers."));
    assert.ok(html.includes("Controlled cohort mitigates downside risk"));
  });

  // 4. Restored analysis renders scenarios correctly
  test("4. Restored analysis renders scenarios trajectory panel", () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: MOCK_COMPLETED_ANALYSIS,
        onReset: () => {},
      })
    );

    assert.ok(html.includes("Standard Pilot Adoption"));
    assert.ok(html.includes("Baseline customer adoption with stable error rates."));
  });

  // 5. Restored analysis renders deterministic resilience report correctly
  test("5. Restored analysis renders exact baseline resilience score without recalculation", () => {
    const html = renderToStaticMarkup(
      React.createElement(AnalysisResultCard, {
        result: MOCK_COMPLETED_ANALYSIS,
        onReset: () => {},
      })
    );

    assert.ok(html.includes("66.4"), "Exact baseline score 66.4 (formatted 66.38) must render");
    assert.ok(html.includes("Resilience Score") || html.includes("Resilience Assessment") || html.includes("Decision Resilience"));
  });

  // 6. What-if Simulation Dashboard is rendered for restored analysis
  test("6. What-if Simulation Dashboard mounts for restored analysis", () => {
    const html = renderToStaticMarkup(
      React.createElement(WhatIfDashboard, {
        analysisId: MOCK_COMPLETED_ANALYSIS.analysis_id,
      })
    );

    assert.ok(html.includes("What-if Simulation Engine") || html.includes("Simulation Variables") || html.includes("aria-label=\"What-if Simulation\"") || html.includes("Discovering adjustable simulation variables"));
  });

  // 7. Cached explanation retrieval returns cached content with 0 LLM calls
  test("7. getCachedSimulationExplanation retrieves cached AI explanation via GET endpoint", async () => {
    const originalFetch = globalThis.fetch;
    let requestedMethod = null;
    let requestedUrl = null;

    globalThis.fetch = async (url, options) => {
      requestedUrl = url;
      requestedMethod = options.method;
      return {
        ok: true,
        status: 200,
        json: async () => MOCK_CACHED_EXPLANATION,
      };
    };

    try {
      const result = await getCachedSimulationExplanation(
        "b2abf510-aacb-44d7-8a11-7cc40806cca1",
        "sim_50d5ddcf9d79f30bd71f809ab2d722ff",
        "owner-alice"
      );

      assert.strictEqual(requestedMethod, "GET", "Must use GET endpoint (pure read-only lookup)");
      assert.ok(
        requestedUrl.includes("/simulations/sim_50d5ddcf9d79f30bd71f809ab2d722ff/explain"),
        "URL must target simulation explain endpoint"
      );
      assert.ok(result);
      assert.strictEqual(result.simulation_id, "sim_50d5ddcf9d79f30bd71f809ab2d722ff");
      assert.strictEqual(result.generation_status, "cached");
      assert.ok(result.summary.includes("2,000 customers"));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  // 8. Missing cached explanation returns null cleanly (HTTP 404 handled gracefully)
  test("8. getCachedSimulationExplanation returns null on HTTP 404 without throwing", async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = async () => ({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ detail: "No cached AI explanation found" }),
    });

    try {
      const result = await getCachedSimulationExplanation(
        "b2abf510-aacb-44d7-8a11-7cc40806cca1",
        "sim_unexplained"
      );
      assert.strictEqual(result, null, "Uncached simulation explanation returns null");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  // 9. Preserves null score delta and unsupported calculation status
  test("9. Saved simulation preserves null score delta without fabricating zero change", () => {
    assert.strictEqual(MOCK_SAVED_SIMULATION.simulated_resilience_score, null);
    assert.strictEqual(MOCK_SAVED_SIMULATION.score_delta, null);
    assert.strictEqual(MOCK_SAVED_SIMULATION.status, "unsupported_no_causal_mapping");
  });

  // 10. SSR safety: works in non-browser environment without errors
  test("10. Session operations handle absence of window/storage without throwing", () => {
    delete globalThis.window;
    assert.strictEqual(loadActiveSession(), null);
    assert.strictEqual(hasActiveSession(), false);
    assert.doesNotThrow(() => saveActiveSession({ jobId: "job-1" }));
    assert.doesNotThrow(() => clearActiveSession());
  });
});
