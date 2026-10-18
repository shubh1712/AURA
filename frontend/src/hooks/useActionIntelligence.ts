"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type {
  IntelligentActionPlan,
  ValidationWarning,
  ActionPlanResponse,
} from "@/types";
import {
  getActionPlan,
  getActionPlanStatus,
  generateActionPlan as apiGenerateActionPlan,
  ApiClientError,
} from "@/lib/api";

export type ActionPlanUIStatus =
  | "not_generated"
  | "running"
  | "ready"
  | "failed";

export interface UseActionIntelligenceReturn {
  plan: IntelligentActionPlan | null;
  status: ActionPlanUIStatus;
  isLoading: boolean;
  isGenerating: boolean;
  isPolling: boolean;
  isPollingTimeout: boolean;
  cached: boolean;
  error: string | null;
  errorStatusCode: number | null;
  warnings: ValidationWarning[];
  generate: (forceRegenerate?: boolean) => Promise<IntelligentActionPlan | null>;
  loadSavedPlan: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  clearError: () => void;
  clearPollingTimeout: () => void;
}

const POLLING_INTERVAL_MS = 3000;
const MAX_POLLING_ATTEMPTS = 50; // 50 * 3s = 150s bounded timeout (exceeds 120s backend operation timeout)

export function useActionIntelligence(
  analysisId: string,
  enabled: boolean = true,
  ownerId?: string | null
): UseActionIntelligenceReturn {
  const [plan, setPlan] = useState<IntelligentActionPlan | null>(null);
  const [status, setStatus] = useState<ActionPlanUIStatus>("not_generated");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [cached, setCached] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatusCode, setErrorStatusCode] = useState<number | null>(null);
  const [isPollingTimeout, setIsPollingTimeout] = useState<boolean>(false);

  const activeAnalysisIdRef = useRef<string>(analysisId);
  const isSubmittingRef = useRef<boolean>(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pollCountRef = useRef<number>(0);

  // Synchronize ref on analysisId change
  useEffect(() => {
    activeAnalysisIdRef.current = analysisId;
  }, [analysisId]);

  // Cleanup polling timer helper
  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
    pollCountRef.current = 0;
  }, []);

  // Ensure polling stops on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  // Poll status endpoint
  const pollStatus = useCallback(async () => {
    if (!analysisId) return;

    try {
      pollCountRef.current += 1;
      const resp = await getActionPlanStatus(analysisId, ownerId);

      if (activeAnalysisIdRef.current !== analysisId) {
        stopPolling();
        return;
      }

      if (resp.status === "ready" || resp.status === "cached") {
        stopPolling();
        setPlan(resp.plan);
        setStatus("ready");
        setCached(resp.cached);
        setIsGenerating(false);
        setIsPollingTimeout(false);
        setError(null);
        setErrorStatusCode(null);
      } else if (resp.status === "failed") {
        stopPolling();
        setStatus("failed");
        setIsGenerating(false);
        setIsPollingTimeout(false);
        setError(resp.error_message || "Action plan generation failed.");
      } else if (resp.status === "running") {
        setStatus("running");
        if (pollCountRef.current >= MAX_POLLING_ATTEMPTS) {
          stopPolling();
          setIsGenerating(false);
          setIsPollingTimeout(true);
        }
      }
    } catch {
      if (activeAnalysisIdRef.current === analysisId) {
        // If polling reaches max attempts on network or client errors, stop polling without asserting backend failed
        if (pollCountRef.current >= MAX_POLLING_ATTEMPTS) {
          stopPolling();
          setIsGenerating(false);
          setIsPollingTimeout(true);
        }
      }
    }
  }, [analysisId, ownerId, stopPolling]);

  // Start bounded polling
  const startPolling = useCallback(() => {
    stopPolling();
    setIsPolling(true);
    pollCountRef.current = 0;
    pollTimerRef.current = setInterval(pollStatus, POLLING_INTERVAL_MS);
  }, [pollStatus, stopPolling]);

  // Refresh current status without starting generation
  const refreshStatus = useCallback(async () => {
    if (!analysisId) return;

    try {
      setIsPollingTimeout(false);
      const resp = await getActionPlanStatus(analysisId, ownerId);
      if (activeAnalysisIdRef.current === analysisId) {
        if (resp.status === "ready" || resp.status === "cached") {
          setPlan(resp.plan);
          setStatus("ready");
          setCached(resp.cached);
          setError(null);
          setErrorStatusCode(null);
        } else if (resp.status === "running") {
          setStatus("running");
          startPolling();
        } else if (resp.status === "failed") {
          setStatus("failed");
          setError(resp.error_message || "Action plan generation failed.");
        } else {
          setStatus("not_generated");
        }
      }
    } catch (err) {
      if (activeAnalysisIdRef.current === analysisId) {
        const msg =
          err instanceof ApiClientError
            ? err.message
            : "Failed to check action plan status.";
        setError(msg);
        setErrorStatusCode(
          err instanceof ApiClientError ? err.statusCode || null : null
        );
      }
    }
  }, [analysisId, ownerId, startPolling]);

  // Load saved plan (purely read-only; zero LLM calls)
  const loadSavedPlan = useCallback(async () => {
    if (!enabled || !analysisId) return;

    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
    pollCountRef.current = 0;

    setIsLoading(true);
    setPlan(null);
    setStatus("not_generated");
    setError(null);
    setErrorStatusCode(null);
    setCached(false);
    setIsPollingTimeout(false);

    try {
      const resp = await getActionPlan(analysisId, ownerId);

      if (activeAnalysisIdRef.current !== analysisId) return;

      if (resp && resp.plan) {
        setPlan(resp.plan);
        setStatus("ready");
        setCached(true);
      } else {
        // Plan not found via GET (404); check if a generation is currently in progress
        const statResp = await getActionPlanStatus(analysisId, ownerId);
        if (activeAnalysisIdRef.current !== analysisId) return;

        if (statResp.status === "running") {
          setStatus("running");
          startPolling();
        } else if (statResp.status === "failed") {
          setStatus("failed");
          setError(statResp.error_message || "Previous generation failed.");
        } else if (statResp.status === "ready" && statResp.plan) {
          setPlan(statResp.plan);
          setStatus("ready");
          setCached(statResp.cached);
        } else {
          setStatus("not_generated");
        }
      }
    } catch (err) {
      if (activeAnalysisIdRef.current === analysisId) {
        const msg =
          err instanceof ApiClientError
            ? err.message
            : "Failed to load saved action plan.";
        setError(msg);
        setErrorStatusCode(
          err instanceof ApiClientError ? err.statusCode || null : null
        );
        setStatus("not_generated");
      }
    } finally {
      if (activeAnalysisIdRef.current === analysisId) {
        setIsLoading(false);
      }
    }
  }, [analysisId, enabled, ownerId, startPolling]);

  // Load on mount or analysisId change (never triggers generation!)
  useEffect(() => {
    let ignore = false;
    if (enabled && analysisId) {
      void Promise.resolve().then(() => {
        if (!ignore) {
          void loadSavedPlan();
        }
      });
    }
    return () => {
      ignore = true;
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [analysisId, enabled, loadSavedPlan]);

  // Trigger post-analysis generation
  const generate = useCallback(
    async (forceRegenerate: boolean = false): Promise<IntelligentActionPlan | null> => {
      if (!analysisId) return null;
      if (isSubmittingRef.current) return null;

      isSubmittingRef.current = true;
      setIsGenerating(true);
      setError(null);
      setErrorStatusCode(null);
      setIsPollingTimeout(false);

      try {
        const resp: ActionPlanResponse = await apiGenerateActionPlan(
          analysisId,
          forceRegenerate,
          ownerId
        );

        if (activeAnalysisIdRef.current !== analysisId) return null;

        if (resp.status === "ready" || resp.status === "cached") {
          if (resp.plan) {
            setPlan(resp.plan);
            setStatus("ready");
            setCached(resp.cached);
            setIsGenerating(false);
            return resp.plan;
          }
        } else if (resp.status === "running") {
          setStatus("running");
          startPolling();
          return null;
        }

        // If returned without plan
        setStatus("not_generated");
        setIsGenerating(false);
        return null;
      } catch (err) {
        if (activeAnalysisIdRef.current === analysisId) {
          if (err instanceof ApiClientError && err.statusCode === 409) {
            // Concurrent generation already running: poll instead of failing!
            setStatus("running");
            startPolling();
            return null;
          }

          const msg =
            err instanceof ApiClientError
              ? err.message
              : "Action plan generation failed.";
          setError(msg);
          setErrorStatusCode(
            err instanceof ApiClientError ? err.statusCode || null : null
          );
          setStatus("failed");
          setIsGenerating(false);
        }
        return null;
      } finally {
        isSubmittingRef.current = false;
      }
    },
    [analysisId, ownerId, startPolling]
  );

  const clearError = useCallback(() => {
    setError(null);
    setErrorStatusCode(null);
  }, []);

  const clearPollingTimeout = useCallback(() => {
    setIsPollingTimeout(false);
  }, []);

  const warnings = plan?.validation_warnings || [];

  return {
    plan,
    status,
    isLoading,
    isGenerating,
    isPolling,
    isPollingTimeout,
    cached,
    error,
    errorStatusCode,
    warnings,
    generate,
    loadSavedPlan,
    refreshStatus,
    clearError,
    clearPollingTimeout,
  };
}
