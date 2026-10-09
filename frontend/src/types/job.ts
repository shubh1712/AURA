/**
 * Asynchronous Analysis Job Types matching backend app.schemas.job.
 */

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "timed_out";

export type PipelineStage =
  | "queued"
  | "stage1_decision_framer"
  | "stage2_evidence_engine"
  | "stage3_ai_boardroom"
  | "completed"
  | "failed"
  | "timed_out";

export interface AnalysisJobCreateRequest {
  question: string;
  context?: Record<string, unknown> | null;
  constraints?: string[];
  owner_id?: string | null;
  timeout_seconds?: number | null;
  framer_operation_timeout_seconds?: number | null;
}

export interface AnalysisJobStatusResponse {
  job_id: string;
  status: JobStatus;
  stage: PipelineStage;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  progress_message: string;
  error?: string | null;
  error_status_code?: number | null;
  owner_id?: string | null;
}
