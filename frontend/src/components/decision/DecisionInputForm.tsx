import React from "react";
import { DecisionInput, DecisionStatus, AnalysisResponse } from "@/types";
import { Button } from "@/components/ui/Button";

export interface DecisionInputFormProps {
  input: DecisionInput;
  status?: DecisionStatus;
  isLoading: boolean;
  validationError: string | null;
  apiError: string | null;
  apiResponse: AnalysisResponse | null;
  onFieldChange: (field: keyof DecisionInput, value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onReset: () => void;
}

export function DecisionInputForm({
  input,
  isLoading,
  validationError,
  apiError,
  apiResponse,
  onFieldChange,
  onSubmit,
  onReset,
}: DecisionInputFormProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="decision-title"
          className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5"
        >
          Decision Question / Problem Statement *
        </label>
        <input
          id="decision-title"
          type="text"
          disabled={isLoading}
          value={input.title}
          onChange={(e) => onFieldChange("title", e.target.value)}
          placeholder="e.g., Should we migrate our monolithic database to a distributed architecture?"
          className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
        />
      </div>

      <div>
        <label
          htmlFor="decision-context"
          className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5"
        >
          Operational Context & Background (Optional)
        </label>
        <textarea
          id="decision-context"
          rows={3}
          disabled={isLoading}
          value={input.context}
          onChange={(e) => onFieldChange("context", e.target.value)}
          placeholder="Provide background, scale metrics, deadlines, or technical scope..."
          className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
        />
      </div>

      <div>
        <label
          htmlFor="decision-target"
          className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5"
        >
          Primary Constraint / Target Outcome (Optional)
        </label>
        <input
          id="decision-target"
          type="text"
          disabled={isLoading}
          value={input.targetOutcome || ""}
          onChange={(e) => onFieldChange("targetOutcome", e.target.value)}
          placeholder="e.g., Zero downtime migration under $25,000 budget"
          className="w-full rounded-lg border border-zinc-800 bg-zinc-950/70 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
        />
      </div>

      {validationError && (
        <div className="rounded-lg border border-amber-800/40 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          {validationError}
        </div>
      )}

      {apiError && (
        <div className="rounded-lg border border-red-800/50 bg-red-950/40 px-3.5 py-2.5 text-xs text-red-300">
          <p className="font-semibold">Backend Communication Error</p>
          <p className="text-red-400/90 mt-0.5">{apiError}</p>
        </div>
      )}

      {apiResponse && (
        <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/30 p-3.5 text-xs text-emerald-300 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-emerald-200">
              Analysis Staged Successfully
            </span>
            <span className="rounded bg-emerald-900/60 px-2 py-0.5 font-mono text-[10px] text-emerald-300 border border-emerald-800/60">
              {apiResponse.status}
            </span>
          </div>
          <p className="text-zinc-300">{apiResponse.message}</p>
          <div className="border-t border-emerald-900/50 pt-2 text-[11px] text-emerald-400 font-mono">
            Analysis ID: {apiResponse.analysis_id}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 pt-2">
        <Button
          type="submit"
          variant="primary"
          size="md"
          disabled={isLoading}
        >
          {isLoading ? "Submitting to Engine..." : "Submit for Analysis"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="md"
          disabled={isLoading}
          onClick={onReset}
        >
          Reset
        </Button>
      </div>
    </form>
  );
}
