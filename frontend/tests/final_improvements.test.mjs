import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DecisionForm } from "../src/components/decision/DecisionForm.tsx";
import { StageAwareProgress } from "../src/components/decision/StageAwareProgress.tsx";
import { Header } from "../src/components/common/Header.tsx";
import { ExploreView } from "../src/components/decision/dashboard/ExploreView.tsx";
import { OverviewView } from "../src/components/decision/dashboard/OverviewView.tsx";
import { DashboardViewTabs } from "../src/components/decision/dashboard/DashboardViewTabs.tsx";
import { BoardroomAlignmentGauge } from "../src/components/decision/charts/BoardroomAlignmentGauge.tsx";
import { ScenarioProbabilitySpectrum } from "../src/components/decision/charts/ScenarioProbabilitySpectrum.tsx";
import { ActionTimelineVisual } from "../src/components/decision/charts/ActionTimelineVisual.tsx";
import { DecisionModelSummary } from "../src/components/decision/DecisionModelSummary.tsx";
import { createAnalysisJob, getAnalysisJobStatus, getAnalysisJobResult } from "../src/lib/api.ts";

const MOCK_SCENARIOS = {
  summary: "Comprehensive three-scenario modeling of architectural scaling.",
  scenarios: [
    {
      scenario_type: "optimistic",
      name: "High Growth Expansion",
      probability: 0.35,
      narrative: "Infrastructure accommodates 3x traffic with minimal latency overhead.",
      timeline: [{ milestone: "Cluster deployed", timeframe: "Month 1" }],
      key_events: ["Early adoption", "Low error rate"],
      opportunities: ["Cost savings"],
      risks: ["Resource contention under sudden spike"],
    },
    {
      scenario_type: "base_case",
      name: "Gradual Read Optimization",
      probability: 0.50,
      narrative: "Read replicas provide 70% query offload matching expected usage.",
      timeline: [{ milestone: "Replica verification", timeframe: "Week 3" }],
      key_events: ["Query caching active"],
      opportunities: ["Predictable cost"],
      risks: ["Replication lag under batch writes"],
    },
    {
      scenario_type: "pessimistic",
      name: "Operational Bottleneck",
      probability: 0.15,
      narrative: "Migration complexity introduces latency degradation.",
      timeline: [{ milestone: "Rollback window", timeframe: "Week 4" }],
      key_events: ["Unplanned failover"],
      opportunities: [],
      risks: ["Data inconsistency during failover"],
    },
  ],
};

const MOCK_RESULT = {
  analysis_id: "test-analysis-final-01",
  status: "completed",
  question: "Should we optimize PostgreSQL with read replicas or migrate to a distributed cluster?",
  message: "Analysis completed successfully.",
  decision_model: {
    id: "dm-01",
    decision: {
      summary: "Database Architecture Scaling Strategy",
      time_horizon: "medium_term",
    },
    constraints: [],
    objectives: [],
    variables: [],
    assumptions: [],
  },
  recommendation: {
    id: "rec-01",
    decision_status: "proceed",
    recommended_action: "Implement PostgreSQL read replicas with connection pooling.",
    executive_rationale: "Maximizes throughput within existing operational envelope.",
    alternative_options: [],
    uncertainty_assessment: {
      critical_missing_information: ["Peak query write-to-read ratio"],
      conditions_changing_recommendation: ["Write volume exceeds 50k writes/sec"],
    },
  },
  scenarios: MOCK_SCENARIOS,
  resilience: {
    overall_resilience_score: 78.5,
    calculation_version: "2.1",
    risk_factors: [],
  },
};

describe("AURA Final Premium Transformation Tests", () => {
  // ----------------------------------------------------------------------------
  // 1. Stop Analyzing: User Control & UI Presence
  // ----------------------------------------------------------------------------
  test("1. DecisionForm renders Stop Analyzing button when analysis is active (isLoading = true)", () => {
    let stopped = false;
    const markup = renderToStaticMarkup(
      React.createElement(DecisionForm, {
        formData: { question: "Test question", context: "", constraints: "" },
        isLoading: true,
        jobStatus: "running",
        pipelineStage: "stage3_ai_boardroom",
        progressMessage: "Evaluating perspectives...",
        validationError: null,
        apiError: null,
        onFieldChange: () => {},
        onSubmit: () => {},
        onReset: () => {},
        onClearError: () => {},
        onStop: () => {
          stopped = true;
        },
      })
    );

    assert.ok(
      markup.includes("Stop Analyzing"),
      "Must render Stop Analyzing button while isLoading is true"
    );
    assert.ok(
      markup.includes("Analyzing Decision..."),
      "Must render active loading indicator"
    );
    // Developer endpoint string must NOT be displayed
    assert.ok(
      !markup.includes("Calls FastAPI /api/analysis/jobs"),
      "Developer label 'Calls FastAPI /api/analysis/jobs' must be removed from the UI"
    );
    assert.ok(
      markup.includes("Autonomous 6-Stage Deliberation"),
      "Must display professional engine text"
    );
  });

  // ----------------------------------------------------------------------------
  // 2. StageAwareProgress: Stop Analyzing Control
  // ----------------------------------------------------------------------------
  test("2. StageAwareProgress renders Stop Analyzing button in header during execution", () => {
    const markup = renderToStaticMarkup(
      React.createElement(StageAwareProgress, {
        status: "running",
        stage: "stage2_evidence_engine",
        progressMessage: "Retrieving sources...",
        jobId: "job-aura-12345",
        onStop: () => {},
      })
    );

    assert.ok(
      markup.includes("Stop Analyzing"),
      "Must render Stop Analyzing action in StageAwareProgress during active run"
    );
    assert.ok(
      markup.includes("Analysis in Progress"),
      "Must render progress header"
    );
  });

  // ----------------------------------------------------------------------------
  // 3. API Client AbortSignal Support
  // ----------------------------------------------------------------------------
  test("3. createAnalysisJob, getAnalysisJobStatus, and getAnalysisJobResult accept AbortSignal and abort cleanly", async () => {
    const controller = new AbortController();
    controller.abort(); // already aborted

    await assert.rejects(
      async () => {
        await createAnalysisJob(
          { question: "Should we scale?", context: undefined, constraints: [] },
          null,
          controller.signal
        );
      },
      (err) => err.name === "AbortError",
      "createAnalysisJob must respect aborted signal"
    );

    await assert.rejects(
      async () => {
        await getAnalysisJobStatus("job-test", null, controller.signal);
      },
      (err) => err.name === "AbortError",
      "getAnalysisJobStatus must respect aborted signal"
    );

    await assert.rejects(
      async () => {
        await getAnalysisJobResult("job-test", null, controller.signal);
      },
      (err) => err.name === "AbortError",
      "getAnalysisJobResult must respect aborted signal"
    );
  });

  // ----------------------------------------------------------------------------
  // 4. Promoted Interactive Future Explorer Tree in ExploreView
  // ----------------------------------------------------------------------------
  test("4. ExploreView prominently features FutureExplorerTree with professional heading", () => {
    const markup = renderToStaticMarkup(
      React.createElement(ExploreView, {
        result: MOCK_RESULT,
      })
    );

    assert.ok(
      markup.includes("Interactive Future Scenario Tree"),
      "ExploreView must feature the promoted Interactive Future Scenario Tree"
    );
    assert.ok(
      markup.includes("Explore cascading downstream implications and branch probabilities"),
      "Must include clear, understandable explanation"
    );
    assert.ok(
      markup.includes("Pan &amp; Zoom Enabled") || markup.includes("Pan & Zoom Enabled"),
      "Must highlight interactive canvas capabilities"
    );
  });

  // ----------------------------------------------------------------------------
  // 5. Action Intelligence Shortcut in OverviewView
  // ----------------------------------------------------------------------------
  test("5. OverviewView renders Action Intelligence navigation shortcut with clear CTA", () => {
    let actionNavigated = false;
    const markup = renderToStaticMarkup(
      React.createElement(OverviewView, {
        result: MOCK_RESULT,
        onActionClick: () => {
          actionNavigated = true;
        },
      })
    );

    assert.ok(
      markup.includes("Turn Recommendation Into a Grounded Execution Roadmap"),
      "OverviewView must render the Action Intelligence discovery heading"
    );
    assert.ok(
      markup.includes("Open Action Plan &amp; Roadmap") || markup.includes("Open Action Plan & Roadmap"),
      "Must provide prominent navigation button to Action Plan tab"
    );
  });

  // ----------------------------------------------------------------------------
  // 6. Header Visual and Terminology Refinements
  // ----------------------------------------------------------------------------
  test("6. Header renders clean, non-technical status labels", () => {
    const markup = renderToStaticMarkup(React.createElement(Header));

    assert.ok(
      !markup.includes("Backend Offline (Port 8000)"),
      "Raw port references must be removed from Header"
    );
    assert.ok(
      markup.includes("AURA") && markup.includes("Decision Intelligence"),
      "Header must render brand identity"
    );
  });

  // ----------------------------------------------------------------------------
  // 7. Navigation Polish: Semibold Tabs & Prominent Actions
  // ----------------------------------------------------------------------------
  test("7. DashboardViewTabs renders semibold typography, enlarged icons, and prominent action buttons", () => {
    let resetClicked = false;
    let printClicked = false;

    const markup = renderToStaticMarkup(
      React.createElement(DashboardViewTabs, {
        activeView: "overview",
        onViewChange: () => {},
        scenarioCount: 3,
        actionCount: 4,
        onPrint: () => {
          printClicked = true;
        },
        onReset: () => {
          resetClicked = true;
        },
      })
    );

    // Check tab labels and badge
    assert.ok(markup.includes("Overview"), "Must render Overview tab");
    assert.ok(markup.includes("Explore"), "Must render Explore tab");
    assert.ok(markup.includes("Action Plan"), "Must render Action Plan tab");
    assert.ok(markup.includes("Details &amp; Audit") || markup.includes("Details & Audit"), "Must render Details tab");

    // Check typography & style tokens
    assert.ok(markup.includes("font-semibold"), "Tabs must use font-semibold");
    assert.ok(markup.includes("h-[18px] w-[18px]"), "Tab icons must be appropriately sized (18px)");

    // Check buttons
    assert.ok(markup.includes("Export Report"), "Must render Export Report button");
    assert.ok(markup.includes("New Analysis"), "Must render New Analysis button");
    assert.ok(markup.includes("bg-emerald-950/40"), "New Analysis must have emerald accent background");
  });

  // ----------------------------------------------------------------------------
  // 8. Boardroom Alignment Gauge: Real Data Synthesis
  // ----------------------------------------------------------------------------
  test("8. BoardroomAlignmentGauge calculates and renders consensus distribution from real data", () => {
    const mockBoard = {
      id: "board-01",
      decision_model_id: "dm-01",
      evidence_package_id: "ep-01",
      perspectives: [
        {
          id: "p-growth",
          perspective_type: "growth",
          summary: "Market expansion upside is strong.",
          arguments: [
            { id: "a1", claim: "Captures 25% more queries", direction: "favorable", basis: "evidence", reasoning: "", evidence_item_ids: [], requirement_ids: [], assumption_ids: [], unknown_ids: [], evidence_gap_ids: [], related_entity_ids: [] },
            { id: "a2", claim: "Accelerates feature rollout", direction: "favorable", basis: "inference", reasoning: "", evidence_item_ids: [], requirement_ids: [], assumption_ids: [], unknown_ids: [], evidence_gap_ids: [], related_entity_ids: [] },
          ],
          concerns: ["Engineering capacity"],
          opportunities: ["Global replication"],
          critical_assumption_ids: [],
          evidence_gap_ids: [],
          unresolved_questions: [],
          limitations: [],
        },
        {
          id: "p-finance",
          perspective_type: "finance",
          summary: "Cost envelope is within acceptable ROI.",
          arguments: [
            { id: "a3", claim: "Low capital expenditure", direction: "favorable", basis: "evidence", reasoning: "", evidence_item_ids: [], requirement_ids: [], assumption_ids: [], unknown_ids: [], evidence_gap_ids: [], related_entity_ids: [] },
            { id: "a4", claim: "Operational maintenance overhead", direction: "unfavorable", basis: "inference", reasoning: "", evidence_item_ids: [], requirement_ids: [], assumption_ids: [], unknown_ids: [], evidence_gap_ids: [], related_entity_ids: [] },
          ],
          concerns: ["Cloud egress fees"],
          opportunities: ["Tiered caching savings"],
          critical_assumption_ids: [],
          evidence_gap_ids: [],
          unresolved_questions: [],
          limitations: [],
        },
      ],
      disagreements: [],
      synthesis: {
        summary: "Broad consensus on initial read-replica strategy.",
        areas_of_agreement: ["Read replicas offer best short-term ROI"],
        disagreement_ids: [],
        critical_assumption_ids: [],
        critical_evidence_gap_ids: [],
        evidence_sensitive_points: [],
        unresolved_questions: [],
      },
    };

    const markup = renderToStaticMarkup(
      React.createElement(BoardroomAlignmentGauge, { board: mockBoard })
    );

    assert.ok(markup.includes("AI Boardroom Alignment &amp; Argument Distribution") || markup.includes("AI Boardroom Alignment & Argument Distribution"));
    assert.ok(markup.includes("Favorable:"));
    assert.ok(markup.includes("Growth &amp; Market") || markup.includes("Growth & Market"));
    assert.ok(markup.includes("Finance &amp; ROI") || markup.includes("Finance & ROI"));
    assert.ok(markup.includes("Read replicas offer best short-term ROI"));
  });

  // ----------------------------------------------------------------------------
  // 9. Boardroom Alignment Gauge: Missing Data Safety
  // ----------------------------------------------------------------------------
  test("9. BoardroomAlignmentGauge returns null safely when board or perspectives are missing", () => {
    const markupNull = renderToStaticMarkup(
      React.createElement(BoardroomAlignmentGauge, { board: null })
    );
    assert.equal(markupNull, "");

    const markupEmpty = renderToStaticMarkup(
      React.createElement(BoardroomAlignmentGauge, { board: { perspectives: [] } })
    );
    assert.equal(markupEmpty, "");
  });

  // ----------------------------------------------------------------------------
  // 10. Scenario Probability Spectrum & Scenario Card Ratio Meter
  // ----------------------------------------------------------------------------
  test("10. ScenarioProbabilitySpectrum renders proportional 100% stacked bar and ExploreView renders ratio meters", () => {
    let selected = null;
    const markupSpectrum = renderToStaticMarkup(
      React.createElement(ScenarioProbabilitySpectrum, {
        scenarios: MOCK_SCENARIOS.scenarios,
        selectedScenarioType: "base_case",
        onSelectScenario: (t) => {
          selected = t;
        },
      })
    );

    assert.ok(markupSpectrum.includes("100% Proportional Probability Distribution"));
    assert.ok(markupSpectrum.includes("35%"), "Must render 35% probability for optimistic");
    assert.ok(markupSpectrum.includes("50%"), "Must render 50% probability for base case");
    assert.ok(markupSpectrum.includes("15%"), "Must render 15% probability for pessimistic");

    const markupExplore = renderToStaticMarkup(
      React.createElement(ExploreView, {
        result: MOCK_RESULT,
      })
    );

    assert.ok(markupExplore.includes("Upside Driver"), "Must render upside driver ratio text");
    assert.ok(markupExplore.includes("Vulnerabilit"), "Must render vulnerability ratio text");
    assert.ok(markupExplore.includes('role="meter"'), "Must render ratio meter bar");
  });

  // ----------------------------------------------------------------------------
  // 11. ActionTimelineVisual: Execution Priority Load & Dependency Mapping
  // ----------------------------------------------------------------------------
  test("11. ActionTimelineVisual renders execution priority distribution strip", () => {
    const mockActions = [
      { id: "act-1", title: "Deploy read replica", priority: "critical", time_horizon: "Week 1", dependencies: [] },
      { id: "act-2", title: "Configure PgBouncer", priority: "high", time_horizon: "Week 2", dependencies: ["act-1"] },
      { id: "act-3", title: "Benchmark latency", priority: "medium", time_horizon: "Week 3", dependencies: ["act-2"] },
      { id: "act-4", title: "Document runbook", priority: "low", time_horizon: "Week 4", dependencies: [] },
    ];

    const markup = renderToStaticMarkup(
      React.createElement(ActionTimelineVisual, { actions: mockActions })
    );

    assert.ok(markup.includes("Execution Priority Load:"));
    assert.ok(markup.includes("2 High/Critical"));
    assert.ok(markup.includes("4 Sequenced Actions"));
    assert.ok(markup.includes("2 Dependencies Mapped"));
    assert.ok(markup.includes("● 1 Critical"));
    assert.ok(markup.includes("● 1 High"));
  });

  // ----------------------------------------------------------------------------
  // 12. DecisionModelSummary: Visual Complexity Gauge & Reversibility Commitment
  // ----------------------------------------------------------------------------
  test("12. DecisionModelSummary renders visual complexity gauge bar and reversibility commitment badge", () => {
    const mockModel = {
      id: "dm-01",
      decision: {
        summary: "Database Architecture Scaling Strategy",
        decision_type: "technical_architecture",
        time_horizon: "medium_term",
      },
      complexity: {
        level: "medium",
        score: 65,
        reversibility: "two_way_door",
        reasoning: "Replicas can be de-provisioned without permanent data loss.",
      },
      objectives: [{ id: "obj-1", description: "Keep p99 query latency under 50ms" }],
      constraints: [{ id: "c-1", name: "Budget", description: "Under $2,000/mo" }],
      tradeoffs: [],
      variables: [],
      assumptions: [],
      unknowns: [],
    };

    const markup = renderToStaticMarkup(
      React.createElement(DecisionModelSummary, { model: mockModel })
    );

    assert.ok(markup.includes("Two Way Door Commitment"));
    assert.ok(markup.includes("Score:"));
    assert.ok(markup.includes("65"));
    assert.ok(markup.includes('role="progressbar"'));
    assert.ok(markup.includes("Replicas can be de-provisioned without permanent data loss."));
  });
});
