export type DecisionStatus =
  | "draft"
  | "submitted"
  | "analyzing"
  | "completed"
  | "failed";

export interface DecisionInput {
  title: string;
  context: string;
  targetOutcome?: string;
  constraints?: string[];
}

export interface DecisionDecompositionSummary {
  variablesCount: number;
  constraintsCount: number;
  stakeholdersCount: number;
}

export interface AnalysisSession {
  id: string;
  input: DecisionInput;
  status: DecisionStatus;
  createdAt: string;
  updatedAt: string;
  decomposition?: DecisionDecompositionSummary;
}
