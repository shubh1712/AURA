/**
 * Canonical AI Boardroom Reasoning Types matching backend app.schemas.reasoning.
 */

export type PerspectiveType = "growth" | "finance" | "customer" | "risk";

export type ReasoningBasis =
  | "evidence"
  | "inference"
  | "assumption"
  | "unresolved"
  | "mixed";

export type ArgumentDirection =
  | "favorable"
  | "unfavorable"
  | "neutral"
  | "mixed";

export type DisagreementNature =
  | "evidence_dependent"
  | "assumption_dependent"
  | "interpretation"
  | "unresolved";

export interface ReasoningArgument {
  id: string;
  claim: string;
  direction: ArgumentDirection;
  basis: ReasoningBasis;
  reasoning: string;
  evidence_item_ids: string[];
  requirement_ids: string[];
  assumption_ids: string[];
  unknown_ids: string[];
  evidence_gap_ids: string[];
  related_entity_ids: string[];
  caveat?: string | null;
}

export interface ReasoningPerspective {
  id: string;
  perspective_type: PerspectiveType;
  summary: string;
  arguments: ReasoningArgument[];
  critical_assumption_ids: string[];
  evidence_gap_ids: string[];
  unresolved_questions: string[];
  limitations: string[];
  opportunities: string[];
  concerns: string[];
}

export interface ReasoningDisagreement {
  id: string;
  topic: string;
  perspective_ids: string[];
  argument_ids: string[];
  positions: Record<string, string>;
  evidence_item_ids: string[];
  assumption_ids: string[];
  evidence_gap_ids: string[];
  nature: DisagreementNature;
}

export interface BoardSynthesis {
  summary: string;
  areas_of_agreement: string[];
  disagreement_ids: string[];
  critical_assumption_ids: string[];
  critical_evidence_gap_ids: string[];
  evidence_sensitive_points: string[];
  unresolved_questions: string[];
}

export interface ReasoningBoard {
  id: string;
  decision_model_id: string;
  evidence_package_id: string;
  perspectives: ReasoningPerspective[];
  disagreements: ReasoningDisagreement[];
  synthesis: BoardSynthesis;
  created_at?: string;
}
