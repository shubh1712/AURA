import type {
  ScenarioType,
  FutureScenario,
  EvidencePackage,
  DecisionModel,
  EvidenceItem,
  Assumption,
  Constraint,
  EvidenceGap,
} from "@/types";

export interface ScenarioConfig {
  type: ScenarioType;
  label: string;
  badgeClass: string;
  dotClass: string;
  borderClass: string;
  activeBorderClass: string;
  bgClass: string;
  activeBgClass: string;
  textClass: string;
  accentHex: string;
  tagline: string;
}

export const SCENARIO_CONFIGS: Record<ScenarioType, ScenarioConfig> = {
  optimistic: {
    type: "optimistic",
    label: "Optimistic",
    badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/80",
    dotClass: "bg-emerald-400",
    borderClass: "border-emerald-800/60 hover:border-emerald-700/80",
    activeBorderClass: "border-emerald-500 ring-2 ring-emerald-500/20 shadow-lg shadow-emerald-950/30",
    bgClass: "bg-emerald-950/10",
    activeBgClass: "bg-emerald-950/25",
    textClass: "text-emerald-300",
    accentHex: "#10b981",
    tagline: "Upside trajectory where positive catalysts manifest and assumptions hold.",
  },
  base_case: {
    type: "base_case",
    label: "Base Case",
    badgeClass: "bg-sky-950/60 text-sky-300 border-sky-800/80",
    dotClass: "bg-sky-400",
    borderClass: "border-sky-800/60 hover:border-sky-700/80",
    activeBorderClass: "border-sky-500 ring-2 ring-sky-500/20 shadow-lg shadow-sky-950/30",
    bgClass: "bg-sky-950/10",
    activeBgClass: "bg-sky-950/25",
    textClass: "text-sky-300",
    accentHex: "#0ea5e9",
    tagline: "Most probable operating reality under current epistemic evidence and constraints.",
  },
  pessimistic: {
    type: "pessimistic",
    label: "Pessimistic",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/80",
    dotClass: "bg-rose-400",
    borderClass: "border-rose-800/60 hover:border-rose-700/80",
    activeBorderClass: "border-rose-500 ring-2 ring-rose-500/20 shadow-lg shadow-rose-950/30",
    bgClass: "bg-rose-950/10",
    activeBgClass: "bg-rose-950/25",
    textClass: "text-rose-300",
    accentHex: "#f43f5e",
    tagline: "Downside stress-test where risks crystallize and critical friction occurs.",
  },
};

export function getScenarioConfig(type: ScenarioType | string): ScenarioConfig {
  if (type in SCENARIO_CONFIGS) {
    return SCENARIO_CONFIGS[type as ScenarioType];
  }
  // Fallback for unknown type
  return {
    type: "base_case",
    label: String(type).replace("_", " "),
    badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
    dotClass: "bg-zinc-400",
    borderClass: "border-zinc-800",
    activeBorderClass: "border-zinc-500 ring-1 ring-zinc-500/20",
    bgClass: "bg-zinc-900/30",
    activeBgClass: "bg-zinc-900/60",
    textClass: "text-zinc-300",
    accentHex: "#71717a",
    tagline: "Scenario trajectory.",
  };
}

/**
 * Formats scenario probability as an accessible, human-readable percentage.
 * Handles bounds safely (0.0 to 1.0).
 */
export function formatScenarioProbability(probability: number | null | undefined): string {
  if (probability === null || probability === undefined || Number.isNaN(probability)) {
    return "—";
  }
  const pct = Math.round(Number(probability) * 100);
  return `${pct}%`;
}

/**
 * Resolves an EvidenceItem referenced in supporting_evidence_item_ids from the EvidencePackage.
 */
export function resolveScenarioEvidenceItem(
  pkg: EvidencePackage | null | undefined,
  itemId: string
): EvidenceItem | null {
  if (!pkg || !pkg.items) return null;
  return pkg.items.find((item) => item.id === itemId) || null;
}

/**
 * Resolves an Assumption referenced in relevant_assumption_ids from the DecisionModel.
 */
export function resolveScenarioAssumption(
  model: DecisionModel | null | undefined,
  assumptionId: string
): Assumption | null {
  if (!model || !model.assumptions) return null;
  return model.assumptions.find((a) => a.id === assumptionId) || null;
}

/**
 * Resolves a Constraint referenced in relevant_constraint_ids from the DecisionModel.
 */
export function resolveScenarioConstraint(
  model: DecisionModel | null | undefined,
  constraintId: string
): Constraint | null {
  if (!model || !model.constraints) return null;
  return model.constraints.find((c) => c.id === constraintId) || null;
}

/**
 * Resolves an EvidenceGap referenced in relevant_gap_ids from the EvidencePackage.
 */
export function resolveScenarioGap(
  pkg: EvidencePackage | null | undefined,
  gapId: string
): EvidenceGap | null {
  if (!pkg || !pkg.gaps) return null;
  return pkg.gaps.find((g) => g.id === gapId) || null;
}

/**
 * Sorts scenarios in canonical order: Optimistic, Base Case, Pessimistic.
 */
export function sortScenariosCanonical(scenarios: FutureScenario[]): FutureScenario[] {
  const order: Record<ScenarioType, number> = {
    optimistic: 0,
    base_case: 1,
    pessimistic: 2,
  };
  return [...scenarios].sort(
    (a, b) => (order[a.scenario_type] ?? 99) - (order[b.scenario_type] ?? 99)
  );
}
