"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { DecisionIntegrityReport } from "@/types";
import { getDecisionIntegrity } from "@/lib/api";

interface UseDecisionIntegrityResult {
  integrityReport: DecisionIntegrityReport | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useDecisionIntegrity(
  analysisId: string | null | undefined,
  ownerId?: string | null
): UseDecisionIntegrityResult {
  const [integrityReport, setIntegrityReport] =
    useState<DecisionIntegrityReport | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Cache to avoid refetching on section toggles
  const cachedIdRef = useRef<string | null>(null);

  const fetchIntegrity = useCallback(async () => {
    if (!analysisId) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await getDecisionIntegrity(analysisId, ownerId);
      setIntegrityReport(data);
      cachedIdRef.current = analysisId;
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to load decision integrity evaluation.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [analysisId, ownerId]);

  useEffect(() => {
    if (analysisId && cachedIdRef.current !== analysisId) {
      fetchIntegrity();
    }
  }, [analysisId, fetchIntegrity]);

  return {
    integrityReport,
    isLoading,
    error,
    refetch: fetchIntegrity,
  };
}
