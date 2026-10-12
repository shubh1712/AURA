import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Import components built for Phase 7D (Grounded AI Explanation)
import { SimulationAIExplanation } from "../src/components/decision/simulation/SimulationAIExplanation.tsx";
import { explainSimulation, ApiClientError } from "../src/lib/api.ts";

// ------------------------------------------------------------------------------
// Test Fixtures
// ------------------------------------------------------------------------------

const MOCK_EXPLANATION_GENERATED = {
  simulation_id: "sim_1234567890abcdef1234567890abcdef",
  baseline_fingerprint: "fp_abcdef1234567890abcdef1234567890",
  summary: "Simulated scaling operational expenditure from $35k to $52k, successfully evaluating threshold margins.",
  what_changed: [
    "Monthly Cloud Spend increased from $35,000 to $52,000 USD (+48.6%).",
  ],
  constraint_implications: [
    "Breached hard budget ceiling ($50,000) by $2,000, reducing buffer to negative 4%.",
  ],
  resilience_interpretation: "Direct causal pathway to composite resilience is not mapped; operational constraints were evaluated without fabricated score shifts.",
  limitations: [
    "Assumes static tier pricing without multi-region reserved instance commitments.",
  ],
  suggested_validation_steps: [
    "Request automated quote for reserved instances in eu-west-1.",
    "Perform load-test with synthetic shadow ingress before final cutover.",
  ],
  evidence_or_artifact_references: [
    "dec_model_001",
    "cnstr_budget",
    "scenset_001",
  ],
  generation_status: "generated",
  model_name: "gemini-3.8-flash",
  prompt_version: "v1",
  created_at: "2026-10-11T12:00:00Z",
};

const MOCK_EXPLANATION_CACHED = {
  ...MOCK_EXPLANATION_GENERATED,
  generation_status: "cached",
};

describe("Phase 7D: Grounded AI Simulation Explanations & Frontend Verification", () => {
  // ----------------------------------------------------------------------------
  // Test 1: Explanation Button Visibility when Simulation Active
  // ----------------------------------------------------------------------------
  test("1. Explicit 'Explain This Simulation' button is rendered when explanation is unrequested", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: null,
        isExplaining: false,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("Explain This Simulation"), "Must show Explain This Simulation button");
    assert.ok(html.includes("id=\"explain-simulation-btn\""), "Button must have unique ID");
    assert.ok(html.includes("AI Qualitative Explanation &amp; Epistemic Boundaries") || html.includes("AI Qualitative Explanation"), "Must display title");
    assert.ok(html.includes("AI-Interpreted (Non-Deterministic)"), "Must display non-deterministic disclaimer badge");
  });

  // ----------------------------------------------------------------------------
  // Test 2: Loading State
  // ----------------------------------------------------------------------------
  test("2. Loading state renders accessible spinner and progress narrative", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: null,
        isExplaining: true,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("Synthesizing Grounded Explanation with Gemini..."), "Must show loading label");
    assert.ok(html.includes("role=\"status\""), "Must have role='status' for accessibility");
    assert.ok(html.includes("aria-busy=\"true\""), "Must indicate aria-busy='true'");
    assert.ok(!html.includes("id=\"explain-simulation-btn\""), "Explain button should be hidden while loading");
  });

  // ----------------------------------------------------------------------------
  // Test 3: Successful Generated Explanation Rendering
  // ----------------------------------------------------------------------------
  test("3. Successfully generated explanation renders all grounded sections and badges", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: MOCK_EXPLANATION_GENERATED,
        isExplaining: false,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    // Header metadata
    assert.ok(html.includes("Freshly Generated"), "Must display Freshly Generated status");
    assert.ok(html.includes("gemini-3.8-flash"), "Must display model name");

    // Sections
    assert.ok(html.includes("Executive Summary"), "Must have Executive Summary section");
    assert.ok(html.includes(MOCK_EXPLANATION_GENERATED.summary), "Must render summary text");

    assert.ok(html.includes("What Changed"), "Must have What Changed section");
    assert.ok(html.includes(MOCK_EXPLANATION_GENERATED.what_changed[0]), "Must render what changed item");

    assert.ok(html.includes("Constraint Implications &amp; Margins") || html.includes("Constraint Implications"), "Must have Constraint Implications");
    assert.ok(html.includes(MOCK_EXPLANATION_GENERATED.constraint_implications[0]), "Must render constraint implication");

    assert.ok(html.includes("Resilience Interpretation"), "Must have Resilience Interpretation");
    assert.ok(html.includes(MOCK_EXPLANATION_GENERATED.resilience_interpretation), "Must render resilience interpretation");

    assert.ok(html.includes("Modeling Limitations &amp; Caveats") || html.includes("Modeling Limitations"), "Must have Limitations section");
    assert.ok(html.includes(MOCK_EXPLANATION_GENERATED.limitations[0]), "Must render limitation item");

    assert.ok(html.includes("Suggested Empirical Validation Steps"), "Must have Validation Steps section");
    assert.ok(html.includes(MOCK_EXPLANATION_GENERATED.suggested_validation_steps[0]), "Must render validation step");

    assert.ok(html.includes("Grounded Artifacts:"), "Must list referenced artifacts");
    assert.ok(html.includes("dec_model_001"), "Must display artifact ID badge");
  });

  // ----------------------------------------------------------------------------
  // Test 4: Cached Explanation Rendering
  // ----------------------------------------------------------------------------
  test("4. Cached explanation renders 'Cached Synthesis' badge", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: MOCK_EXPLANATION_CACHED,
        isExplaining: false,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("Cached Synthesis"), "Must display Cached Synthesis badge");
    assert.ok(!html.includes("Freshly Generated"), "Must not display Freshly Generated badge");
  });

  // ----------------------------------------------------------------------------
  // Test 5: Failure State & Retry Action
  // ----------------------------------------------------------------------------
  test("5. Failure state displays user-facing error and retry button", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: null,
        isExplaining: false,
        explanationError: "AI explanation generation exceeded allowed processing time (HTTP 504).",
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("role=\"alert\""), "Must have role='alert'");
    assert.ok(html.includes("Failed to Generate AI Explanation"), "Must show error heading");
    assert.ok(html.includes("exceeded allowed processing time"), "Must show normalized error message");
    assert.ok(html.includes("id=\"retry-explanation-btn\""), "Must have retry button");
    assert.ok(html.includes("Retry Explanation"), "Button must say Retry Explanation");
  });

  // ----------------------------------------------------------------------------
  // Test 6: Null Score-Delta Preservation
  // ----------------------------------------------------------------------------
  test("6. Null score delta preservation renders transparent explanation without fabricated zero", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: {
          ...MOCK_EXPLANATION_GENERATED,
          resilience_interpretation: "AURA lacks a mathematical causal link for cloud spend; resilience score delta is uncalculable and not 0.0.",
        },
        isExplaining: false,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("uncalculable and not 0.0"), "Must preserve transparent null score explanation");
    assert.ok(!html.includes("0.0% probability"), "Must not contain invented probability");
  });

  // ----------------------------------------------------------------------------
  // Test 7: Accessible Element Identifiers
  // ----------------------------------------------------------------------------
  test("7. Accessible IDs and landmarks are strictly preserved", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: MOCK_EXPLANATION_GENERATED,
        isExplaining: false,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("id=\"simulation-ai-explanation-panel\""), "Must have container ID");
    assert.ok(html.includes("aria-labelledby=\"simulation-ai-explanation-title\""), "Must have aria-labelledby");
    assert.ok(html.includes("id=\"simulation-ai-explanation-title\""), "Must have title ID");
  });

  // ----------------------------------------------------------------------------
  // Test 8: Print-Friendly CSS Classes
  // ----------------------------------------------------------------------------
  test("8. Print-friendly CSS hides interactive buttons while keeping text readable", () => {
    const html = renderToStaticMarkup(
      React.createElement(SimulationAIExplanation, {
        simulationId: "sim_123",
        explanation: MOCK_EXPLANATION_GENERATED,
        isExplaining: false,
        explanationError: null,
        onRequestExplanation: () => {},
      })
    );

    assert.ok(html.includes("print:bg-white"), "Must use white background for print");
    assert.ok(html.includes("print:text-black"), "Must use black text for print");
    assert.ok(html.includes("print:hidden"), "Interactive footer controls must have print:hidden");
  });

  // ----------------------------------------------------------------------------
  // Test 9: API Client Contract
  // ----------------------------------------------------------------------------
  test("9. API client explainSimulation creates valid request URL and headers", async () => {
    let capturedUrl = "";
    let capturedOptions = {};

    globalThis.fetch = async (url, options) => {
      capturedUrl = String(url);
      capturedOptions = options;
      return {
        ok: true,
        status: 200,
        json: async () => MOCK_EXPLANATION_GENERATED,
      };
    };

    const res = await explainSimulation("analysis_test_123", "sim_test_456", "test_owner");
    assert.equal(capturedUrl, "http://127.0.0.1:8000/api/analysis/analysis_test_123/simulations/sim_test_456/explain");
    assert.equal(capturedOptions.method, "POST");
    assert.equal(capturedOptions.headers["X-Owner-Id"], "test_owner");
    assert.equal(res.simulation_id, MOCK_EXPLANATION_GENERATED.simulation_id);
    assert.equal(res.generation_status, "generated");
  });

  // ----------------------------------------------------------------------------
  // Test 10: API Client Error Handling
  // ----------------------------------------------------------------------------
  test("10. API client explainSimulation raises typed ApiClientError on HTTP 504", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 504,
      statusText: "Gateway Timeout",
      json: async () => ({ detail: "AI explanation generation exceeded allowed processing time." }),
    });

    await assert.rejects(
      async () => {
        await explainSimulation("analysis_1", "sim_1");
      },
      (err) => {
        assert.ok(err instanceof ApiClientError);
        assert.equal(err.statusCode, 504);
        assert.ok(err.message.includes("exceeded allowed processing time"));
        return true;
      }
    );
  });
});
