/**
 * AURA Presentation Layer Formatters & Integrity Helpers (Day 8G-C).
 *
 * Provides calibrated, deterministic formatting for:
 * - Currency, numbers, and percentage metrics
 * - Human-readable enum and snake_case transformations
 * - Clean word-boundary text truncation
 * - Decision readiness vs technical completion distinction
 * - Integrity evaluation (never displaying green badges on critical issues)
 */

import type {
  AnalysisResponse,
  DecisionReadiness,
  ProvenanceType,
} from "@/types";

/**
 * Format currency with proper symbols, commas, and handling for negative/zero values.
 */
export function formatCurrency(
  value: number | string | null | undefined,
  currency: string = "USD",
  compact: boolean = false
): string {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  const num = typeof value === "string" ? parseFloat(value.replace(/[^0-9.-]/g, "")) : value;
  if (isNaN(num)) {
    return String(value);
  }

  try {
    const formatter = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency.toUpperCase() === "USD" ? "USD" : currency.toUpperCase(),
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 1 : 0,
      minimumFractionDigits: 0,
    });
    return formatter.format(num);
  } catch {
    return `$${num.toLocaleString("en-US")}`;
  }
}

/**
 * Format general numbers with units (e.g. 50,000 writes/sec, 15ms).
 */
export function formatMetricNumber(
  value: number | string | null | undefined,
  unit?: string | null,
  decimals: number = 0
): string {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) {
    return unit ? `${value} ${unit}` : String(value);
  }

  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num);

  if (!unit) return formatted;
  if (unit === "%") return `${formatted}%`;
  return `${formatted} ${unit}`;
}

/**
 * Maps internal enum keys to human-readable executive terminology.
 */
const ENUM_LABEL_MAP: Record<string, string> = {
  architecture_technology: "Architecture & Technology",
  resource_allocation: "Resource Allocation",
  strategic_direction: "Strategic Direction",
  operational_policy: "Operational Policy",
  product_roadmap: "Product Roadmap",
  general_choice: "General Decision",
  partially_reversible: "Partially Reversible",
  irreversible: "Irreversible",
  reversible: "Fully Reversible",
  immediate: "Immediate (0–30 days)",
  short_term: "Near-Term (1–3 months)",
  medium_term: "Medium-Term (3–6 months)",
  long_term: "Long-Term (6+ months)",
  conditional_go: "Conditional Approval",
  proceed: "Proceed with Implementation",
  pilot: "Pilot Phased Rollout",
  defer: "Defer Commitment",
  reject: "Do Not Proceed",
  insufficient_evidence: "Insufficient Evidence",
  ready: "Ready for Execution",
  conditional: "Conditional Clearance",
  needs_validation: "Validation Required",
  blocked: "Execution Blocked",
  high: "High",
  moderate: "Moderate",
  low: "Low",
  fragile: "Fragile",
  vulnerable: "Vulnerable",
  hard_constraint: "Hard Constraint Ceiling",
  soft_constraint: "Operational Guideline",
  constraint_boundary_tolerance: "Constraint Boundary Tolerance",
  pessimistic_scenario_survivability: "Pessimistic Scenario Survivability",
  contingency_and_fallback_coverage: "Contingency & Fallback Coverage",
  information_robustness: "Information Robustness",
  user_provided: "User-Provided",
  inferred: "Analytically Inferred",
  unknown: "Unknown Origin",
  unsupported_no_causal_mapping: "No Causal Mapping",
  calculated: "Deterministic Calculation",
  base_case: "Base Case",
  optimistic: "Optimistic Trajectory",
  pessimistic: "Pessimistic Stress Trajectory",
};

/**
 * Format any snake_case or internal enum string into clean title prose.
 */
export function formatEnumLabel(raw: string | null | undefined): string {
  if (!raw) return "Not Specified";
  const normalized = raw.toLowerCase().trim();
  if (ENUM_LABEL_MAP[normalized]) {
    return ENUM_LABEL_MAP[normalized];
  }

  return normalized
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Format provenance type cleanly.
 */
export function formatProvenance(provenance: ProvenanceType | string | null | undefined): string {
  if (!provenance) return "Unspecified";
  return ENUM_LABEL_MAP[provenance.toLowerCase()] ?? formatEnumLabel(provenance);
}

/**
 * Truncate text on word boundaries cleanly, without cutting words mid-character.
 */
export function truncateOnWordBoundary(text: string | null | undefined, maxChars: number = 200): string {
  if (!text) return "";
  const trimmed = text.trim();
  if (trimmed.length <= maxChars) return trimmed;

  const sub = trimmed.slice(0, maxChars);
  const lastSpace = sub.lastIndexOf(" ");
  if (lastSpace > maxChars * 0.7) {
    return sub.slice(0, lastSpace) + "…";
  }
  return sub + "…";
}

/**
 * Extract first 1-2 sentences cleanly for executive overview.
 */
export function extractConciseRecommendation(fullText: string | null | undefined): string {
  if (!fullText) return "No recommendation statement provided.";
  const sentences = fullText.match(/[^.!?]+[.!?]+/g);
  if (sentences && sentences.length >= 1) {
    if (sentences.length === 1) return sentences[0].trim();
    return `${sentences[0].trim()} ${sentences[1].trim()}`;
  }
  return truncateOnWordBoundary(fullText, 220);
}

export interface DecisionIntegrityState {
  hasCriticalIssues: boolean;
  technicalCompletion: "complete" | "partial" | "failed";
  decisionReadiness: DecisionReadiness | "unknown";
  readinessLabel: string;
  badgeBorderClass: string;
  badgeBgClass: string;
  badgeTextClass: string;
  dotClass: string;
  issues: string[];
  unresolvedCalculations: string[];
}

/**
 * Evaluates decision integrity and guarantees that no green success indicator
 * is displayed when unresolved critical findings exist.
 */
export function evaluateDecisionIntegrity(result: AnalysisResponse): DecisionIntegrityState {
  const issues: string[] = [];
  const unresolvedCalculations: string[] = [];

  // Check technical status
  const isPartial = result.status === "partial_success";
  const technicalCompletion = isPartial ? "partial" : result.status === "completed" ? "complete" : "failed";

  if (isPartial) {
    issues.push("Analysis pipeline finished with partial success; some stages could not complete.");
  }
  if (result.recommendation_error) {
    issues.push(`Stage 4 Recommendation notice: ${result.recommendation_error}`);
  }
  if (result.scenario_error) {
    issues.push(`Stage 5 Scenarios notice: ${result.scenario_error}`);
  }
  if (result.resilience_error) {
    issues.push(`Stage 6 Resilience notice: ${result.resilience_error}`);
  }

  // Check Stage 6 resilience stress tests & critical vulnerabilities
  if (result.resilience) {
    if (result.resilience.stress_test_passed === false) {
      issues.push("Deterministic stress-test failed under severe constraint boundaries.");
    }
    if (result.resilience.critical_vulnerabilities && result.resilience.critical_vulnerabilities.length > 0) {
      issues.push(
        `${result.resilience.critical_vulnerabilities.length} critical vulnerabilities detected in stress test.`
      );
    }
  }

  // Check Stage 4 readiness and missing info
  const readiness = result.recommendation?.uncertainty_assessment?.decision_readiness || "unknown";
  const criticalMissing = result.recommendation?.uncertainty_assessment?.critical_missing_information || [];
  if (criticalMissing.length > 0) {
    issues.push(`${criticalMissing.length} critical information gaps pending verification.`);
  }

  // Check evidence contested requirements
  if (result.evidence_package?.requirements) {
    const contested = result.evidence_package.requirements.filter((r) => r.status === "contested");
    if (contested.length > 0) {
      issues.push(`${contested.length} empirical evidence requirements are actively contested.`);
    }
  }

  const hasCriticalIssues =
    isPartial ||
    Boolean(result.recommendation_error) ||
    Boolean(result.scenario_error) ||
    Boolean(result.resilience_error) ||
    (result.resilience?.stress_test_passed === false) ||
    ((result.resilience?.critical_vulnerabilities?.length || 0) > 0) ||
    criticalMissing.length > 0 ||
    readiness === "blocked";

  let readinessLabel = "Ready for Execution";
  let badgeBorderClass = "border-emerald-800/80";
  let badgeBgClass = "bg-emerald-950/40";
  let badgeTextClass = "text-emerald-300";
  let dotClass = "bg-emerald-400";

  if (hasCriticalIssues) {
    if (readiness === "blocked" || result.resilience?.stress_test_passed === false) {
      readinessLabel = "Execution Blocked / Severe Risks";
      badgeBorderClass = "border-rose-800/80";
      badgeBgClass = "bg-rose-950/40";
      badgeTextClass = "text-rose-300";
      dotClass = "bg-rose-400";
    } else {
      readinessLabel = "Conditional Clearance / Action Required";
      badgeBorderClass = "border-amber-800/80";
      badgeBgClass = "bg-amber-950/40";
      badgeTextClass = "text-amber-300";
      dotClass = "bg-amber-400";
    }
  } else if (readiness === "conditional") {
    readinessLabel = "Conditional Approval";
    badgeBorderClass = "border-amber-800/80";
    badgeBgClass = "bg-amber-950/40";
    badgeTextClass = "text-amber-300";
    dotClass = "bg-amber-400";
  } else if (readiness === "needs_validation") {
    readinessLabel = "Validation Required";
    badgeBorderClass = "border-sky-800/80";
    badgeBgClass = "bg-sky-950/40";
    badgeTextClass = "text-sky-300";
    dotClass = "bg-sky-400";
  }

  return {
    hasCriticalIssues,
    technicalCompletion,
    decisionReadiness: readiness,
    readinessLabel,
    badgeBorderClass,
    badgeBgClass,
    badgeTextClass,
    dotClass,
    issues,
    unresolvedCalculations,
  };
}
