"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import type {
  SimulationVariableDiscoveryResponse,
  SimulationResult,
  SimulationAdjustment,
  SimulationSubmitRequest,
  SimulationExplanationResponse,
} from "@/types";
import {
  getSimulationVariables,
  runSimulation as apiRunSimulation,
  listSimulations as apiListSimulations,
  explainSimulation as apiExplainSimulation,
  getCachedSimulationExplanation as apiGetCachedSimulationExplanation,
  ApiClientError,
} from "@/lib/api";

export interface UseWhatIfSimulationReturn {
  isLoadingDiscovery: boolean;
  discoveryError: string | null;
  discoveryErrorStatusCode: number | null;
  discovery: SimulationVariableDiscoveryResponse | null;
  adjustments: Record<string, number>;
  rawInputs: Record<string, string>;
  inputErrors: Record<string, string>;
  hasChanges: boolean;
  isValid: boolean;
  canRunSimulation: boolean;
  isSimulating: boolean;
  simulationError: string | null;
  simulationErrorStatusCode: number | null;
  activeResult: SimulationResult | null;
  history: SimulationResult[];
  isLoadingHistory: boolean;
  historyError: string | null;
  selectedSimulationId: string | null;
  explanation: SimulationExplanationResponse | null;
  isExplaining: boolean;
  explanationError: string | null;
  explanationErrorStatusCode: number | null;
  setAdjustment: (variableId: string, rawValue: string | number) => void;
  resetToBaseline: () => void;
  runSimulation: () => Promise<SimulationResult | null>;
  requestExplanation: () => Promise<SimulationExplanationResponse | null>;
  loadHistory: () => Promise<void>;
  selectSavedSimulation: (sim: SimulationResult) => void | Promise<void>;
  clearErrors: () => void;
  reloadDiscovery: () => Promise<void>;
}

export function useWhatIfSimulation(
  analysisId: string,
  enabled: boolean = true,
  ownerId?: string | null
): UseWhatIfSimulationReturn {
  const [isLoadingDiscovery, setIsLoadingDiscovery] = useState<boolean>(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [discoveryErrorStatusCode, setDiscoveryErrorStatusCode] = useState<number | null>(null);
  const [discovery, setDiscovery] = useState<SimulationVariableDiscoveryResponse | null>(null);

  const [adjustments, setAdjustments] = useState<Record<string, number>>({});
  const [rawInputs, setRawInputs] = useState<Record<string, string>>({});
  const [inputErrors, setInputErrors] = useState<Record<string, string>>({});

  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [simulationErrorStatusCode, setSimulationErrorStatusCode] = useState<number | null>(null);
  const [activeResult, setActiveResult] = useState<SimulationResult | null>(null);

  const [history, setHistory] = useState<SimulationResult[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [selectedSimulationId, setSelectedSimulationId] = useState<string | null>(null);

  const [explanation, setExplanation] = useState<SimulationExplanationResponse | null>(null);
  const [isExplaining, setIsExplaining] = useState<boolean>(false);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [explanationErrorStatusCode, setExplanationErrorStatusCode] = useState<number | null>(null);

  const activeAnalysisIdRef = useRef<string>(analysisId);
  const isSubmittingRef = useRef<boolean>(false);

  // Keep ref synchronized with analysisId
  useEffect(() => {
    activeAnalysisIdRef.current = analysisId;
  }, [analysisId]);

  const loadHistory = useCallback(async () => {
    if (!analysisId) return;
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const resp = await apiListSimulations(analysisId, ownerId);
      if (activeAnalysisIdRef.current === analysisId) {
        setHistory(resp.simulations || []);
      }
    } catch (err) {
      if (activeAnalysisIdRef.current === analysisId) {
        const msg = err instanceof ApiClientError ? err.message : "Failed to load simulation history.";
        setHistoryError(msg);
      }
    } finally {
      if (activeAnalysisIdRef.current === analysisId) {
        setIsLoadingHistory(false);
      }
    }
  }, [analysisId, ownerId]);

  const loadDiscovery = useCallback(async () => {
    if (!enabled || !analysisId) return;

    setIsLoadingDiscovery(true);
    setDiscovery(null);
    setAdjustments({});
    setRawInputs({});
    setInputErrors({});
    setActiveResult(null);
    setHistory([]);
    setSelectedSimulationId(null);
    setSimulationError(null);
    setDiscoveryError(null);
    setDiscoveryErrorStatusCode(null);
    setExplanation(null);
    setIsExplaining(false);
    setExplanationError(null);
    setExplanationErrorStatusCode(null);

    try {
      const resp = await getSimulationVariables(analysisId, ownerId);
      if (activeAnalysisIdRef.current !== analysisId) return;

      setDiscovery(resp);

      // Initialize adjustments and raw inputs to baseline values
      const initialAdjustments: Record<string, number> = {};
      const initialRaw: Record<string, string> = {};
      for (const v of resp.variables) {
        initialAdjustments[v.variable_id] = v.baseline_value;
        initialRaw[v.variable_id] = String(v.baseline_value);
      }
      setAdjustments(initialAdjustments);
      setRawInputs(initialRaw);
      setInputErrors({});

      // Also trigger history load
      void loadHistory();
    } catch (err) {
      if (activeAnalysisIdRef.current !== analysisId) return;

      if (err instanceof ApiClientError) {
        setDiscoveryError(err.message);
        setDiscoveryErrorStatusCode(err.statusCode ?? null);
      } else {
        setDiscoveryError("Failed to discover simulation variables from analysis.");
        setDiscoveryErrorStatusCode(null);
      }
    } finally {
      if (activeAnalysisIdRef.current === analysisId) {
        setIsLoadingDiscovery(false);
      }
    }
  }, [analysisId, enabled, ownerId, loadHistory]);

  // Initial fetch on mount or analysisId / enabled change
  useEffect(() => {
    let ignore = false;
    if (enabled && analysisId) {
      void Promise.resolve().then(() => {
        if (!ignore) {
          void loadDiscovery();
        }
      });
    }
    return () => {
      ignore = true;
    };
  }, [analysisId, enabled, loadDiscovery]);

  const setAdjustment = useCallback(
    (variableId: string, rawVal: string | number) => {
      const strVal = String(rawVal);
      setRawInputs((prev) => ({ ...prev, [variableId]: strVal }));

      // Find variable definition
      const targetVar = discovery?.variables.find((v) => v.variable_id === variableId);
      if (!targetVar) return;

      const trimmed = strVal.trim();
      if (trimmed === "") {
        setInputErrors((prev) => ({
          ...prev,
          [variableId]: "Value cannot be empty.",
        }));
        return;
      }

      const numVal = Number(trimmed);
      if (!Number.isFinite(numVal)) {
        setInputErrors((prev) => ({
          ...prev,
          [variableId]: "Value must be a finite number.",
        }));
        return;
      }

      // Check bounds
      if (targetVar.minimum_value !== null && targetVar.minimum_value !== undefined) {
        if (numVal < targetVar.minimum_value) {
          setInputErrors((prev) => ({
            ...prev,
            [variableId]: `Value cannot be less than ${targetVar.minimum_value}${targetVar.unit ? ` ${targetVar.unit}` : ""}.`,
          }));
          setAdjustments((prev) => ({ ...prev, [variableId]: numVal }));
          return;
        }
      }

      if (targetVar.maximum_value !== null && targetVar.maximum_value !== undefined) {
        if (numVal > targetVar.maximum_value) {
          setInputErrors((prev) => ({
            ...prev,
            [variableId]: `Value cannot exceed ${targetVar.maximum_value}${targetVar.unit ? ` ${targetVar.unit}` : ""}.`,
          }));
          setAdjustments((prev) => ({ ...prev, [variableId]: numVal }));
          return;
        }
      }

      // Valid number within bounds
      setInputErrors((prev) => {
        const next = { ...prev };
        delete next[variableId];
        return next;
      });
      setAdjustments((prev) => ({ ...prev, [variableId]: numVal }));
      if (simulationError) {
        setSimulationError(null);
        setSimulationErrorStatusCode(null);
      }
      // Any slider movement clears the existing explanation
      setExplanation(null);
      setExplanationError(null);
      setExplanationErrorStatusCode(null);
    },
    [discovery, simulationError]
  );

  const resetToBaseline = useCallback(() => {
    if (!discovery) return;
    const initialAdjustments: Record<string, number> = {};
    const initialRaw: Record<string, string> = {};
    for (const v of discovery.variables) {
      initialAdjustments[v.variable_id] = v.baseline_value;
      initialRaw[v.variable_id] = String(v.baseline_value);
    }
    setAdjustments(initialAdjustments);
    setRawInputs(initialRaw);
    setInputErrors({});
    setActiveResult(null);
    setSelectedSimulationId(null);
    setSimulationError(null);
    setSimulationErrorStatusCode(null);
    setExplanation(null);
    setIsExplaining(false);
    setExplanationError(null);
    setExplanationErrorStatusCode(null);
  }, [discovery]);

  // Determine if there are actual adjustments differing from baseline
  const hasChanges = useMemo(() => {
    if (!discovery) return false;
    return discovery.variables.some((v) => {
      if (!v.simulation_supported) return false;
      const currentVal = adjustments[v.variable_id];
      return currentVal !== undefined && Math.abs(currentVal - v.baseline_value) > 1e-9;
    });
  }, [discovery, adjustments]);

  const isValid = useMemo(() => {
    return Object.keys(inputErrors).length === 0;
  }, [inputErrors]);

  const canRunSimulation = useMemo(() => {
    return hasChanges && isValid && !isSimulating && discovery !== null;
  }, [hasChanges, isValid, isSimulating, discovery]);

  const runSimulation = useCallback(async (): Promise<SimulationResult | null> => {
    if (!canRunSimulation || !discovery || isSubmittingRef.current) {
      return null;
    }

    isSubmittingRef.current = true;
    setIsSimulating(true);
    setSimulationError(null);
    setSimulationErrorStatusCode(null);
    setExplanation(null);
    setExplanationError(null);
    setExplanationErrorStatusCode(null);

    // Filter adjustments for variables that have actually changed
    const changedAdjustments: SimulationAdjustment[] = [];
    for (const v of discovery.variables) {
      if (!v.simulation_supported) continue;
      const current = adjustments[v.variable_id];
      if (current !== undefined && Math.abs(current - v.baseline_value) > 1e-9) {
        changedAdjustments.push({
          variable_id: v.variable_id,
          proposed_value: current,
          unit: v.unit ?? null,
        });
      }
    }

    if (changedAdjustments.length === 0) {
      setSimulationError("No variable adjustments detected to simulate.");
      setIsSimulating(false);
      isSubmittingRef.current = false;
      return null;
    }

    const payload: SimulationSubmitRequest = {
      adjustments: changedAdjustments,
      baseline_fingerprint: discovery.baseline_fingerprint,
    };

    try {
      const result = await apiRunSimulation(analysisId, payload, ownerId);
      if (activeAnalysisIdRef.current !== analysisId) {
        return null;
      }

      setActiveResult(result);
      setSelectedSimulationId(result.id);

      // Prepend to history if not already present
      setHistory((prev) => {
        const exists = prev.some((s) => s.id === result.id);
        if (exists) return prev;
        return [result, ...prev];
      });

      return result;
    } catch (err) {
      if (activeAnalysisIdRef.current !== analysisId) {
        return null;
      }

      if (err instanceof ApiClientError) {
        setSimulationError(err.message);
        setSimulationErrorStatusCode(err.statusCode ?? null);
      } else {
        setSimulationError("An unexpected error occurred during simulation execution.");
        setSimulationErrorStatusCode(null);
      }
      return null;
    } finally {
      if (activeAnalysisIdRef.current === analysisId) {
        setIsSimulating(false);
      }
      isSubmittingRef.current = false;
    }
  }, [canRunSimulation, discovery, adjustments, analysisId, ownerId]);

  const selectSavedSimulation = useCallback(
    async (sim: SimulationResult) => {
      setActiveResult(sim);
      setSelectedSimulationId(sim.id);
      setExplanation(null);
      setExplanationError(null);
      setExplanationErrorStatusCode(null);

      // Align inputs with the applied adjustments from the saved run
      if (discovery) {
        const nextAdjustments: Record<string, number> = {};
        const nextRaw: Record<string, string> = {};
        // Start from baseline
        for (const v of discovery.variables) {
          nextAdjustments[v.variable_id] = v.baseline_value;
          nextRaw[v.variable_id] = String(v.baseline_value);
        }
        // Override with applied adjustments
        for (const adj of sim.applied_adjustments) {
          nextAdjustments[adj.variable_id] = adj.proposed_value;
          nextRaw[adj.variable_id] = String(adj.proposed_value);
        }
        setAdjustments(nextAdjustments);
        setRawInputs(nextRaw);
        setInputErrors({});
      }

      // Automatically check for and restore a cached explanation if available (0 LLM calls)
      if (analysisId && sim.id) {
        try {
          const cached = await apiGetCachedSimulationExplanation(analysisId, sim.id, ownerId);
          if (activeAnalysisIdRef.current === analysisId) {
            setExplanation(cached);
          }
        } catch {
          // Stale cache or network issue; leaves explanation null cleanly
        }
      }
    },
    [discovery, analysisId, ownerId]
  );

  const requestExplanation = useCallback(async (): Promise<SimulationExplanationResponse | null> => {
    if (!activeResult || !activeResult.id || !analysisId || isExplaining) {
      return null;
    }

    setIsExplaining(true);
    setExplanationError(null);
    setExplanationErrorStatusCode(null);

    try {
      const exp = await apiExplainSimulation(analysisId, activeResult.id, ownerId);
      if (activeAnalysisIdRef.current === analysisId) {
        setExplanation(exp);
      }
      return exp;
    } catch (err) {
      if (activeAnalysisIdRef.current === analysisId) {
        if (err instanceof ApiClientError) {
          setExplanationError(err.message);
          setExplanationErrorStatusCode(err.statusCode ?? null);
        } else {
          setExplanationError("An unexpected error occurred while generating AI explanation.");
          setExplanationErrorStatusCode(null);
        }
      }
      return null;
    } finally {
      if (activeAnalysisIdRef.current === analysisId) {
        setIsExplaining(false);
      }
    }
  }, [activeResult, analysisId, isExplaining, ownerId]);

  const clearErrors = useCallback(() => {
    setDiscoveryError(null);
    setDiscoveryErrorStatusCode(null);
    setSimulationError(null);
    setSimulationErrorStatusCode(null);
    setExplanationError(null);
    setExplanationErrorStatusCode(null);
  }, []);

  return {
    isLoadingDiscovery,
    discoveryError,
    discoveryErrorStatusCode,
    discovery,
    adjustments,
    rawInputs,
    inputErrors,
    hasChanges,
    isValid,
    canRunSimulation,
    isSimulating,
    simulationError,
    simulationErrorStatusCode,
    activeResult,
    history,
    isLoadingHistory,
    historyError,
    selectedSimulationId,
    explanation,
    isExplaining,
    explanationError,
    explanationErrorStatusCode,
    setAdjustment,
    resetToBaseline,
    runSimulation,
    requestExplanation,
    loadHistory,
    selectSavedSimulation,
    clearErrors,
    reloadDiscovery: loadDiscovery,
  };
}
