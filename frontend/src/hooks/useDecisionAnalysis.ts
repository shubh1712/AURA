"use client";

import { useState, useCallback, useRef } from "react";
import { DecisionFormData, DecisionStatus, AnalysisResponse } from "@/types";
import { analyzeDecision, ApiClientError } from "@/lib/api";

export interface UseDecisionAnalysisReturn {
  formData: DecisionFormData;
  status: DecisionStatus;
  isLoading: boolean;
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

/**
 * Reusable React hook for managing decision intake, validation,
 * loading and error states, and real FastAPI backend communication.
 */
export function useDecisionAnalysis(): UseDecisionAnalysisReturn {
  const [formData, setFormData] = useState<DecisionFormData>(INITIAL_FORM_DATA);
  const [status, setStatus] = useState<DecisionStatus>("idle");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [apiErrorStatusCode, setApiErrorStatusCode] = useState<number | null>(null);
  const [apiResponse, setApiResponse] = useState<AnalysisResponse | null>(null);
  const isSubmittingRef = useRef<boolean>(false);

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
    isSubmittingRef.current = false;
    setFormData(INITIAL_FORM_DATA);
    setStatus("idle");
    setIsLoading(false);
    setValidationError(null);
    setApiError(null);
    setApiErrorStatusCode(null);
    setApiResponse(null);
  }, []);

  const submitAnalysis = useCallback(async (): Promise<boolean> => {
    // Prevent double submission via ref guard and state check
    if (isSubmittingRef.current || isLoading) {
      return false;
    }

    const trimmedQuestion = formData.question.trim();

    // Client-side validation for required question
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
    setValidationError(null);
    setApiError(null);
    setApiErrorStatusCode(null);
    setApiResponse(null); // Clear any prior stale result
    setIsLoading(true);
    setStatus("submitting");

    // Parse constraints into array of strings (from newlines or commas)
    const rawConstraints = formData.constraints.trim();
    const constraintsList = rawConstraints
      ? rawConstraints
          .split(/\r?\n|,/)
          .map((c) => c.trim())
          .filter((c) => c.length > 0)
      : [];

    // Parse context into dictionary if provided
    const trimmedContext = formData.context.trim();
    const contextPayload = trimmedContext
      ? { notes: trimmedContext }
      : undefined;

    try {
      // Direct call to real FastAPI backend POST /api/analyze
      const response = await analyzeDecision({
        question: trimmedQuestion,
        context: contextPayload,
        constraints: constraintsList,
      });

      setApiResponse(response);
      setStatus("completed");
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
      return false;
    } finally {
      setIsLoading(false);
      isSubmittingRef.current = false;
    }
  }, [formData, isLoading]);

  return {
    formData,
    status,
    isLoading,
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
