"use client";

import React from "react";
import type {
  ClaimEvidenceLink,
  EvidenceItem,
  EvidenceKind,
  EvidenceRequirement,
  RequirementStatus,
  Source,
} from "@/types";
import { EvidenceItemCard } from "./EvidenceItemCard";

interface RequirementCardProps {
  requirement: EvidenceRequirement;
  linkedEvidence: Array<{
    link: ClaimEvidenceLink;
    item?: EvidenceItem;
    source?: Source;
  }>;
}

function getKindBadge(kind: EvidenceKind) {
  switch (kind) {
    case "external_research":
      return {
        label: "External Research",
        className: "bg-sky-950/50 text-sky-300 border-sky-800/60",
      };
    case "internal_data":
      return {
        label: "Internal / Telemetry Data",
        className: "bg-purple-950/50 text-purple-300 border-purple-800/60",
      };
    case "user_clarification":
      return {
        label: "User Clarification Required",
        className: "bg-amber-950/50 text-amber-300 border-amber-800/60",
      };
    case "deterministic_calculation":
      return {
        label: "Deterministic Calculation",
        className: "bg-teal-950/50 text-teal-300 border-teal-800/60",
      };
  }
}

function getStatusBadge(status: RequirementStatus) {
  switch (status) {
    case "fulfilled":
      return {
        label: "Fulfilled",
        className: "bg-emerald-950/60 text-emerald-300 border-emerald-800/70",
        dotColor: "bg-emerald-400",
      };
    case "contested":
      return {
        label: "Contested / Conflicting",
        className: "bg-rose-950/70 text-rose-300 border-rose-700 font-semibold animate-pulse",
        dotColor: "bg-rose-400",
      };
    case "pending":
      return {
        label: "Pending Inquiry",
        className: "bg-amber-950/50 text-amber-300 border-amber-800/60",
        dotColor: "bg-amber-400",
      };
    case "unsupported":
      return {
        label: "Unsupported",
        className: "bg-zinc-800 text-zinc-400 border-zinc-700",
        dotColor: "bg-zinc-500",
      };
    case "inconclusive":
      return {
        label: "Inconclusive",
        className: "bg-zinc-800 text-zinc-300 border-zinc-700",
        dotColor: "bg-zinc-400",
      };
  }
}

export function RequirementCard({ requirement, linkedEvidence }: RequirementCardProps) {
  const kindBadge = getKindBadge(requirement.kind);
  const statusBadge = getStatusBadge(requirement.status);

  // Check for stance conflict in empirical findings
  const hasSupporting = linkedEvidence.some((e) => e.link.stance === "supports");
  const hasChallenging = linkedEvidence.some((e) => e.link.stance === "challenges");
  const isContested = requirement.status === "contested" || (hasSupporting && hasChallenging);

  // Separate findings by stance polarity for transparency without averaging
  const supportingFindings = linkedEvidence.filter((e) => e.link.stance === "supports");
  const challengingFindings = linkedEvidence.filter((e) => e.link.stance === "challenges");
  const contextFindings = linkedEvidence.filter(
    (e) => e.link.stance === "context" || e.link.stance === "inconclusive"
  );

  return (
    <div
      className={`rounded-xl border ${
        isContested ? "border-rose-800/60 bg-rose-950/10" : "border-zinc-800/90 bg-zinc-900/30"
      } p-5 space-y-4 shadow-sm`}
    >
      {/* Top Header: Target, Kind, Priority, Status */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-3 border-b border-zinc-800/70">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Status Badge */}
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-xs font-mono font-medium border ${statusBadge.className}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${statusBadge.dotColor}`} />
            {statusBadge.label}
          </span>

          {/* Kind Badge */}
          <span
            className={`px-2 py-0.5 rounded text-xs font-mono font-medium border ${kindBadge.className}`}
          >
            {kindBadge.label}
          </span>

          {/* Priority */}
          <span className="text-[11px] font-mono text-zinc-400 bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800">
            Priority: {requirement.priority}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-500">
          <span>Target: {requirement.target_entity_type} ({requirement.target_entity_id})</span>
          <span>&bull;</span>
          <span>{requirement.id}</span>
        </div>
      </div>

      {/* Requirement Factual Statement */}
      <div className="space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
          Investigative Hypothesis / Evidence Requirement
        </span>
        <p className="text-sm sm:text-base font-medium text-white leading-relaxed">
          {requirement.description}
        </p>
      </div>

      {/* Contested Conflict Callout Banner */}
      {isContested && (
        <div
          role="alert"
          className="rounded-lg border border-rose-800/80 bg-rose-950/40 p-3.5 text-xs text-rose-200 space-y-1"
        >
          <div className="flex items-center gap-2 font-semibold text-rose-300">
            <span aria-hidden="true">&bull;</span>
            <span>Conflicting Empirical Findings Detected</span>
          </div>
          <p className="text-rose-200/90 leading-relaxed font-sans">
            This requirement contains directly contradictory evidence across consulted sources.
            Both supporting and challenging findings are presented below without averaging or forced synthesis.
          </p>
        </div>
      )}

      {/* Suggested Provider Queries (if external research) */}
      {requirement.suggested_queries && requirement.suggested_queries.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 block">
            Targeted Query Lineage
          </span>
          <div className="flex flex-wrap gap-1.5">
            {requirement.suggested_queries.map((q, idx) => (
              <span
                key={idx}
                className="text-[11px] font-mono text-zinc-400 bg-zinc-950/80 px-2 py-0.5 rounded border border-zinc-800/80"
              >
                &ldquo;{q}&rdquo;
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Linked Empirical Findings */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between text-xs border-b border-zinc-800/40 pb-1.5">
          <span className="font-semibold uppercase tracking-wider text-zinc-400 text-[11px]">
            Linked Empirical Evidence ({linkedEvidence.length})
          </span>
          {isContested && (
            <span className="text-[10px] font-mono text-rose-400">
              {supportingFindings.length} Supports vs {challengingFindings.length} Challenges
            </span>
          )}
        </div>

        {linkedEvidence.length === 0 ? (
          <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-950/30 p-4 text-xs text-zinc-400 leading-relaxed font-sans">
            {requirement.kind === "external_research" && (
              <p>No external findings were retrieved for this requirement during search.</p>
            )}
            {requirement.kind === "internal_data" && (
              <p>
                <strong className="text-zinc-300">Internal Data Required:</strong> This premise depends on
                proprietary internal telemetry, customer records, or financial warehouses not accessible
                via public search.
              </p>
            )}
            {requirement.kind === "user_clarification" && (
              <p>
                <strong className="text-zinc-300">Decision-Maker Clarification Required:</strong> This premise
                involves organizational preferences or strategic boundaries requiring direct user input.
              </p>
            )}
            {requirement.kind === "deterministic_calculation" && (
              <p>
                <strong className="text-zinc-300">Quantitative Task:</strong> Reserved for downstream
                mathematical and deterministic modeling engines.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {/* If contested, render Supporting vs Challenging with clear headers */}
            {isContested ? (
              <>
                {supportingFindings.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-[11px] font-mono font-medium text-emerald-400 flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      Supporting Evidence ({supportingFindings.length})
                    </span>
                    <div className="space-y-2.5">
                      {supportingFindings.map(({ link, item, source }) => (
                        <EvidenceItemCard key={link.id} link={link} item={item} source={source} />
                      ))}
                    </div>
                  </div>
                )}

                {challengingFindings.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <span className="text-[11px] font-mono font-medium text-rose-400 flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                      Challenging / Contradictory Evidence ({challengingFindings.length})
                    </span>
                    <div className="space-y-2.5">
                      {challengingFindings.map(({ link, item, source }) => (
                        <EvidenceItemCard key={link.id} link={link} item={item} source={source} />
                      ))}
                    </div>
                  </div>
                )}

                {contextFindings.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <span className="text-[11px] font-mono font-medium text-zinc-400">
                      Context &amp; Inconclusive Evidence ({contextFindings.length})
                    </span>
                    <div className="space-y-2.5">
                      {contextFindings.map(({ link, item, source }) => (
                        <EvidenceItemCard key={link.id} link={link} item={item} source={source} />
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              // Non-contested: sequential list of evidence cards
              linkedEvidence.map(({ link, item, source }) => (
                <EvidenceItemCard key={link.id} link={link} item={item} source={source} />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
