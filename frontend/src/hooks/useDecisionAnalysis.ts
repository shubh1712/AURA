"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  DecisionFormData,
  DecisionStatus,
  AnalysisResponse,
  JobStatus,
  PipelineStage,
} from "@/types";
import {
  createAnalysisJob,
  getAnalysisJobStatus,
  getAnalysisJobResult,
  ApiClientError,
} from "@/lib/api";

export interface UseDecisionAnalysisReturn {
  formData: DecisionFormData;
  status: DecisionStatus;
  isLoading: boolean;
  jobId: string | null;
  jobStatus: JobStatus | null;
  pipelineStage: PipelineStage | null;
  progressMessage: string | null;
  validationError: string | null;
  apiError: string | null;
  apiErrorStatusCode: number | null;
  apiResponse: AnalysisResponse | null;
  updateField: (field: keyof DecisionFormData, value: string) => void;
  reset: () => void;
  clearError: () => void;
  submitAnalysis: () => Promise<boolean>;
}

const INITIAL_FORM_DATA: DecisionFormData = {
  question: "",
  context: "",
  constraints: "",
};

const POLLING_INTERVAL_MS = 1500;
const MAX_CONSECUTIVE_POLL_FAILURES = 5;

/**
 * Reusable React hook for managing decision intake, validation,
 * asynchronous job submission, stage-aware polling, and result retrieval.
 */
export function useDecisionAnalysis(): UseDecisionAnalysisReturn {
  const [formData, setFormData] = useState<DecisionFormData>(INITIAL_FORM_DATA);
  const [status, setStatus] = useState<DecisionStatus>("idle");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [pipelineStage, setPipelineStage] = useState<PipelineStage | null>(null);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [apiErrorStatusCode, setApiErrorStatusCode] = useState<number | null>(null);
  const [apiResponse, setApiResponse] = useState<AnalysisResponse | null>(null);

  const isSubmittingRef = useRef<boolean>(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const consecutiveFailuresRef = useRef<number>(0);
  const pollJobStatusRef = useRef<((targetJobId: string) => Promise<void>) | null>(null);

  const clearPollingTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // Cleanup polling timer on component unmount
  useEffect(() => {
    return () => {
      activeJobIdRef.current = null;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  const updateField = useCallback(
    (field: keyof DecisionFormData, value: string) => {
      setFormData((prev) => ({
        ...prev,
        [field]: value,
      }));
      if (validationError) setValidationError(null);
      if (apiError) {
        setApiError(null);
        setApiErrorStatusCode(null);
      }
    },
    [validationError, apiError]
  );

  const clearError = useCallback(() => {
    setValidationError(null);
    setApiError(null);
    setApiErrorStatusCode(null);
  }, []);

  const reset = useCallback(() => {
    activeJobIdRef.current = null;
    isSubmittingRef.current = false;
    clearPollingTimer();
    setFormData(INITIAL_FORM_DATA);
    setStatus("idle");
    setIsLoading(false);
    setJobId(null);
    setJobStatus(null);
    setPipelineStage(null);
    setProgressMessage(null);
    setValidationError(null);
    setApiError(null);
    setApiErrorStatusCode(null);
    setApiResponse(null);
  }, [clearPollingTimer]);

  /**
   * Recursive poll runner that queries status every POLLING_INTERVAL_MS
   * until termination state is reached.
   */
  const pollJobStatus = useCallback(
    async (targetJobId: string) => {
      if (activeJobIdRef.current !== targetJobId) {
        return;
      }

      try {
        const jobStatusResp = await getAnalysisJobStatus(targetJobId);

        // Discard response if user reset or started a new job
        if (activeJobIdRef.current !== targetJobId) {
          return;
        }

        consecutiveFailuresRef.current = 0;
        setJobStatus(jobStatusResp.status);
        setPipelineStage(jobStatusResp.stage);
        if (jobStatusResp.progress_message) {
          setProgressMessage(jobStatusResp.progress_message);
        }

        if (jobStatusResp.status === "succeeded") {
          // Terminal Success: Retrieve full validated AnalysisResponse
          try {
            const finalResult = await getAnalysisJobResult(targetJobId);
            if (activeJobIdRef.current === targetJobId) {
              setApiResponse(finalResult);
              setStatus("completed");
              setIsLoading(false);
              isSubmittingRef.current = false;
            }
          } catch (resErr) {
            if (activeJobIdRef.current === targetJobId) {
              const errMsg =
                resErr instanceof ApiClientError
                  ? resErr.message
                  : "Failed to retrieve completed analysis result.";
              const errCode =
                resErr instanceof ApiClientError ? resErr.statusCode ?? 500 : 500;
              setApiError(errMsg);
              setApiErrorStatusCode(errCode);
              setStatus("error");
              setIsLoading(false);
              isSubmittingRef.current = false;
            }
          }
          return;
        }

        if (jobStatusResp.status === "timed_out") {
          // Terminal Timeout (HTTP 504)
          setApiError(
            jobStatusResp.error ||
              "The decision analysis exceeded its allowed processing time."
          );
          setApiErrorStatusCode(504);
          setStatus("error");
          setIsLoading(false);
          isSubmittingRef.current = false;
          return;
        }

        if (jobStatusResp.status === "failed") {
          // Terminal Failure
          setApiError(
            jobStatusResp.error ||
              "An error occurred while evaluating the decision inquiry."
          );
          setApiErrorStatusCode(jobStatusResp.error_status_code || 500);
          setStatus("error");
          setIsLoading(false);
          isSubmittingRef.current = false;
          return;
        }

        // Job is still queued or running -> schedule next poll cycle
        if (activeJobIdRef.current === targetJobId) {
          pollTimerRef.current = setTimeout(() => {
            pollJobStatusRef.current?.(targetJobId);
          }, POLLING_INTERVAL_MS);
        }
      } catch (pollErr) {
        if (activeJobIdRef.current !== targetJobId) {
          return;
        }

        consecutiveFailuresRef.current += 1;
        if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_POLL_FAILURES) {
          const errMsg =
            pollErr instanceof ApiClientError
              ? pollErr.message
              : "Lost communication with the analysis service.";
          const errCode =
            pollErr instanceof ApiClientError ? pollErr.statusCode ?? null : null;
          setApiError(errMsg);
          setApiErrorStatusCode(errCode);
          setStatus("error");
          setIsLoading(false);
          isSubmittingRef.current = false;
          return;
        }

        // Retry polling after standard interval on transient poll network glitch
        pollTimerRef.current = setTimeout(() => {
          pollJobStatusRef.current?.(targetJobId);
        }, POLLING_INTERVAL_MS);
      }
    },
    []
  );

  useEffect(() => {
    pollJobStatusRef.current = pollJobStatus;
  }, [pollJobStatus]);

  const submitAnalysis = useCallback(async (): Promise<boolean> => {
    // Prevent double submission
    if (isSubmittingRef.current || isLoading) {
      return false;
    }

    const trimmedQuestion = formData.question.trim();

    if (!trimmedQuestion) {
      setValidationError("Please enter the decision question you are facing.");
      return false;
    }

    if (trimmedQuestion.length < 5) {
      setValidationError(
        "Please enter a more descriptive question (at least 5 characters)."
      );
      return false;
    }

    isSubmittingRef.current = true;
    clearPollingTimer();
    setValidationError(null);
    setApiError(null);
    setApiErrorStatusCode(null);
    setApiResponse(null);
    setIsLoading(true);
    setStatus("submitting");
    setJobStatus("queued");
    setPipelineStage("queued");
    setProgressMessage("Submitting decision inquiry to AURA engine...");
    consecutiveFailuresRef.current = 0;

    const rawConstraints = formData.constraints.trim();
    const constraintsList = rawConstraints
      ? rawConstraints
          .split(/\r?\n|,/)
          .map((c) => c.trim())
          .filter((c) => c.length > 0)
      : [];

    const trimmedContext = formData.context.trim();
    const contextPayload = trimmedContext ? { notes: trimmedContext } : undefined;

    try {
      // Step 1: Submit job to async API POST /api/analysis/jobs
      const jobResponse = await createAnalysisJob({
        question: trimmedQuestion,
        context: contextPayload,
        constraints: constraintsList,
      });

      const newJobId = jobResponse.job_id;
      activeJobIdRef.current = newJobId;
      setJobId(newJobId);
      setJobStatus(jobResponse.status);
      setPipelineStage(jobResponse.stage);
      if (jobResponse.progress_message) {
        setProgressMessage(jobResponse.progress_message);
      }

      // Step 2: Begin bounded polling cycle
      pollTimerRef.current = setTimeout(() => {
        pollJobStatusRef.current?.(newJobId);
      }, POLLING_INTERVAL_MS);

      return true;
    } catch (error) {
      const errorMessage =
        error instanceof ApiClientError
          ? error.message
          : "An unexpected error occurred while communicating with the AURA backend.";
      const statusCode =
        error instanceof ApiClientError && typeof error.statusCode === "number"
          ? error.statusCode
          : null;
      setApiError(errorMessage);
      setApiErrorStatusCode(statusCode);
      setStatus("error");
      setIsLoading(false);
      isSubmittingRef.current = false;
      activeJobIdRef.current = null;
      return false;
    }
  }, [formData, isLoading, clearPollingTimer]);

  return {
    formData,
    status,
    isLoading,
    jobId,
    jobStatus,
    pipelineStage,
    progressMessage,
    validationError,
    apiError,
    apiErrorStatusCode,
    apiResponse,
    updateField,
    reset,
    clearError,
    submitAnalysis,
  };
}
