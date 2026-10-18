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
import {
  saveActiveSession,
  loadActiveSession,
  clearActiveSession,
} from "@/lib/session";

export interface UseDecisionAnalysisReturn {
  formData: DecisionFormData;
  status: DecisionStatus;
  isLoading: boolean;
  isRestoring: boolean;
  restorationError: string | null;
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
  stopAnalysis: () => void;
  retryRestoration: () => Promise<void>;
}

const INITIAL_FORM_DATA: DecisionFormData = {
  question: "",
  context: "",
  constraints: "",
};

const POLLING_INTERVAL_MS = 5000;
const MAX_POLL_BACKOFF_MS = 60000;

/**
 * Reusable React hook for managing decision intake, validation,
 * asynchronous job submission, stage-aware polling, session restoration across refreshes,
 * and complete result retrieval.
 */
export function useDecisionAnalysis(ownerId?: string | null): UseDecisionAnalysisReturn {
  const [formData, setFormData] = useState<DecisionFormData>(INITIAL_FORM_DATA);
  const [status, setStatus] = useState<DecisionStatus>("idle");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isRestoring, setIsRestoring] = useState<boolean>(true);
  const [restorationError, setRestorationError] = useState<string | null>(null);
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
  const pollJobStatusRef = useRef<((targetJobId: string, expectedRunId: number) => Promise<void>) | null>(null);
  const runIdRef = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const clearPollingTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // Cleanup polling timer and abort controller on unmount
  useEffect(() => {
    return () => {
      runIdRef.current += 1;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
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

  const stopAnalysis = useCallback(() => {
    // 1. Advance run counter to invalidate pending asynchronous responses or poll cycles
    runIdRef.current += 1;

    // 2. Abort active in-flight fetch request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // 3. Stop timer and clear active stored session so refreshes do not reconnect to cancelled job
    clearPollingTimer();
    clearActiveSession();

    // 4. Detach job tracking
    activeJobIdRef.current = null;
    isSubmittingRef.current = false;

    // 5. Restore user to original editable decision form while preserving formData & any previous results
    setIsLoading(false);
    setStatus("idle");
    setJobId(null);
    setJobStatus(null);
    setPipelineStage(null);
    setProgressMessage(null);
    setValidationError(null);
    setApiError(null);
    setApiErrorStatusCode(null);
  }, [clearPollingTimer]);

  const reset = useCallback(() => {
    runIdRef.current += 1;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    clearActiveSession();
    activeJobIdRef.current = null;
    isSubmittingRef.current = false;
    clearPollingTimer();
    setFormData(INITIAL_FORM_DATA);
    setStatus("idle");
    setIsLoading(false);
    setIsRestoring(false);
    setRestorationError(null);
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
    async (targetJobId: string, expectedRunId: number) => {
      if (activeJobIdRef.current !== targetJobId || runIdRef.current !== expectedRunId) {
        return;
      }

      try {
        const jobStatusResp = await getAnalysisJobStatus(
          targetJobId,
          ownerId,
          abortControllerRef.current?.signal
        );

        // Discard response if user stopped, reset, or started a new job
        if (activeJobIdRef.current !== targetJobId || runIdRef.current !== expectedRunId) {
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
            const finalResult = await getAnalysisJobResult(
              targetJobId,
              ownerId,
              abortControllerRef.current?.signal
            );
            if (activeJobIdRef.current === targetJobId && runIdRef.current === expectedRunId) {
              setApiResponse(finalResult);
              setStatus("completed");
              setIsLoading(false);
              isSubmittingRef.current = false;

              // Persist canonical session reference
              saveActiveSession({
                jobId: targetJobId,
                analysisId: finalResult.analysis_id,
                ownerId: ownerId ?? undefined,
              });
            }
          } catch (resErr) {
            if (activeJobIdRef.current !== targetJobId) {
              return;
            }

            const statusCode =
              resErr instanceof ApiClientError ? resErr.statusCode : undefined;
            const isTransient =
              statusCode === undefined ||
              statusCode === 408 ||
              statusCode === 429 ||
              (statusCode >= 500 && statusCode <= 599);

            if (isTransient) {
              consecutiveFailuresRef.current += 1;
              const backoffMs = Math.min(
                POLLING_INTERVAL_MS * 2 ** Math.min(consecutiveFailuresRef.current, 10),
                MAX_POLL_BACKOFF_MS
              );

              setProgressMessage(
                "Analysis completed. Waiting to retrieve results..."
              );

              pollTimerRef.current = setTimeout(() => {
                pollJobStatusRef.current?.(targetJobId, expectedRunId);
              }, backoffMs);
              return;
            }

            setApiError(
              resErr instanceof ApiClientError
                ? resErr.message
                : "Failed to retrieve completed analysis result."
            );
            setApiErrorStatusCode(statusCode ?? null);
            setStatus("error");
            setIsLoading(false);
            isSubmittingRef.current = false;
          }
          return;
        }

        if (jobStatusResp.status === "timed_out") {
          // Terminal Timeout (HTTP 504)
          setJobStatus("timed_out");
          setApiError(
            "Gemini may be experiencing high traffic or taking longer than expected to respond. Your analysis couldn't be completed in time. Please try again shortly."
          );
          setApiErrorStatusCode(504);
          setStatus("error");
          setIsLoading(false);
          isSubmittingRef.current = false;
          return;
        }

        if (jobStatusResp.status === "failed") {
          // Terminal Failure
          setJobStatus("failed");
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
        if (activeJobIdRef.current === targetJobId && runIdRef.current === expectedRunId) {
          pollTimerRef.current = setTimeout(() => {
            pollJobStatusRef.current?.(targetJobId, expectedRunId);
          }, POLLING_INTERVAL_MS);
        }
      } catch (pollErr) {
        if (activeJobIdRef.current !== targetJobId || runIdRef.current !== expectedRunId) {
          return;
        }
        if (pollErr instanceof Error && pollErr.name === "AbortError") {
          return;
        }

        const statusCode =
          pollErr instanceof ApiClientError ? pollErr.statusCode : undefined;
        const isTransient =
          statusCode === undefined ||
          statusCode === 408 ||
          statusCode === 429 ||
          (statusCode >= 500 && statusCode <= 599);

        if (!isTransient) {
          const errMsg =
            pollErr instanceof ApiClientError
              ? pollErr.message
              : "Unable to retrieve analysis status.";
          setApiError(errMsg);
          setApiErrorStatusCode(statusCode ?? null);
          setStatus("error");
          setIsLoading(false);
          isSubmittingRef.current = false;
          return;
        }

        consecutiveFailuresRef.current += 1;
        const backoffMs = Math.min(
          POLLING_INTERVAL_MS * 2 ** Math.min(consecutiveFailuresRef.current, 10),
          MAX_POLL_BACKOFF_MS
        );

        // Preserve progress while temporarily unable to contact the backend.
        setProgressMessage(
          "Connection temporarily interrupted. Retrying analysis status..."
        );

        pollTimerRef.current = setTimeout(() => {
          pollJobStatusRef.current?.(targetJobId, expectedRunId);
        }, backoffMs);
      }
    },
    [ownerId]
  );

  useEffect(() => {
    pollJobStatusRef.current = pollJobStatus;
  }, [pollJobStatus]);

  /**
   * Session Restoration Runner:
   * Restores an active or previously completed analysis without re-running stages or calling Gemini/Brave.
   */
  const restoreSession = useCallback(async () => {
    const session = loadActiveSession();
    if (!session || (!session.jobId && !session.analysisId)) {
      setIsRestoring(false);
      return;
    }

    setIsRestoring(true);
    setRestorationError(null);

    const targetLookupId = session.jobId || session.analysisId!;
    const effectiveOwner = ownerId || session.ownerId;

    try {
      const statusResp = await getAnalysisJobStatus(targetLookupId, effectiveOwner);
      const canonicalJobId = statusResp.job_id || session.jobId || targetLookupId;

      if (statusResp.status === "succeeded") {
        const finalResult = await getAnalysisJobResult(targetLookupId, effectiveOwner);
        activeJobIdRef.current = canonicalJobId;
        setJobId(canonicalJobId);
        setJobStatus("succeeded");
        setPipelineStage("completed");
        setApiResponse(finalResult);
        setStatus("completed");
        setIsLoading(false);

        if (finalResult.question) {
          setFormData((prev) => ({
            ...prev,
            question: finalResult.question,
          }));
        }

        saveActiveSession({
          jobId: canonicalJobId,
          analysisId: finalResult.analysis_id,
          ownerId: effectiveOwner,
        });
      } else if (statusResp.status === "queued" || statusResp.status === "running") {
        activeJobIdRef.current = canonicalJobId;
        setJobId(canonicalJobId);
        setJobStatus(statusResp.status);
        setPipelineStage(statusResp.stage);
        setProgressMessage(statusResp.progress_message || "Resuming analysis...");
        setIsLoading(true);
        setStatus("submitting");

        pollTimerRef.current = setTimeout(() => {
          pollJobStatusRef.current?.(canonicalJobId, runIdRef.current);
        }, POLLING_INTERVAL_MS);
      } else if (statusResp.status === "timed_out") {
        setJobStatus("timed_out");
        setApiError(
          "Gemini may be experiencing high traffic or taking longer than expected to respond. Your analysis couldn't be completed in time. Please try again shortly."
        );
        setApiErrorStatusCode(504);
        setStatus("error");
      } else if (statusResp.status === "failed") {
        setJobStatus("failed");
        setApiError(
          statusResp.error || "The previous decision analysis encountered an unrecoverable failure."
        );
        setApiErrorStatusCode(statusResp.error_status_code || 500);
        setStatus("error");
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.statusCode === 404) {
          // If query with jobId failed but analysisId is present, try direct lookup with analysisId
          if (session.analysisId && session.analysisId !== targetLookupId) {
            try {
              const directResult = await getAnalysisJobResult(session.analysisId, effectiveOwner);
              activeJobIdRef.current = session.analysisId;
              setJobId(session.analysisId);
              setJobStatus("succeeded");
              setPipelineStage("completed");
              setApiResponse(directResult);
              setStatus("completed");
              setIsLoading(false);
              if (directResult.question) {
                setFormData((prev) => ({ ...prev, question: directResult.question }));
              }
              return;
            } catch {
              // Both lookups failed
            }
          }
          setRestorationError("Your previous analysis could not be found.");
          clearActiveSession();
        } else if (err.statusCode === 403) {
          setRestorationError("Access to the previous analysis was denied.");
          clearActiveSession();
        } else {
          setRestorationError(`Unable to reconnect to the analysis service: ${err.message}`);
        }
      } else {
        setRestorationError("Unable to reconnect to the analysis service. Please verify that the backend is running.");
      }
    } finally {
      setIsRestoring(false);
    }
  }, [ownerId]);

  // Execute session restoration on initial mount
  useEffect(() => {
    const timer = setTimeout(() => {
      restoreSession();
    }, 0);

    return () => {
      clearTimeout(timer);
    };
  }, [restoreSession]);

  const submitAnalysis = useCallback(async (): Promise<boolean> => {
    // Prevent double submission
    if (isSubmittingRef.current || isLoading || isRestoring) {
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

    const currentRunId = ++runIdRef.current;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

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
      const jobResponse = await createAnalysisJob(
        {
          question: trimmedQuestion,
          context: contextPayload,
          constraints: constraintsList,
        },
        ownerId,
        abortController.signal
      );

      if (runIdRef.current !== currentRunId) {
        return false;
      }

      const newJobId = jobResponse.job_id;
      activeJobIdRef.current = newJobId;
      setJobId(newJobId);
      setJobStatus(jobResponse.status);
      setPipelineStage(jobResponse.stage);
      if (jobResponse.progress_message) {
        setProgressMessage(jobResponse.progress_message);
      }

      // Persist active session immediately
      saveActiveSession({
        jobId: newJobId,
        ownerId: ownerId ?? undefined,
      });

      // Step 2: Begin bounded polling cycle
      pollTimerRef.current = setTimeout(() => {
        pollJobStatusRef.current?.(newJobId, currentRunId);
      }, POLLING_INTERVAL_MS);

      return true;
    } catch (error) {
      if (runIdRef.current !== currentRunId || (error instanceof Error && error.name === "AbortError")) {
        return false;
      }
      const statusCode =
        error instanceof ApiClientError && typeof error.statusCode === "number"
          ? error.statusCode
          : null;
      const errorMessage =
        statusCode === 504
          ? "Gemini may be experiencing high traffic or taking longer than expected to respond. Your analysis couldn't be completed in time. Please try again shortly."
          : error instanceof ApiClientError
            ? error.message
            : "An unexpected error occurred while communicating with the AURA backend.";
      setApiError(errorMessage);
      setApiErrorStatusCode(statusCode);
      setJobStatus(statusCode === 504 ? "timed_out" : "failed");
      setStatus("error");
      setIsLoading(false);
      isSubmittingRef.current = false;
      activeJobIdRef.current = null;
      return false;
    }
  }, [formData, isLoading, isRestoring, ownerId, clearPollingTimer]);

  return {
    formData,
    status,
    isLoading,
    isRestoring,
    restorationError,
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
    stopAnalysis,
    retryRestoration: restoreSession,
  };
}
