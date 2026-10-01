"use client";

import React from "react";
import { Header } from "@/components/common/Header";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/Card";
import { DecisionInputForm } from "@/components/decision/DecisionInputForm";
import { PillarsOverview } from "@/components/decision/PillarsOverview";
import { useDecisionAnalysis } from "@/hooks";

export default function AuraPage() {
  const {
    input,
    status,
    isLoading,
    validationError,
    apiError,
    apiResponse,
    updateField,
    reset,
    submitAnalysis,
  } = useDecisionAnalysis();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitAnalysis();
  };

  return (
    <div className="min-h-screen flex flex-col bg-zinc-950 text-zinc-100">
      <Header />

      <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
        {/* Hero Section */}
        <section className="space-y-3 max-w-3xl">
          <div className="inline-flex items-center space-x-2 rounded-full border border-indigo-900/60 bg-indigo-950/40 px-3 py-1 text-xs text-indigo-300">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
            <span>Connected Frontend & Backend &mdash; Day 1 Architecture</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
            Decision-Intelligence Platform
          </h1>
          <p className="text-base text-zinc-400 leading-relaxed">
            AURA helps operators analyze medium-complexity decisions by
            decomposing variables and constraints, modeling second-order
            externalities, and testing resilience against deterministic
            scenarios.
          </p>
        </section>

        {/* Core Analysis Workspace Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Main Decision Form Area */}
          <div className="lg:col-span-7 space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Decision Intake & Staging</CardTitle>
                  <span className="rounded bg-zinc-800 px-2 py-0.5 text-[11px] font-mono uppercase tracking-wider text-zinc-300">
                    Status: {status}
                  </span>
                </div>
                <CardDescription>
                  Formulate a decision question. The form dispatches to the
                  FastAPI backend at <code className="text-indigo-400 font-mono">/api/analyze</code> via the API client abstraction.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DecisionInputForm
                  input={input}
                  status={status}
                  isLoading={isLoading}
                  validationError={validationError}
                  apiError={apiError}
                  apiResponse={apiResponse}
                  onFieldChange={updateField}
                  onSubmit={handleSubmit}
                  onReset={reset}
                />
              </CardContent>
            </Card>

            {/* Architecture Hygiene Card */}
            <Card className="border-dashed border-zinc-800 bg-zinc-950/50">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-zinc-300">
                  Separation of Concerns Checklist
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-xs text-zinc-400 space-y-2 list-disc list-inside">
                  <li>
                    <strong className="text-zinc-200">Presentation Layer:</strong> Pure UI components in{" "}
                    <code className="text-zinc-300 font-mono">@/components</code>
                  </li>
                  <li>
                    <strong className="text-zinc-200">State & Validation:</strong> Isolated in reusable hooks via{" "}
                    <code className="text-zinc-300 font-mono">@/hooks</code>
                  </li>
                  <li>
                    <strong className="text-zinc-200">Typed Contracts:</strong> Unified data contracts in{" "}
                    <code className="text-zinc-300 font-mono">@/types</code>
                  </li>
                  <li>
                    <strong className="text-zinc-200">Backend Communication:</strong> HTTP transport in{" "}
                    <code className="text-zinc-300 font-mono">@/lib/api</code> (native fetch API, zero axios)
                  </li>
                </ul>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar / Pillar Overview */}
          <div className="lg:col-span-5 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>System Capabilities</CardTitle>
                <CardDescription>
                  10 core pillars of the planned AURA reasoning engine.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PillarsOverview />
              </CardContent>
            </Card>

            <Card className="bg-gradient-to-br from-zinc-900/60 to-zinc-950 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-sm">Backend Engine Connection</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center space-x-3 text-xs text-zinc-400">
                  <div className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  <span>Target: <code className="text-zinc-300 font-mono">NEXT_PUBLIC_API_BASE_URL</code></span>
                </div>
                <p className="mt-2 text-[11px] text-zinc-500 leading-normal">
                  All requests route dynamically to the configured backend base URL without hardcoded hosts.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>

      <footer className="border-t border-zinc-900 py-6 text-center text-xs text-zinc-500">
        AURA &mdash; Autonomous Reasoning & Architecture for Decision Intelligence
      </footer>
    </div>
  );
}
