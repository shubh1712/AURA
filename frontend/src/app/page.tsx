"use client";

import React from "react";
import { Header } from "@/components/common/Header";
import { DecisionHero } from "@/components/decision/DecisionHero";
import { DecisionForm } from "@/components/decision/DecisionForm";
import { AnalysisResultCard } from "@/components/decision/AnalysisResultCard";
import { useDecisionAnalysis } from "@/hooks";

export default function AuraPage() {
  const {
    formData,
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
  } = useDecisionAnalysis();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitAnalysis();
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-950 text-zinc-100 selection:bg-zinc-800 selection:text-white">
      {/* Top Navigation */}
      <Header />

      {/* Main Workspace Area */}
      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12 space-y-8">
        {/* 1 & 2: AURA Logo/Name & Short Description */}
        <DecisionHero />

        {/* 3, 4, 5, 6, 7, 8: Decision Form, Inputs, Button, Loading & Error States */}
        <div className="rounded-2xl border border-zinc-800/80 bg-zinc-900/30 p-6 sm:p-8 backdrop-blur-sm shadow-sm">
          <DecisionForm
            formData={formData}
            isLoading={isLoading}
            jobId={jobId}
            jobStatus={jobStatus}
            pipelineStage={pipelineStage}
            progressMessage={progressMessage}
            validationError={validationError}
            apiError={apiError}
            apiErrorStatusCode={apiErrorStatusCode}
            onFieldChange={updateField}
            onSubmit={handleSubmit}
            onReset={reset}
            onClearError={clearError}
            onRetry={submitAnalysis}
          />
        </div>

        {/* 9: Analysis Result Card (displayed once real FastAPI response returns) */}
        {apiResponse && (
          <section aria-labelledby="analysis-result-title">
            <AnalysisResultCard result={apiResponse} onReset={reset} />
          </section>
        )}
      </main>

      {/* Minimal Footer */}
      <footer className="border-t border-zinc-900 py-6 text-center text-xs text-zinc-500 font-sans">
        AURA &mdash; Decision intelligence for complex choices.
      </footer>
    </div>
  );
}
