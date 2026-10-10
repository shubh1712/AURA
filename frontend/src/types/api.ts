/**
 * API Contracts matching the AURA FastAPI backend.
 */

import type { DecisionModel } from "./decision";
import type { EvidencePackage } from "./evidence";
import type { ReasoningBoard } from "./reasoning";
import type { DecisionRecommendation } from "./recommendation";

export interface AnalysisRequest {
  question: string;
  context?: Record<string, unknown> | null;
  constraints?: string[];
}

export interface AnalysisResponse {
  analysis_id: string;
  status: string;
  question: string;
  message: string;
  decision_model?: DecisionModel | null;
  evidence_package?: EvidencePackage | null;
  reasoning_board?: ReasoningBoard | null;
  recommendation?: DecisionRecommendation | null;
  recommendation_status?: string | null;
  recommendation_error?: string | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
}

// Backward-compatible alias
export type HealthCheckResponse = HealthResponse;

export interface ApiResponse<T = unknown> {
  data?: T;
  error?: string;
  success: boolean;
  timestamp: string;
}

export interface ApiErrorDetails {
  message: string;
  statusCode?: number;
  details?: unknown;
}
