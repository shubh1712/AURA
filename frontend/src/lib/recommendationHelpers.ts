import type {
  RecommendationDecisionStatus,
  EvidenceStrength,
  DecisionReadiness,
  RecommendationStability,
  ActionPriority,
  ActionTimeHorizon,
  EvidencePackage,
  DecisionModel,
  ReasoningBoard,
} from "@/types";

export interface StatusConfig {
  status: RecommendationDecisionStatus;
  label: string;
  badgeClass: string;
  dotClass: string;
  borderClass: string;
  bgClass: string;
  textClass: string;
  tagline: string;
  isApproval: boolean;
  isInsufficientEvidence: boolean;
}

export const DECISION_STATUS_CONFIGS: Record<RecommendationDecisionStatus, StatusConfig> = {
  proceed: {
    status: "proceed",
    label: "Proceed",
    badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/80",
    dotClass: "bg-emerald-400",
    borderClass: "border-emerald-700/60",
    bgClass: "bg-emerald-950/20",
    textClass: "text-emerald-300",
    tagline: "Execution baseline validated. Proceed with recommended implementation.",
    isApproval: true,
    isInsufficientEvidence: false,
  },
  conditional: {
    status: "conditional",
    label: "Conditional Approval",
    badgeClass: "bg-amber-950/60 text-amber-300 border-amber-800/80",
    dotClass: "bg-amber-400",
    borderClass: "border-amber-700/60",
    bgClass: "bg-amber-950/20",
    textClass: "text-amber-300",
    tagline: "Action plan approved subject to strict prerequisite decision gates.",
    isApproval: true,
    isInsufficientEvidence: false,
  },
  pilot: {
    status: "pilot",
    label: "Pilot / Phased Rollout",
    badgeClass: "bg-sky-950/60 text-sky-300 border-sky-800/80",
    dotClass: "bg-sky-400",
    borderClass: "border-sky-700/60",
    bgClass: "bg-sky-950/20",
    textClass: "text-sky-300",
    tagline: "Execute bounded, low-risk pilot to validate empirical hypotheses before broad commitment.",
    isApproval: true,
    isInsufficientEvidence: false,
  },
  defer: {
    status: "defer",
    label: "Defer Decision",
    badgeClass: "bg-purple-950/60 text-purple-300 border-purple-800/80",
    dotClass: "bg-purple-400",
    borderClass: "border-purple-700/60",
    bgClass: "bg-purple-950/20",
    textClass: "text-purple-300",
    tagline: "Postpone commitment until strategic dependencies or temporal conditions align.",
    isApproval: false,
    isInsufficientEvidence: false,
  },
  reject: {
    status: "reject",
    label: "Do Not Proceed",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/80",
    dotClass: "bg-rose-400",
    borderClass: "border-rose-700/60",
    bgClass: "bg-rose-950/20",
    textClass: "text-rose-300",
    tagline: "Proposed direction violates key constraints or carries unacceptable downside risk.",
    isApproval: false,
    isInsufficientEvidence: false,
  },
  insufficient_evidence: {
    status: "insufficient_evidence",
    label: "Insufficient Evidence",
    badgeClass: "bg-orange-950/60 text-orange-300 border-orange-800/80",
    dotClass: "bg-orange-400",
    borderClass: "border-orange-700/60",
    bgClass: "bg-orange-950/20",
    textClass: "text-orange-300",
    tagline: "The available evidence does not justify a confident decision. Further investigation required.",
    isApproval: false,
    isInsufficientEvidence: true,
  },
};

export function getStatusConfig(status: RecommendationDecisionStatus): StatusConfig {
  return (
    DECISION_STATUS_CONFIGS[status] ?? {
      status,
      label: String(status).replace(/_/g, " ").toUpperCase(),
      badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
      dotClass: "bg-zinc-400",
      borderClass: "border-zinc-800",
      bgClass: "bg-zinc-900/40",
      textClass: "text-zinc-300",
      tagline: "Status determined by analysis pipeline.",
      isApproval: false,
      isInsufficientEvidence: false,
    }
  );
}

// ------------------------------------------------------------------------------
// Uncertainty Assessment Configurations
// ------------------------------------------------------------------------------

export interface CategoryAssessmentConfig {
  value: string;
  label: string;
  badgeClass: string;
  description: string;
}

export const EVIDENCE_STRENGTH_CONFIGS: Record<EvidenceStrength, CategoryAssessmentConfig> = {
  strong: {
    value: "strong",
    label: "Strong Evidence",
    badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/80",
    description: "Multiple corroborating empirical sources with high methodology rigour and verified claims.",
  },
  moderate: {
    value: "moderate",
    label: "Moderate Evidence",
    badgeClass: "bg-sky-950/60 text-sky-300 border-sky-800/80",
    description: "Credible sources supporting core claims, with minor unverified secondary nuances.",
  },
  limited: {
    value: "limited",
    label: "Limited Evidence",
    badgeClass: "bg-amber-950/60 text-amber-300 border-amber-800/80",
    description: "Sparse empirical findings or reliance on preliminary and indirect indicators.",
  },
  contested: {
    value: "contested",
    label: "Contested Evidence",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/80",
    description: "Direct contradictions or conflicting metrics between verified sources requiring resolution.",
  },
  insufficient: {
    value: "insufficient",
    label: "Insufficient Evidence",
    badgeClass: "bg-orange-950/60 text-orange-300 border-orange-800/80",
    description: "Critical evidentiary requirements remain unfulfilled; empirical basis cannot support decision.",
  },
};

export const DECISION_READINESS_CONFIGS: Record<DecisionReadiness, CategoryAssessmentConfig> = {
  ready: {
    value: "ready",
    label: "Execution Ready",
    badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/80",
    description: "Prerequisites defined, risk mitigations assigned, and operational runway is clear.",
  },
  conditional: {
    value: "conditional",
    label: "Conditional Readiness",
    badgeClass: "bg-amber-950/60 text-amber-300 border-amber-800/80",
    description: "Execution should proceed only after specific milestone decision gates are verified.",
  },
  needs_validation: {
    value: "needs_validation",
    label: "Needs Validation",
    badgeClass: "bg-sky-950/60 text-sky-300 border-sky-800/80",
    description: "Requires bounded testing or telemetry verification before committing substantial resources.",
  },
  blocked: {
    value: "blocked",
    label: "Execution Blocked",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/80",
    description: "Hard constraint violations or unmitigated catastrophic risks prevent moving forward.",
  },
};

export const RECOMMENDATION_STABILITY_CONFIGS: Record<RecommendationStability, CategoryAssessmentConfig> = {
  high: {
    value: "high",
    label: "High Stability",
    badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/80",
    description: "Robust recommendation that holds true across wide parameter and market fluctuations.",
  },
  moderate: {
    value: "moderate",
    label: "Moderate Stability",
    badgeClass: "bg-amber-950/60 text-amber-300 border-amber-800/80",
    description: "Sensitive to key underlying assumptions; sensitive variables must be monitored.",
  },
  volatile: {
    value: "volatile",
    label: "Volatile / Fragile",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/80",
    description: "Small shifts in unverified assumptions or data inputs could reverse this recommendation.",
  },
};

// ------------------------------------------------------------------------------
// Action Roadmap Configurations
// ------------------------------------------------------------------------------

export const PRIORITY_CONFIGS: Record<ActionPriority, { label: string; badgeClass: string; dotClass: string }> = {
  critical: {
    label: "Critical Priority",
    badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/80",
    dotClass: "bg-rose-400",
  },
  high: {
    label: "High Priority",
    badgeClass: "bg-amber-950/60 text-amber-300 border-amber-800/80",
    dotClass: "bg-amber-400",
  },
  medium: {
    label: "Medium Priority",
    badgeClass: "bg-sky-950/60 text-sky-300 border-sky-800/80",
    dotClass: "bg-sky-400",
  },
  low: {
    label: "Low Priority",
    badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
    dotClass: "bg-zinc-400",
  },
};

export const TIME_HORIZON_CONFIGS: Record<
  ActionTimeHorizon,
  { label: string; timeWindow: string; badgeClass: string }
> = {
  immediate: {
    label: "Immediate",
    timeWindow: "Day 1 - 30",
    badgeClass: "bg-emerald-950/50 text-emerald-300 border-emerald-800/60",
  },
  near_term: {
    label: "Near-Term",
    timeWindow: "Month 1 - 3",
    badgeClass: "bg-sky-950/50 text-sky-300 border-sky-800/60",
  },
  medium_term: {
    label: "Medium-Term",
    timeWindow: "Month 3 - 12",
    badgeClass: "bg-purple-950/50 text-purple-300 border-purple-800/60",
  },
  long_term: {
    label: "Long-Term",
    timeWindow: "Year 1+",
    badgeClass: "bg-zinc-800/60 text-zinc-300 border-zinc-700",
  },
};

// ------------------------------------------------------------------------------
// Deterministic Reference Resolvers
// ------------------------------------------------------------------------------

export interface ResolvedEvidenceItem {
  id: string;
  found: boolean;
  content: string;
  summary?: string | null;
  confidence?: string;
  sourceTitle?: string;
}

export function resolveEvidenceItem(
  id: string,
  pkg?: EvidencePackage | null
): ResolvedEvidenceItem {
  if (!pkg || !pkg.items) {
    return { id, found: false, content: `Evidence item ${id}` };
  }
  const item = pkg.items.find((i) => i.id === id);
  if (!item) {
    return { id, found: false, content: `Evidence item ${id}` };
  }
  const source = pkg.sources?.find((s) => s.id === item.source_id);
  return {
    id: item.id,
    found: true,
    content: item.content,
    summary: item.summary,
    confidence: item.extraction_confidence,
    sourceTitle: source?.title,
  };
}

export interface ResolvedAssumption {
  id: string;
  found: boolean;
  statement: string;
  confidence?: string;
  falsificationCondition?: string | null;
}

export function resolveAssumption(
  id: string,
  model?: DecisionModel | null
): ResolvedAssumption {
  if (!model || !model.assumptions) {
    return { id, found: false, statement: `Assumption ${id}` };
  }
  const assumption = model.assumptions.find((a) => a.id === id);
  if (!assumption) {
    return { id, found: false, statement: `Assumption ${id}` };
  }
  return {
    id: assumption.id,
    found: true,
    statement: assumption.statement,
    confidence: assumption.confidence,
    falsificationCondition: assumption.falsification_condition,
  };
}

export interface ResolvedEvidenceGap {
  id: string;
  found: boolean;
  description: string;
  gapType?: string;
  impact?: string;
  resolutionGuidance?: string | null;
}

export function resolveEvidenceGap(
  id: string,
  pkg?: EvidencePackage | null
): ResolvedEvidenceGap {
  if (!pkg || !pkg.gaps) {
    return { id, found: false, description: `Evidence gap ${id}` };
  }
  const gap = pkg.gaps.find((g) => g.id === id);
  if (!gap) {
    return { id, found: false, description: `Evidence gap ${id}` };
  }
  return {
    id: gap.id,
    found: true,
    description: gap.description,
    gapType: gap.gap_type,
    impact: gap.impact,
    resolutionGuidance: gap.resolution_guidance,
  };
}

export interface ResolvedDisagreement {
  id: string;
  found: boolean;
  topic: string;
  nature?: string;
  positions?: Record<string, string>;
}

export function resolveDisagreement(
  id: string,
  board?: ReasoningBoard | null
): ResolvedDisagreement {
  if (!board || !board.disagreements) {
    return { id, found: false, topic: `Dialectical disagreement ${id}` };
  }
  const disagreement = board.disagreements.find((d) => d.id === id);
  if (!disagreement) {
    return { id, found: false, topic: `Dialectical disagreement ${id}` };
  }
  return {
    id: disagreement.id,
    found: true,
    topic: disagreement.topic,
    nature: disagreement.nature,
    positions: disagreement.positions,
  };
}
