"use client";

import React, { useState } from "react";
import type { AnalysisResponse } from "@/types";
import { DashboardViewTabs, type DashboardViewType } from "./DashboardViewTabs";
import { OverviewView } from "./OverviewView";
import { ExploreView } from "./ExploreView";
import { ActionPlanView } from "./ActionPlanView";
import { DetailsView } from "./DetailsView";

interface VisualDecisionDashboardProps {
  result: AnalysisResponse;
  onReset: () => void;
  ownerId?: string | null;
}

export function VisualDecisionDashboard({
  result,
  onReset,
  ownerId,
}: VisualDecisionDashboardProps) {
  const [activeView, setActiveView] = useState<DashboardViewType>("overview");

  const handlePrint = () => {
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Accessible View Switcher Navigation Bar */}
      <DashboardViewTabs
        activeView={activeView}
        onViewChange={setActiveView}
        scenarioCount={result.scenarios?.scenarios?.length || 3}
        actionCount={result.recommendation?.action_plan?.actions?.length}
        onPrint={handlePrint}
        onReset={onReset}
      />

      {/* 2. Primary View 1: Overview (Concise Executive Brief) */}
      <div
        id="panel-overview"
        role="tabpanel"
        aria-labelledby="tab-overview"
        className={activeView === "overview" ? "block space-y-6" : "hidden print:block print:space-y-6"}
      >
        <OverviewView
          result={result}
          onExploreClick={() => setActiveView("explore")}
          onActionClick={() => setActiveView("action")}
          onDetailsClick={() => setActiveView("details")}
        />
      </div>

      {/* 3. Primary View 2: Explore (Scenarios, Resilience & What-If) */}
      <div
        id="panel-explore"
        role="tabpanel"
        aria-labelledby="tab-explore"
        className={activeView === "explore" ? "block space-y-6" : "hidden print:block print:space-y-6"}
      >
        <ExploreView result={result} ownerId={ownerId} />
      </div>

      {/* 4. Primary View 3: Action Plan (Roadmap, Roles, Gates, Intelligence) */}
      <div
        id="panel-action"
        role="tabpanel"
        aria-labelledby="tab-action"
        className={activeView === "action" ? "block space-y-6" : "hidden print:block print:space-y-6"}
      >
        <ActionPlanView result={result} ownerId={ownerId} />
      </div>

      {/* 5. Primary View 4: Details & Epistemic Audit (Full 6 Stages, Diagnostics) */}
      <div
        id="panel-details"
        role="tabpanel"
        aria-labelledby="tab-details"
        className={activeView === "details" ? "block space-y-6" : "hidden print:block print:space-y-6"}
      >
        <DetailsView result={result} />
      </div>
    </div>
  );
}
