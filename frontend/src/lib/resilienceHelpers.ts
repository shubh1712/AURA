/**
 * Resilience Engine Helper Functions & Canonical Configurations.
 * Day 6 Phase 6C: Normalization, canonical sorting, rating metadata, and formatting.
 */

import type {
  ResiliencePillar,
  ResilienceRating,
  ResilienceSubScore,
} from "@/types/resilience";

export interface NormalizedPillarScore {
  category: string;
  pillarKey: ResiliencePillar;
  title: string;
  shortTitle: string;
  description: string;
  score: number;
  maxScore: number;
  percentage: number;
  rationale: string;
  vulnerabilities: string[];
}

export interface RatingMetadata {
  rating: ResilienceRating;
  label: string;
  description: string;
  rangeText: string;
  colorClass: {
    text: string;
    bg: string;
    border: string;
    gaugeStroke: string;
    badgeBg: string;
    badgeBorder: string;
    badgeText: string;
  };
}

export interface StressTestMetadata {
  passed: boolean;
  statusLabel: string;
  badgeLabel: string;
  description: string;
  thresholdsExplanation: string;
}

// -----------------------------------------------------------------------------
// 1. Canonical Pillar Definitions & Ordering
// -----------------------------------------------------------------------------

export const CANONICAL_PILLAR_KEYS: ResiliencePillar[] = [
  "constraint_boundary_tolerance",
  "pessimistic_scenario_survivability",
  "contingency_and_fallback_coverage",
  "information_robustness",
];

export const PILLAR_DEFINITIONS: Record<
  string,
  {
    title: string;
    shortTitle: string;
    description: string;
    defaultMax: number;
  }
> = {
  constraint_boundary_tolerance: {
    title: "Constraint Boundary Tolerance",
    shortTitle: "Constraint Tolerance",
    description:
      "Evaluates decision reversibility and operational headroom against hard constraints under stress.",
    defaultMax: 25.0,
  },
  pessimistic_scenario_survivability: {
    title: "Pessimistic Scenario Survivability",
    shortTitle: "Pessimistic Survivability",
    description:
      "Measures survivability, adverse probability exposure, and mitigations across the pessimistic trajectory.",
    defaultMax: 25.0,
  },
  pessimistic_survivability: {
    title: "Pessimistic Scenario Survivability",
    shortTitle: "Pessimistic Survivability",
    description:
      "Measures survivability, adverse probability exposure, and mitigations across the pessimistic trajectory.",
    defaultMax: 25.0,
  },
  contingency_and_fallback_coverage: {
    title: "Contingency & Fallback Coverage",
    shortTitle: "Contingency Coverage",
    description:
      "Assesses formal decision gates, fallback procedures, pre-authorized alternatives, and rollback capability.",
    defaultMax: 25.0,
  },
  contingency_coverage: {
    title: "Contingency & Fallback Coverage",
    shortTitle: "Contingency Coverage",
    description:
      "Assesses formal decision gates, fallback procedures, pre-authorized alternatives, and rollback capability.",
    defaultMax: 25.0,
  },
  information_robustness: {
    title: "Information Robustness",
    shortTitle: "Information Robustness",
    description:
      "Assesses evidence strength, unmitigated gaps, epistemic readiness, and sensitivity to low-confidence assumptions.",
    defaultMax: 25.0,
  },
};

export function getPillarCanonicalKey(categoryOrPillar: string): ResiliencePillar {
  const norm = (categoryOrPillar || "").toLowerCase().trim();
  if (norm.includes("constraint")) return "constraint_boundary_tolerance";
  if (norm.includes("pessimistic") || norm.includes("survivab"))
    return "pessimistic_scenario_survivability";
  if (norm.includes("contingency") || norm.includes("fallback"))
    return "contingency_and_fallback_coverage";
  if (norm.includes("information") || norm.includes("robustness"))
    return "information_robustness";
  return "constraint_boundary_tolerance";
}

// -----------------------------------------------------------------------------
// 2. Normalization & Canonical Sorting
// -----------------------------------------------------------------------------

export function normalizeSubScores(
  rawSubScores: unknown
): NormalizedPillarScore[] {
  let items: ResilienceSubScore[] = [];

  if (Array.isArray(rawSubScores)) {
    items = rawSubScores.filter(Boolean);
  } else if (rawSubScores && typeof rawSubScores === "object") {
    // Defensively handle dictionary / mapping structures
    items = Object.entries(rawSubScores).map(([key, val]) => {
      if (typeof val === "object" && val !== null) {
        return {
          category: (val as { category?: string }).category || key,
          score: (val as { score?: number }).score ?? 0,
          max_score: (val as { max_score?: number }).max_score ?? 25.0,
          rationale: (val as { rationale?: string }).rationale || "",
          vulnerabilities_detected:
            (val as { vulnerabilities_detected?: string[] }).vulnerabilities_detected ||
            (val as { vulnerabilities?: string[] }).vulnerabilities ||
            [],
        };
      }
      return {
        category: key,
        score: typeof val === "number" ? val : 0,
        max_score: 25.0,
        rationale: "",
        vulnerabilities_detected: [],
      };
    });
  }

  // Map to normalized structures
  const normalizedMap: Record<string, NormalizedPillarScore> = {};

  for (const item of items) {
    const rawCat =
      item.category || (item as { pillar?: string }).pillar || (item as { name?: string }).name || "";
    const canonicalKey = getPillarCanonicalKey(rawCat);
    const def = PILLAR_DEFINITIONS[canonicalKey] || {
      title: rawCat || "Resilience Dimension",
      shortTitle: rawCat || "Dimension",
      description: "Evaluation pillar.",
      defaultMax: 25.0,
    };

    const score = Number.isFinite(item.score) ? Math.max(0, item.score) : 0;
    const maxScore =
      item.max_score && Number.isFinite(item.max_score) && item.max_score > 0
        ? item.max_score
        : def.defaultMax;
    const percentage = Math.min(100, Math.max(0, (score / maxScore) * 100));

    const rawVulns =
      item.vulnerabilities_detected || item.vulnerabilities || [];
    const vulnerabilities = Array.isArray(rawVulns)
      ? rawVulns.filter((v): v is string => typeof v === "string" && v.trim().length > 0)
      : [];

    normalizedMap[canonicalKey] = {
      category: item.category || canonicalKey,
      pillarKey: canonicalKey,
      title: def.title,
      shortTitle: def.shortTitle,
      description: def.description,
      score: Math.round(score * 100) / 100,
      maxScore,
      percentage: Math.round(percentage * 10) / 10,
      rationale: item.rationale || "No detailed rationale provided.",
      vulnerabilities,
    };
  }

  // Ensure all 4 canonical pillars are present in canonical order
  return CANONICAL_PILLAR_KEYS.map((key) => {
    if (normalizedMap[key]) {
      return normalizedMap[key];
    }
    const def = PILLAR_DEFINITIONS[key];
    return {
      category: key,
      pillarKey: key,
      title: def.title,
      shortTitle: def.shortTitle,
      description: def.description,
      score: 0,
      maxScore: def.defaultMax,
      percentage: 0,
      rationale: "Dimension evaluation pending or unavailable.",
      vulnerabilities: [],
    };
  });
}

// -----------------------------------------------------------------------------
// 3. Rating Band Metadata
// -----------------------------------------------------------------------------

export function getRatingMetadata(
  ratingOrScore: ResilienceRating | string | number
): RatingMetadata {
  let ratingStr: string;

  if (typeof ratingOrScore === "number") {
    if (ratingOrScore >= 80.0) ratingStr = "high";
    else if (ratingOrScore >= 60.0) ratingStr = "moderate";
    else if (ratingOrScore >= 40.0) ratingStr = "fragile";
    else ratingStr = "vulnerable";
  } else {
    ratingStr = (ratingOrScore || "").toLowerCase().trim();
  }

  switch (ratingStr) {
    case "high":
      return {
        rating: "high",
        label: "High Robustness",
        description:
          "High Robustness: Decision exhibits strong boundary tolerance, survivability, and contingency coverage across scenarios.",
        rangeText: "80–100",
        colorClass: {
          text: "text-emerald-400",
          bg: "bg-emerald-950/40",
          border: "border-emerald-800/60",
          gaugeStroke: "#10b981", // emerald-500
          badgeBg: "bg-emerald-950/60",
          badgeBorder: "border-emerald-700/80",
          badgeText: "text-emerald-300",
        },
      };
    case "moderate":
      return {
        rating: "moderate",
        label: "Moderate Robustness",
        description:
          "Moderate Robustness: Sound baseline strategy with acceptable margins, though specific scenario risks or gaps require monitoring.",
        rangeText: "60–<80",
        colorClass: {
          text: "text-cyan-400",
          bg: "bg-cyan-950/40",
          border: "border-cyan-800/60",
          gaugeStroke: "#06b6d4", // cyan-500
          badgeBg: "bg-cyan-950/60",
          badgeBorder: "border-cyan-700/80",
          badgeText: "text-cyan-300",
        },
      };
    case "fragile":
      return {
        rating: "fragile",
        label: "Fragile",
        description:
          "Fragile: Notable sensitivity to adverse conditions, narrow constraint margins, or insufficient fallback mitigation.",
        rangeText: "40–<60",
        colorClass: {
          text: "text-amber-400",
          bg: "bg-amber-950/40",
          border: "border-amber-800/60",
          gaugeStroke: "#f59e0b", // amber-500
          badgeBg: "bg-amber-950/60",
          badgeBorder: "border-amber-700/80",
          badgeText: "text-amber-300",
        },
      };
    case "vulnerable":
    default:
      return {
        rating: "vulnerable",
        label: "Vulnerable",
        description:
          "Vulnerable: Severe structural exposure to downside scenarios, missing decision gates, or unhedged hard constraints.",
        rangeText: "Below 40",
        colorClass: {
          text: "text-rose-400",
          bg: "bg-rose-950/40",
          border: "border-rose-800/60",
          gaugeStroke: "#f43f5e", // rose-500
          badgeBg: "bg-rose-950/60",
          badgeBorder: "border-rose-700/80",
          badgeText: "text-rose-300",
        },
      };
  }
}

// -----------------------------------------------------------------------------
// 4. Stress-Test Status Metadata
// -----------------------------------------------------------------------------

export function getStressTestMetadata(passed: boolean): StressTestMetadata {
  return {
    passed,
    statusLabel: passed
      ? "Heuristic stress threshold met"
      : "Heuristic stress threshold not met",
    badgeLabel: passed ? "Stress Test Met" : "Stress Threshold Not Met",
    description: passed
      ? "The recommended course of action meets AURA's configured multi-pillar heuristic stress-test thresholds."
      : "The decision strategy falls below the configured survivability or composite stress-test thresholds under adverse conditions.",
    thresholdsExplanation:
      "Result reflects AURA's configured scoring criteria (overall score >= 60.0 and pessimistic survivability >= 12.5 / 25.0), not a real-world guarantee.",
  };
}

// -----------------------------------------------------------------------------
// 5. Number and String Formatting
// -----------------------------------------------------------------------------

export function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "0";
  return Number.isInteger(score) ? score.toString() : score.toFixed(1);
}
