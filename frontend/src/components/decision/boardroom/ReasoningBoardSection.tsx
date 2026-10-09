"use client";

import React, { useState } from "react";
import type {
  ReasoningBoard,
  PerspectiveType,
  EvidencePackage,
  DecisionModel,
} from "@/types";
import { PerspectiveCard } from "./PerspectiveCard";
import { DisagreementsSection } from "./DisagreementsSection";
import { BoardSynthesisSection } from "./BoardSynthesisSection";

interface ReasoningBoardSectionProps {
  board: ReasoningBoard;
  evidencePackage?: EvidencePackage | null;
  decisionModel?: DecisionModel | null;
}

const CANONICAL_ORDER: PerspectiveType[] = [
  "growth",
  "finance",
  "customer",
  "risk",
];

export function ReasoningBoardSection({
  board,
  evidencePackage,
  decisionModel,
}: ReasoningBoardSectionProps) {
  // View mode: 'all' to show all four perspectives stacked, or a specific tab
  const [selectedPerspective, setSelectedPerspective] = useState<
    PerspectiveType | "all"
  >("all");

  if (!board) {
    return null;
  }

  // Ensure perspectives are sorted canonically: growth, finance, customer, risk
  const sortedPerspectives = [...(board.perspectives || [])].sort((a, b) => {
    const idxA = CANONICAL_ORDER.indexOf(a.perspective_type);
    const idxB = CANONICAL_ORDER.indexOf(b.perspective_type);
    return (idxA >= 0 ? idxA : 99) - (idxB >= 0 ? idxB : 99);
  });

  const displayedPerspectives =
    selectedPerspective === "all"
      ? sortedPerspectives
      : sortedPerspectives.filter(
          (p) => p.perspective_type === selectedPerspective
        );

  return (
    <div className="space-y-8" aria-label="AI Boardroom Deliberation">
      {/* 1. Boardroom Masthead & Perspective Navigation */}
      <section
        aria-labelledby="boardroom-main-title"
        className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 space-y-6 text-zinc-100 shadow-sm"
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-5 border-b border-zinc-800/80">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-wider text-purple-400 font-semibold">
                Deliberation Engine
              </span>
              <span className="rounded bg-purple-950/40 border border-purple-800/50 px-2 py-0.5 text-[10px] font-mono text-purple-300">
                4 Canonical Perspectives
              </span>
            </div>
            <h2
              id="boardroom-main-title"
              className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-1"
            >
              AI Boardroom Deliberation
            </h2>
            <p className="text-xs sm:text-sm text-zinc-400 mt-1 max-w-2xl font-sans">
              Structured multi-perspective evaluation across distinct strategic mandates:
              Growth, Finance, Customer, and Risk.
            </p>
          </div>

          <div className="flex flex-col items-start sm:items-end gap-1">
            <span className="text-[11px] font-mono text-zinc-500">Board ID</span>
            <code className="text-xs font-mono text-zinc-300 bg-zinc-950/70 px-2 py-1 rounded border border-zinc-800 break-all">
              {board.id}
            </code>
          </div>
        </div>

        {/* Perspective Quick Filter / Tab Bar */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs text-zinc-400 font-medium mr-1">View:</span>
          <button
            type="button"
            onClick={() => setSelectedPerspective("all")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer border ${
              selectedPerspective === "all"
                ? "bg-zinc-100 text-zinc-900 border-zinc-100 font-semibold"
                : "bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:text-zinc-200 hover:bg-zinc-800/60"
            }`}
          >
            All 4 Perspectives ({sortedPerspectives.length})
          </button>

          {CANONICAL_ORDER.map((type) => {
            const exists = sortedPerspectives.some(
              (p) => p.perspective_type === type
            );
            if (!exists) return null;

            const isSelected = selectedPerspective === type;
            const labels: Record<PerspectiveType, string> = {
              growth: "📈 Growth",
              finance: "💰 Finance",
              customer: "👥 Customer",
              risk: "🛡️ Risk",
            };

            return (
              <button
                key={type}
                type="button"
                onClick={() => setSelectedPerspective(type)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer border capitalize ${
                  isSelected
                    ? "bg-zinc-100 text-zinc-900 border-zinc-100 font-semibold"
                    : "bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:text-zinc-200 hover:bg-zinc-800/60"
                }`}
              >
                {labels[type]}
              </button>
            );
          })}
        </div>
      </section>

      {/* 2. Four Canonical Perspective Cards */}
      <section
        aria-label="Perspective Evaluations"
        className="space-y-6"
      >
        <div className="grid grid-cols-1 gap-6">
          {displayedPerspectives.map((persp) => (
            <PerspectiveCard
              key={persp.id}
              perspective={persp}
              evidencePackage={evidencePackage}
              decisionModel={decisionModel}
            />
          ))}
        </div>
      </section>

      {/* 3. Disagreements Section (Dialectical Friction) */}
      {board.disagreements && board.disagreements.length > 0 && (
        <section aria-label="Boardroom Disagreements">
          <DisagreementsSection disagreements={board.disagreements} />
        </section>
      )}

      {/* 4. Board Synthesis & Strategic Alignment */}
      {board.synthesis && (
        <section aria-label="Boardroom Synthesis">
          <BoardSynthesisSection
            synthesis={board.synthesis}
            evidencePackage={evidencePackage}
            decisionModel={decisionModel}
          />
        </section>
      )}
    </div>
  );
}
