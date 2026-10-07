/**
 * Canonical TypeScript types corresponding to the AURA Evidence & Source Provenance Engine.
 * Authoritative schema mirrors backend/app/schemas/evidence.py.
 */

// ------------------------------------------------------------------------------
// String Union Enums
// ------------------------------------------------------------------------------

export type SourceType =
  | "academic"
  | "industry_report"
  | "government"
  | "regulatory_filing"
  | "company_primary"
  | "financial_market"
  | "news_media"
  | "internal_data"
  | "other";

export type EvidenceKind =
  | "external_research"
  | "internal_data"
  | "user_clarification"
  | "deterministic_calculation";

export type DecisionEntityType =
  | "objective"
  | "variable"
  | "constraint"
  | "stakeholder"
  | "tradeoff"
  | "assumption"
  | "unknown"
  | "key_question"
  | "decision";

export type EvidenceStance =
  | "supports"
  | "challenges"
  | "context"
  | "inconclusive";

export type EvidenceGapType =
  | "unsupported_claim"
  | "unresolved_unknown"
  | "conflicting_evidence"
  | "insufficient_evidence";

export type RequirementStatus =
  | "pending"
  | "fulfilled"
  | "unsupported"
  | "contested"
  | "inconclusive";

export type CriticalityLevel = "low" | "medium" | "high";

export type ConfidenceLevel = "low" | "medium" | "high" | "untested";

// ------------------------------------------------------------------------------
// Core Domain Models
// ------------------------------------------------------------------------------

export interface NumericEvidence {
  metric_name: string;
  value?: number | null;
  unit?: string | null;
  range_min?: number | null;
  range_max?: number | null;
  confidence_interval?: string | null;
  sample_size?: number | null;
  context?: string | null;
}

export interface Source {
  id: string;
  url?: string | null;
  title: string;
  publisher?: string | null;
  source_type: SourceType;
  publication_date?: string | null;
  retrieval_timestamp: string;
  reliability_score?: number | null;
}

export interface EvidenceItem {
  id: string;
  source_id: string;
  content: string;
  summary?: string | null;
  numeric_data: NumericEvidence[];
  extraction_confidence: ConfidenceLevel;
  retrieval_timestamp: string;
}

export interface ClaimEvidenceLink {
  id: string;
  evidence_item_id: string;
  target_entity_id: string;
  target_entity_type: DecisionEntityType;
  stance: EvidenceStance;
  reasoning: string;
  relationship_confidence: ConfidenceLevel;
  requirement_id?: string | null;
}

export interface EvidenceRequirement {
  id: string;
  target_entity_id: string;
  target_entity_type: DecisionEntityType;
  kind: EvidenceKind;
  description: string;
  priority: CriticalityLevel;
  status: RequirementStatus;
  suggested_queries: string[];
}

export interface EvidenceGap {
  id: string;
  gap_type: EvidenceGapType;
  target_entity_id: string;
  target_entity_type: DecisionEntityType;
  requirement_id?: string | null;
  description: string;
  impact: CriticalityLevel;
  conflicting_evidence_ids: string[];
  resolution_guidance?: string | null;
}

export interface EvidencePackage {
  id: string;
  decision_model_id: string;
  requirements: EvidenceRequirement[];
  sources: Source[];
  items: EvidenceItem[];
  claim_links: ClaimEvidenceLink[];
  gaps: EvidenceGap[];
  summary: string;
  created_at: string;
}
