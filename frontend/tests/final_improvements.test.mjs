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
import { ExecutiveKpiGrid } from "../src/components/decision/charts/ExecutiveKpiGrid.tsx";
import { RiskUncertaintyMatrix } from "../src/components/decision/charts/RiskUncertaintyMatrix.tsx";
import { StageProgressionTracker } from "../src/components/decision/charts/StageProgressionTracker.tsx";
import { deriveExecutiveKPIs, deriveRoleDistribution, deriveStageProgression } from "../src/lib/visualIntelligence.ts";
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
    complexity: {
      level: "medium",
      score: 65,
      reversibility: "two_way_door",
      reasoning: "Read replicas can be de-provisioned cleanly.",
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
    action_plan: {
      id: "ap-01",
      strategy_summary: "Phased database replica rollout",
      actions: [
        { id: "act-1", title: "Provision replica", priority: "critical", time_horizon: "Week 1", sequence: 1 },
        { id: "act-2", title: "Setup PgBouncer", priority: "high", time_horizon: "Week 2", sequence: 2 },
      ],
    },
    uncertainty_assessment: {
      critical_missing_information: ["Peak query write-to-read ratio"],
      conditions_changing_recommendation: ["Write volume exceeds 50k writes/sec"],
    },
  },
  reasoning_board: {
    id: "rb-01",
    decision_model_id: "dm-01",
    evidence_package_id: "ep-01",
    perspectives: [
      {
        id: "p1",
        perspective_type: "growth",
        summary: "Read replicas unlock 3x throughput.",
        arguments: [{ id: "a1", claim: "High scalability", direction: "favorable", basis: "evidence", reasoning: "", evidence_item_ids: [], requirement_ids: [], assumption_ids: [], unknown_ids: [], evidence_gap_ids: [], related_entity_ids: [] }],
        concerns: [],
        opportunities: [],
        critical_assumption_ids: [],
        evidence_gap_ids: [],
        unresolved_questions: [],
        limitations: [],
      },
    ],
    disagreements: [],
    synthesis: {
      summary: "Consensus on replica approach.",
      areas_of_agreement: ["Replica is cost effective"],
      disagreement_ids: [],
      critical_assumption_ids: [],
      critical_evidence_gap_ids: [],
      evidence_sensitive_points: [],
      unresolved_questions: [],
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

  // ----------------------------------------------------------------------------
  // 13. Visual Intelligence: ExecutiveKpiGrid & deriveExecutiveKPIs
  // ----------------------------------------------------------------------------
  test("13. deriveExecutiveKPIs extracts structured KPIs and ExecutiveKpiGrid renders responsive cards", () => {
    const kpis = deriveExecutiveKPIs(MOCK_RESULT);
    assert.ok(kpis.length >= 3, "Must derive at least 3 executive KPIs from complete result");

    const statusKpi = kpis.find((k) => k.id === "status");
    assert.ok(statusKpi, "Must include decision status KPI");
    assert.equal(statusKpi.value, "PROCEED");

    const markup = renderToStaticMarkup(
      React.createElement(ExecutiveKpiGrid, { kpis })
    );

    assert.ok(markup.includes('role="region"'));
    assert.ok(markup.includes("PROCEED"));
    assert.ok(markup.includes("Trajectory Forecast") || markup.includes("Decision Stance"));
  });

  // ----------------------------------------------------------------------------
  // 14. Visual Intelligence: Operational Role Ownership in ActionTimelineVisual
  // ----------------------------------------------------------------------------
  test("14. deriveRoleDistribution calculates accurate role counts and ActionTimelineVisual renders role strip", () => {
    const actions = [
      { id: "1", title: "Config", priority: "high", owner_role: "DevOps Lead", dependencies: [] },
      { id: "2", title: "Migrate", priority: "critical", owner_role: "Database Architect", dependencies: ["1"] },
      { id: "3", title: "Test", priority: "medium", owner_role: "DevOps Lead", dependencies: ["2"] },
    ];

    const roles = deriveRoleDistribution(actions);
    assert.equal(roles.length, 2);
    assert.equal(roles[0].role, "DevOps Lead");
    assert.equal(roles[0].count, 2);
    assert.equal(roles[0].percentage, 67);

    const markup = renderToStaticMarkup(
      React.createElement(ActionTimelineVisual, { actions })
    );

    assert.ok(markup.includes("Operational Ownership &amp; Accountability") || markup.includes("Operational Ownership & Accountability"));
    assert.ok(markup.includes("DevOps Lead"));
    assert.ok(markup.includes("Database Architect"));
    assert.ok(markup.includes("2 Distinct Roles"));
  });

  // ----------------------------------------------------------------------------
  // 15. RiskUncertaintyMatrix: Ranked Epistemic Gaps & Dynamic Pivot Triggers
  // ----------------------------------------------------------------------------
  test("15. RiskUncertaintyMatrix renders ranked sensitivity cards and pivot triggers", () => {
    const missing = ["Peak write volume", "Secondary replica latency"];
    const conditions = ["Write traffic exceeds 50k req/sec"];

    const markup = renderToStaticMarkup(
      React.createElement(RiskUncertaintyMatrix, {
        missingInputs: missing,
        changingConditions: conditions,
      })
    );

    assert.ok(markup.includes("Epistemic Boundary Risks"));
    assert.ok(markup.includes("2 Ranked Gaps"));
    assert.ok(markup.includes("#1"));
    assert.ok(markup.includes("Peak write volume"));
    assert.ok(markup.includes("Dynamic Pivot Triggers"));
    assert.ok(markup.includes("Write traffic exceeds 50k req/sec"));
  });

  // ----------------------------------------------------------------------------
  // 16. StageProgressionTracker: 6-Stage Audit Pipeline Flow
  // ----------------------------------------------------------------------------
  test("16. deriveStageProgression maps 6 stages and StageProgressionTracker renders interactive pipeline flow", () => {
    const stages = deriveStageProgression(MOCK_RESULT);
    assert.equal(stages.length, 6, "Must define exactly 6 stages");
    assert.ok(stages[0].isComplete, "Stage 1 must be complete");
    assert.ok(stages[3].isComplete, "Stage 4 must be complete");

    const markup = renderToStaticMarkup(
      React.createElement(StageProgressionTracker, {
        stages,
        openSections: { stage1: true },
      })
    );

    assert.ok(markup.includes("Audit Pipeline Flow"));
    assert.ok(markup.includes("Framer"));
    assert.ok(markup.includes("Evidence"));
    assert.ok(markup.includes("Boardroom"));
    assert.ok(markup.includes("Recommendation"));
    assert.ok(markup.includes("Scenarios"));
    assert.ok(markup.includes("Resilience"));
  });

  // ----------------------------------------------------------------------------
  // 17. Analysis HTTP 504: DecisionForm User-Friendly 503 Display
  // ----------------------------------------------------------------------------
  test("17. DecisionForm renders 503 Service Unavailable title and Gemini message when analysis fails with HTTP 504", () => {
    const markup = renderToStaticMarkup(
      React.createElement(DecisionForm, {
        formData: { question: "Scale cluster?", context: "", constraints: "" },
        isLoading: false,
        jobStatus: null,
        apiError: "The decision analysis exceeded its allowed processing time.",
        apiErrorStatusCode: 504,
        onFieldChange: () => {},
        onSubmit: () => {},
        onReset: () => {},
        onClearError: () => {},
      })
    );

    // Displays the user-friendly 503-style title
    assert.ok(
      markup.includes("503 — AI Service Temporarily Unavailable"),
      "Must display '503 — AI Service Temporarily Unavailable' title"
    );
    // Displays the friendly message explaining Gemini traffic
    const normalizedMarkup = markup.replace(/&#x27;/g, "'");
    assert.ok(
      normalizedMarkup.includes(
        "Gemini may be experiencing high traffic or taking longer than expected to respond. Your analysis couldn't be completed in time. Please try again shortly."
      ),
      "Must display user-friendly Gemini traffic explanation"
    );
    // Does NOT render an intrusive 'HTTP 504' badge next to the 503-style title
    assert.ok(
      !markup.includes("HTTP 504"),
      "Must not render raw 'HTTP 504' badge next to 503-style service unavailable title"
    );
  });

  // ----------------------------------------------------------------------------
  // 18. Analysis Timed-Out Job State: StageAwareProgress User-Friendly 503 Display
  // ----------------------------------------------------------------------------
  test("18. StageAwareProgress renders 503 Service Unavailable title, Gemini message, and Retry button when timed out or status is 504", () => {
    let retried = false;
    const markup = renderToStaticMarkup(
      React.createElement(StageAwareProgress, {
        status: "timed_out",
        stage: "stage2_evidence_engine",
        error: "Gateway timeout during analysis",
        errorStatusCode: 504,
        onRetry: () => {
          retried = true;
        },
      })
    );

    // Displays 503 header and error title
    assert.ok(
      markup.includes("503 — AI Service Temporarily Unavailable"),
      "Must display '503 — AI Service Temporarily Unavailable' in StageAwareProgress"
    );
    // Displays the friendly message explaining Gemini traffic
    const normalizedMarkup = markup.replace(/&#x27;/g, "'");
    assert.ok(
      normalizedMarkup.includes(
        "Gemini may be experiencing high traffic or taking longer than expected to respond. Your analysis couldn't be completed in time. Please try again shortly."
      ),
      "Must display user-friendly Gemini traffic explanation"
    );
    // Retry button is preserved
    assert.ok(
      markup.includes("Retry Analysis"),
      "Must preserve Retry Analysis action button"
    );
  });

  // ----------------------------------------------------------------------------
  // 19. Preserves Standard Error Display for HTTP 400, 403, and 500 Errors
  // ----------------------------------------------------------------------------
  test("19. DecisionForm and StageAwareProgress preserve standard error labels and original messages for HTTP 400, 403, and 500", () => {
    // Test HTTP 400 Bad Request
    const markup400 = renderToStaticMarkup(
      React.createElement(DecisionForm, {
        formData: { question: "", context: "", constraints: "" },
        isLoading: false,
        jobStatus: null,
        apiError: "Question must be at least 10 characters.",
        apiErrorStatusCode: 400,
        onFieldChange: () => {},
        onSubmit: () => {},
        onReset: () => {},
        onClearError: () => {},
      })
    );
    assert.ok(markup400.includes("Analysis Error"), "HTTP 400 must display 'Analysis Error'");
    assert.ok(markup400.includes("HTTP 400"), "HTTP 400 must display HTTP 400 badge");
    assert.ok(markup400.includes("Question must be at least 10 characters."), "HTTP 400 must retain original message");
    assert.ok(!markup400.includes("503 — AI Service Temporarily Unavailable"), "HTTP 400 must not display 503 title");
    assert.ok(!markup400.includes("Gemini may be experiencing high traffic"), "HTTP 400 must not display Gemini explanation");

    // Test HTTP 403 Forbidden
    const markup403 = renderToStaticMarkup(
      React.createElement(DecisionForm, {
        formData: { question: "Restricted analysis?", context: "", constraints: "" },
        isLoading: false,
        jobStatus: null,
        apiError: "Access denied to organization workspace.",
        apiErrorStatusCode: 403,
        onFieldChange: () => {},
        onSubmit: () => {},
        onReset: () => {},
        onClearError: () => {},
      })
    );
    assert.ok(markup403.includes("Analysis Error"), "HTTP 403 must display 'Analysis Error'");
    assert.ok(markup403.includes("HTTP 403"), "HTTP 403 must display HTTP 403 badge");
    assert.ok(markup403.includes("Access denied to organization workspace."), "HTTP 403 must retain original message");
    assert.ok(!markup403.includes("503 — AI Service Temporarily Unavailable"), "HTTP 403 must not display 503 title");
    assert.ok(!markup403.includes("Gemini may be experiencing high traffic"), "HTTP 403 must not display Gemini explanation");

    // Test HTTP 500 Internal Server Error in StageAwareProgress
    const markup500 = renderToStaticMarkup(
      React.createElement(StageAwareProgress, {
        status: "failed",
        stage: "stage1_decision_boundary",
        error: "Internal database query failed.",
        errorStatusCode: 500,
        onRetry: () => {},
      })
    );
    assert.ok(markup500.includes("Analysis Interrupted"), "HTTP 500 must display 'Analysis Interrupted' header");
    assert.ok(markup500.includes("Execution Error (HTTP 500)"), "HTTP 500 must display 'Execution Error (HTTP 500)' title");
    assert.ok(markup500.includes("Internal database query failed."), "HTTP 500 must retain original message");
    assert.ok(!markup500.includes("503 — AI Service Temporarily Unavailable"), "HTTP 500 must not display 503 title");
    assert.ok(!markup500.includes("Gemini may be experiencing high traffic"), "HTTP 500 must not display Gemini explanation");
  });
});
