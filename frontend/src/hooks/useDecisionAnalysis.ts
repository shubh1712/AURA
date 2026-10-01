"use client";

import { useState, useCallback } from "react";
import { DecisionInput, DecisionStatus, AnalysisResponse } from "@/types";
import { analyzeDecision, ApiClientError } from "@/lib/api";

export interface UseDecisionAnalysisReturn {
  input: DecisionInput;
  status: DecisionStatus;
  isLoading: boolean;
  validationError: string | null;
  apiError: string | null;
  apiResponse: AnalysisResponse | null;
  updateField: (field: keyof DecisionInput, value: string) => void;
  reset: () => void;
  submitAnalysis: () => Promise<boolean>;
}

const INITIAL_INPUT: DecisionInput = {
  title: "",
  context: "",
  targetOutcome: "",
};

/**
 * Reusable React hook for managing decision drafting, validation,
 * and API client communication.
 * Isolates network transport and state management entirely from UI components.
 */
export function useDecisionAnalysis(): UseDecisionAnalysisReturn {
  const [input, setInput] = useState<DecisionInput>(INITIAL_INPUT);
  const [status, setStatus] = useState<DecisionStatus>("draft");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [apiResponse, setApiResponse] = useState<AnalysisResponse | null>(null);

  const updateField = useCallback(
    (field: keyof DecisionInput, value: string) => {
      setInput((prev) => ({
        ...prev,
        [field]: value,
      }));
      if (validationError) setValidationError(null);
      if (apiError) setApiError(null);
    },
    [validationError, apiError]
  );

  const reset = useCallback(() => {
    setInput(INITIAL_INPUT);
    setStatus("draft");
    setIsLoading(false);
    setValidationError(null);
    setApiError(null);
    setApiResponse(null);
  }, []);

  const submitAnalysis = useCallback(async (): Promise<boolean> => {
    // 1. Client-side validation
    const trimmedTitle = input.title.trim();
    if (!trimmedTitle) {
      setValidationError("Decision question cannot be empty.");
      return false;
    }

    if (trimmedTitle.length < 5) {
      setValidationError(
        "Please provide a more descriptive decision question (at least 5 characters)."
      );
      return false;
    }

    setValidationError(null);
    setApiError(null);
    setIsLoading(true);
    setStatus("submitting" as DecisionStatus);

    // 2. Dispatch to backend API client abstraction
    try {
      const response = await analyzeDecision({
        question: trimmedTitle,
        context: input.context
          ? {
              notes: input.context,
              target_outcome: input.targetOutcome || undefined,
            }
          : undefined,
        constraints: input.targetOutcome ? [input.targetOutcome] : [],
      });

      setApiResponse(response);
      setStatus("completed");
      return true;
    } catch (error) {
      const errorMessage =
        error instanceof ApiClientError
          ? error.message
          : "An unexpected error occurred while contacting the decision engine.";
      setApiError(errorMessage);
      setStatus("failed");
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [input]);

  return {
    input,
    status,
    isLoading,
    validationError,
    apiError,
    apiResponse,
    updateField,
    reset,
    submitAnalysis,
  };
}
