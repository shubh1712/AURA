export type DecisionStatus =
  | "idle"
  | "draft"
  | "submitting"
  | "completed"
  | "failed"
  | "error";

export interface DecisionFormData {
  question: string;
  context: string;
  constraints: string;
}

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
  formData: DecisionFormData;
  status: DecisionStatus;
  createdAt: string;
  updatedAt: string;
}
