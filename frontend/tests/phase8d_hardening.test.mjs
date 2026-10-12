import { test, describe } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ActionStrategyOverview } from "../src/components/decision/action/ActionStrategyOverview.tsx";
import { ActionIntelligenceRoadmapSection } from "../src/components/decision/action/ActionRoadmapSection.tsx";
import { ActionDecisionGates } from "../src/components/decision/action/ActionDecisionGates.tsx";
import { ActionValidationWarnings } from "../src/components/decision/action/ActionValidationWarnings.tsx";
import { ActionUnresolvedQuestions } from "../src/components/decision/action/ActionUnresolvedQuestions.tsx";
import { ActionIntelligenceDashboard } from "../src/components/decision/action/ActionIntelligenceDashboard.tsx";

// ------------------------------------------------------------------------------
// Test Fixtures for SaaS Support Assistant Decision
// ------------------------------------------------------------------------------

const SAAS_SUPPORT_PLAN = {
  plan_id: "plan_saas_support_assistant_01",
  analysis_id: "analysis_saas_01",
  source_recommendation_fingerprint: "srfp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  schema_version: "1.0",
  generator_version: "day8b_v1",
  created_at: "2026-10-12T10:00:00Z",
  strategy_summary:
    "Grounded operational plan for 3-month SaaS support-assistant pilot across 1,000 customers.",
  actions: [
    {
      action_id: "act_saas_pilot_item",
      source_action_reference: "act_saas_pilot",
      title: "Phase 1: 1,000 Customer Pilot Deployment",
      sequence: 1,
      priority: "high",
      owner_role: "VP of Customer Support",
      timing: "Months 1-3",
      description:
        "Deploy support-assistant to 1,000 customers under tight latency and satisfaction monitoring.",
      execution_steps: [
        "Step 1: Provision isolated compute pool with $20,000 monthly cost cap",
        "Step 2: Route 1,000 customer tickets to support assistant with human agent fallback",
      ],
      dependencies: [],
      prerequisites: ["Cohort selection finalized", "Agent fallback routing configured"],
      success_criteria: [
        {
          criterion_id: "crit_pilot_budget",
          criterion_type: "hard_constraint",
          is_hard: true,
          description: "Pilot setup expenditure within $150,000 budget cap",
          metric_name: "budget",
          operator: "<=",
          threshold_value: 45000.0,
          threshold_raw: "$45,000",
          unit: "USD",
          provenance_type: "decision_model.constraints",
          source_reference: "cnstr_budget_cap",
        },
        {
          criterion_id: "crit_pilot_csat_target",
          criterion_type: "recommendation_target",
          is_hard: true,
          description: "Customer satisfaction target >= 90%",
          metric_name: "csat",
          operator: ">=",
          threshold_value: 90.0,
          threshold_raw: "90%",
          unit: "%",
          provenance_type: "decision_model.constraints",
          source_reference: "cnstr_csat_floor",
        },
      ],
      risk_mitigations: ["Automated human agent takeover if confidence falls below 80%"],
      contingency_or_rollback: "Instant traffic fallback to legacy human support routing queue.",
      evidence_references: ["evi_saas_01"],
      rationale: "Minimizes financial risk while gathering real interaction and deflection data.",
      confidence_label: "high",
      confidence_rationale: "Evidence demonstrates 68% deflection with 91.2% CSAT on tier-1 tickets.",
      missing_information: [],
    },
    {
      action_id: "act_saas_eval_item",
      source_action_reference: "act_saas_evaluation",
      title: "Phase 2: Pilot Review and General Rollout Decision",
      sequence: 2,
      priority: "medium",
      owner_role: "CTO",
      timing: "Month 4",
      description:
        "Evaluate CSAT metrics and monthly cloud run-rate before company-wide cutover.",
      execution_steps: [
        "Step 1: Audit monthly cloud infrastructure costs against $20,000 cap",
        "Step 2: Review CSAT survey scores against 90% floor",
      ],
      dependencies: ["act_saas_pilot_item"],
      prerequisites: ["3-month pilot completed", "Gate 1 checkpoint evaluation verified"],
      success_criteria: [
        {
          criterion_id: "crit_cloud_cost_check",
          criterion_type: "hard_constraint",
          is_hard: true,
          description: "Monthly cloud run-rate within $20,000 cap",
          metric_name: "monthly_cost",
          operator: "<=",
          threshold_value: 18000.0,
          threshold_raw: "$18,000/mo",
          unit: "USD",
          provenance_type: "decision_model.constraints",
          source_reference: "cnstr_monthly_cloud_cap",
        },
      ],
      risk_mitigations: ["Impose hard cloud provisioning quota alerts"],
      contingency_or_rollback:
        "Pause general expansion and keep assistant restricted to pilot cohort only.",
      evidence_references: ["evi_saas_01"],
      rationale: "Ensures unit economics are verified before full capital commitment.",
      confidence_label: "moderate",
      confidence_rationale: "Dependent on ticket deflection metrics from Phase 1.",
      missing_information: ["Long-term deflection sustainability under peak season spikes."],
    },
  ],
  decision_gates: [
    {
      gate_id: "gate_saas_pilot_checkpoint",
      title: "Gate 1: Pilot Acceptance Checkpoint",
      checkpoint: "Month 3 Completion Checkpoint",
      criteria: [
        {
          criterion_id: "gate_crit_csat",
          criterion_type: "hard_constraint",
          is_hard: true,
          description: "Customer satisfaction must remain at or above 90%",
          metric_name: "csat",
          operator: ">=",
          threshold_value: 90.0,
          threshold_raw: "90%",
          unit: "%",
          provenance_type: "decision_model.constraints",
          source_reference: "cnstr_csat_floor",
        },
      ],
      related_action_ids: ["act_saas_pilot_item"],
      failure_response:
        "Halt rollout and revert customer routing to standard human support queue.",
      source_references: ["cnstr_csat_floor"],
      unresolved_conflicts: [],
    },
  ],
  unresolved_questions: [
    "Enterprise compliance certification requirements for HIPAA/SOC2 compliance.",
  ],
  limitations: ["Pilot findings apply solely to English-language support inquiries."],
  validation_warnings: [
    {
      warning_id: "conflict_crit_rollback_85_cnstr_csat_floor",
      severity: "conflict",
      message:
        "Direct threshold conflict: Action/gate criterion evaluates CSAT at 85.0%, which is below the mandatory user hard constraint floor of 90.0% (constraint 'cnstr_csat_floor').",
      related_action_ids: ["act_saas_pilot_item"],
      related_gate_ids: ["gate_saas_pilot_checkpoint"],
      related_criterion_ids: ["crit_rollback_85"],
    },
  ],
  generation_metadata: {
    model_name: "gemini-3.8-flash",
    prompt_version: "day8b_v1",
    generator_version: "day8b_v1",
  },
};

// ------------------------------------------------------------------------------
// Test Suite: Phase 8D Hardening & Verification
// ------------------------------------------------------------------------------

describe("Phase 8D: Action Intelligence Hardening & Acceptance Verification", () => {
  // Test 1: SaaS Support-Assistant Strategy Overview
  test("1. Renders SaaS support-assistant strategy overview with pilot details", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionStrategyOverview, {
        plan: SAAS_SUPPORT_PLAN,
        cached: false,
      })
    );

    assert.ok(html.includes("3-month SaaS support-assistant pilot"));
    assert.ok(html.includes("gemini-3.8-flash"));
    assert.ok(html.includes("day8b_v1"));
  });

  // Test 2: Renders direct threshold CONFLICT warning
  test("2. Flags 85% CSAT rollback trigger as a prominent CONFLICT warning against 90% floor", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionValidationWarnings, {
        warnings: SAAS_SUPPORT_PLAN.validation_warnings,
      })
    );

    assert.ok(html.includes("CONFLICT"), "Must render CONFLICT badge");
    assert.ok(html.includes("Direct threshold conflict"));
    assert.ok(html.includes("85.0%"));
    assert.ok(html.includes("90.0%"));
    assert.ok(html.includes("cnstr_csat_floor"));
  });

  // Test 3: Renders sequenced SaaS actions with roles, steps, and criteria
  test("3. Prioritized Execution Roadmap displays roles, execution steps, and rollback criteria", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceRoadmapSection, {
        actions: SAAS_SUPPORT_PLAN.actions,
      })
    );

    assert.ok(html.includes("Phase 1: 1,000 Customer Pilot Deployment"));
    assert.ok(html.includes("VP of Customer Support"));
    assert.ok(html.includes("Phase 2: Pilot Review and General Rollout Decision"));
    assert.ok(html.includes("CTO"));
    assert.ok(html.includes("$45,000"));
    assert.ok(html.includes("90%"));
    assert.ok(html.includes("Instant traffic fallback to legacy human support routing queue."));
  });

  // Test 4: Decision Gates rendering
  test("4. Decision Gates display evaluation checkpoints and mandatory rollback response", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionDecisionGates, {
        decisionGates: SAAS_SUPPORT_PLAN.decision_gates,
        actions: SAAS_SUPPORT_PLAN.actions,
      })
    );

    assert.ok(html.includes("Gate 1: Pilot Acceptance Checkpoint"));
    assert.ok(html.includes("Month 3 Completion Checkpoint"));
    assert.ok(html.includes("Halt rollout and revert customer routing"));
  });

  // Test 5: Unresolved Questions & Limitations
  test("5. Identifies compliance questions and analytical limitations", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionUnresolvedQuestions, {
        unresolvedQuestions: SAAS_SUPPORT_PLAN.unresolved_questions,
        limitations: SAAS_SUPPORT_PLAN.limitations,
      })
    );

    assert.ok(html.includes("HIPAA/SOC2 compliance"));
    assert.ok(html.includes("English-language support inquiries"));
  });

  // Test 6: Accessibility attributes & print styles
  test("6. Dashboard includes accessible roles, aria labels, and print-media responsive classes", () => {
    const html = renderToStaticMarkup(
      React.createElement(ActionIntelligenceDashboard, {
        analysisId: "analysis_test_acc",
        enabled: true,
      })
    );

    assert.ok(html.includes("aria-label=\"Action Intelligence\""));
    assert.ok(html.includes("print:hidden"));
    assert.ok(html.includes("print:border-zinc-300"));
  });
});
