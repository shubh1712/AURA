/**
 * AURA Visual Intelligence Layer
 *
 * Deterministic data-to-visual transformation utilities.
 * Extracts, normalizes, and groups existing backend API data into structured
 * metric summaries, distributions, and visual indicators.
 *
 * ZERO backend modifications. ZERO fabricated data.
 */

import type {
  AnalysisResponse,
  DecisionModel,
  EvidencePackage,
  ReasoningBoard,
  DecisionRecommendation,
  ScenarioSet,
  ResilienceReport,
  ActionItem,
  IntelligentActionItem,
} from "@/types";

export type UnifiedAction = ActionItem | IntelligentActionItem;

export interface ExecutiveKPI {
  id: string;
  label: string;
  value: string;
  subtext?: string;
  statusClass: string;
  badgeClass?: string;
  icon: string;
}

export interface RiskMatrixItem {
  id: string;
  type: "epistemic_risk" | "pivot_trigger";
  title: string;
  rank?: number;
  severity: "critical" | "warning" | "advisory";
  severityLabel: string;
  badgeClass: string;
}

export interface RoleDistribution {
  role: string;
  count: number;
  percentage: number;
  colorClass: string;
}

export interface StageProgressionItem {
  stage: number;
  id: string;
  title: string;
  shortName: string;
  isComplete: boolean;
  metricLabel: string;
  badgeClass: string;
}

const ROLE_COLORS = [
  "bg-emerald-500 text-emerald-300 border-emerald-700/60",
  "bg-sky-500 text-sky-300 border-sky-700/60",
  "bg-purple-500 text-purple-300 border-purple-700/60",
  "bg-amber-500 text-amber-300 border-amber-700/60",
  "bg-rose-500 text-rose-300 border-rose-700/60",
];

/**
 * Derives top executive KPIs from the complete analysis result.
 */
export function deriveExecutiveKPIs(result: AnalysisResponse): ExecutiveKPI[] {
  const kpis: ExecutiveKPI[] = [];
  const rec = result.recommendation;
  const dm = result.decision_model;
  const scenarios = result.scenarios?.scenarios || [];
  const board = result.reasoning_board;

  // 1. Decision Status
  if (rec?.decision_status) {
    const status = rec.decision_status.toLowerCase();
    const isProceed = status === "proceed";
    const isConditional = status === "conditional" || status === "monitor";

    kpis.push({
      id: "status",
      label: "Decision Stance",
      value: rec.decision_status.toUpperCase(),
      subtext: isProceed
        ? "Executable within baseline envelope"
        : isConditional
        ? "Contingent on stated conditions"
        : "Reconsideration indicated",
      statusClass: isProceed
        ? "text-emerald-400 border-emerald-800/60 bg-emerald-950/40"
        : isConditional
        ? "text-amber-400 border-amber-800/60 bg-amber-950/40"
        : "text-rose-400 border-rose-800/60 bg-rose-950/40",
      icon: isProceed ? "✓" : isConditional ? "⚠" : "✕",
    });
  }

  // 2. Boardroom Debate Consensus Ratio
  if (board?.perspectives && board.perspectives.length > 0) {
    let pro = 0;
    let con = 0;
    board.perspectives.forEach((p) => {
      (p.arguments || []).forEach((a) => {
        if (a.direction === "favorable") pro++;
        else if (a.direction === "unfavorable") con++;
      });
    });
    const total = pro + con;
    const consensusPct = total > 0 ? Math.round((pro / total) * 100) : 50;

    kpis.push({
      id: "consensus",
      label: "Boardroom Consensus",
      value: `${consensusPct}% Alignment`,
      subtext: `${pro} Favorable vs ${con} Concerns across 4 Perspectives`,
      statusClass:
        consensusPct >= 65
          ? "text-emerald-400 border-emerald-800/60 bg-emerald-950/40"
          : consensusPct >= 40
          ? "text-sky-400 border-sky-800/60 bg-sky-950/40"
          : "text-amber-400 border-amber-800/60 bg-amber-950/40",
      icon: "⚖",
    });
  }

  // 3. Modeled Scenarios & Base Case Probability
  if (scenarios.length > 0) {
    const baseScenario =
      scenarios.find((s) => s.scenario_type === "base_case") || scenarios[0];
    const basePct = Math.round((baseScenario.probability || 0) * 100);

    kpis.push({
      id: "scenarios",
      label: "Trajectory Forecast",
      value: `${basePct}% Base Likelihood`,
      subtext: `${scenarios.length} Scenarios (Stress test: ${
        Math.round((scenarios.find((s) => s.scenario_type === "pessimistic")?.probability || 0) * 100)
      }%)`,
      statusClass: "text-sky-400 border-sky-800/60 bg-sky-950/40",
      icon: "☊",
    });
  }

  // 4. Decision Complexity & Reversibility
  if (dm?.complexity) {
    const isReversible =
      dm.complexity.reversibility?.toLowerCase().includes("two_way") ||
      dm.complexity.reversibility?.toLowerCase().includes("reversible");

    kpis.push({
      id: "complexity",
      label: "Commitment Risk",
      value: isReversible ? "Two-Way Door" : "One-Way Door",
      subtext: typeof dm.complexity.score === "number"
        ? `Complexity Score: ${dm.complexity.score.toFixed(0)}/100 (${dm.complexity.level})`
        : `Level: ${dm.complexity.level || "Standard"}`,
      statusClass: isReversible
        ? "text-emerald-400 border-emerald-800/60 bg-emerald-950/40"
        : "text-rose-400 border-rose-800/60 bg-rose-950/40",
      icon: isReversible ? "⇄" : "⚡",
    });
  }

  // 5. Action Plan & Roadmap Readiness
  const actions = rec?.action_plan?.actions;
  if (actions && actions.length > 0) {
    const criticalCount = actions.filter(
      (a) => a.priority === "critical" || a.priority === "high"
    ).length;

    kpis.push({
      id: "actions",
      label: "Operational Roadmap",
      value: `${actions.length} Sequenced Actions`,
      subtext: `${criticalCount} High/Critical priorities mapped`,
      statusClass: "text-purple-400 border-purple-800/60 bg-purple-950/40",
      icon: "▶",
    });
  }

  return kpis;
}

/**
 * Derives operational role distribution from baseline or intelligent actions.
 */
export function deriveRoleDistribution(actions: UnifiedAction[]): RoleDistribution[] {
  if (!actions || actions.length === 0) return [];

  const counts: Record<string, number> = {};
  actions.forEach((a) => {
    const role =
      ("owner_role" in a && a.owner_role) ||
      ("responsible_role" in a && a.responsible_role) ||
      "Unassigned / General";
    counts[role] = (counts[role] || 0) + 1;
  });

  const total = actions.length;
  const roles = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([role, count], idx) => ({
      role,
      count,
      percentage: total > 0 ? Math.round((count / total) * 100) : 0,
      colorClass: ROLE_COLORS[idx % ROLE_COLORS.length],
    }));

  return roles;
}

/**
 * Derives 6-Stage progression status for Details & Epistemic Audit.
 */
export function deriveStageProgression(result: AnalysisResponse): StageProgressionItem[] {
  return [
    {
      stage: 1,
      id: "stage1",
      title: "Decision Framer & Model",
      shortName: "1. Framer",
      isComplete: Boolean(result.decision_model),
      metricLabel: result.decision_model
        ? `${result.decision_model.objectives?.length || 0} Objectives`
        : "Not computed",
      badgeClass: "text-indigo-400 border-indigo-800/60 bg-indigo-950/40",
    },
    {
      stage: 2,
      id: "stage2",
      title: "Evidence Engine & Citations",
      shortName: "2. Evidence",
      isComplete: Boolean(result.evidence_package),
      metricLabel: result.evidence_package
        ? `${result.evidence_package.items?.length || 0} Citations`
        : "Not computed",
      badgeClass: "text-sky-400 border-sky-800/60 bg-sky-950/40",
    },
    {
      stage: 3,
      id: "stage3",
      title: "AI Boardroom Deliberation",
      shortName: "3. Boardroom",
      isComplete: Boolean(result.reasoning_board),
      metricLabel: result.reasoning_board
        ? `${result.reasoning_board.perspectives?.length || 0} Perspectives`
        : "Not computed",
      badgeClass: "text-purple-400 border-purple-800/60 bg-purple-950/40",
    },
    {
      stage: 4,
      id: "stage4",
      title: "Executive Recommendation",
      shortName: "4. Recommendation",
      isComplete: Boolean(result.recommendation),
      metricLabel: result.recommendation?.decision_status?.toUpperCase() || "Not computed",
      badgeClass: "text-emerald-400 border-emerald-800/60 bg-emerald-950/40",
    },
    {
      stage: 5,
      id: "stage5",
      title: "Future Scenario Engine",
      shortName: "5. Scenarios",
      isComplete: Boolean(result.scenarios?.scenarios?.length),
      metricLabel: result.scenarios
        ? `${result.scenarios.scenarios?.length || 0} Trajectories`
        : "Not computed",
      badgeClass: "text-blue-400 border-blue-800/60 bg-blue-950/40",
    },
    {
      stage: 6,
      id: "stage6",
      title: "Stress Testing & Resilience",
      shortName: "6. Resilience",
      isComplete: Boolean(result.resilience),
      metricLabel: typeof (result.resilience?.overall_score ?? (result.resilience as unknown as Record<string, unknown>)?.overall_resilience_score) === "number"
        ? `${((result.resilience?.overall_score ?? (result.resilience as unknown as Record<string, unknown>)?.overall_resilience_score) as number).toFixed(0)}/100 Score`
        : "Not computed",
      badgeClass: "text-amber-400 border-amber-800/60 bg-amber-950/40",
    },
  ];
}
