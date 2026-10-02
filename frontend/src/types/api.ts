/**
 * API Contracts matching the AURA FastAPI backend.
 */

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
  decision_model?: Record<string, unknown> | null;
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
