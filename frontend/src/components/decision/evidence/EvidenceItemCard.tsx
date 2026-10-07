"use client";

import React from "react";
import type { ClaimEvidenceLink, EvidenceItem, Source } from "@/types";

interface EvidenceItemCardProps {
  link: ClaimEvidenceLink;
  item?: EvidenceItem | null;
  source?: Source | null;
}

export function isSafeUrl(rawUrl?: string | null): boolean {
  if (!rawUrl) return false;
  try {
    const parsed = new URL(rawUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function EvidenceItemCard({ link, item, source }: EvidenceItemCardProps) {
  // Stance formatting preserving exact backend semantics
  const stanceConfig = {
    supports: {
      label: "SUPPORTS",
      badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/70",
      dotClass: "bg-emerald-400",
      borderClass: "border-emerald-900/40",
    },
    challenges: {
      label: "CHALLENGES",
      badgeClass: "bg-rose-950/60 text-rose-300 border-rose-800/70",
      dotClass: "bg-rose-400",
      borderClass: "border-rose-900/40",
    },
    context: {
      label: "CONTEXT",
      badgeClass: "bg-sky-950/60 text-sky-300 border-sky-800/70",
      dotClass: "bg-sky-400",
      borderClass: "border-sky-900/40",
    },
    inconclusive: {
      label: "INCONCLUSIVE",
      badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
      dotClass: "bg-zinc-400",
      borderClass: "border-zinc-800/60",
    },
  }[link.stance] || {
    label: link.stance.toUpperCase(),
    badgeClass: "bg-zinc-800 text-zinc-300 border-zinc-700",
    dotClass: "bg-zinc-400",
    borderClass: "border-zinc-800/60",
  };

  const hasSafeUrl = isSafeUrl(source?.url);

  return (
    <div
      className={`rounded-lg border ${stanceConfig.borderClass} bg-zinc-950/60 p-4 space-y-3.5 text-xs text-zinc-200 transition-colors`}
    >
      {/* Top Header: Stance, Confidence, and Link Identifier */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {/* Stance Badge */}
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-medium border ${stanceConfig.badgeClass}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${stanceConfig.dotClass}`} />
            {stanceConfig.label}
          </span>

          {/* Relationship Confidence */}
          <span className="text-[10px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
            Link Confidence: {link.relationship_confidence}
          </span>
        </div>

        <span className="font-mono text-[10px] text-zinc-500">
          ID: {link.id}
        </span>
      </div>

      {/* Primary Evidence Content (Verbatim finding excerpt) */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
          Empirical Finding (Direct Excerpt)
        </span>
        <blockquote className="rounded border-l-2 border-zinc-700 bg-zinc-900/40 px-3 py-2 text-zinc-200 italic leading-relaxed text-xs break-words">
          &ldquo;{item?.content || "Referenced evidence item details unavailable."}&rdquo;
        </blockquote>
      </div>

      {/* AURA Summary / Interpretation (if present and distinct) */}
      {item?.summary && item.summary !== item.content && (
        <div className="space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
            AURA Synthesis
          </span>
          <p className="text-zinc-300 leading-relaxed font-sans">{item.summary}</p>
        </div>
      )}

      {/* Reasoning (Transparent epistemic link rationale) */}
      {link.reasoning && (
        <div className="space-y-1 bg-zinc-900/30 p-2.5 rounded border border-zinc-800/40">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
            Stance Rationale
          </span>
          <p className="text-zinc-300 leading-relaxed">{link.reasoning}</p>
        </div>
      )}

      {/* Structured Numeric Evidence Pills (if extracted) */}
      {item?.numeric_data && item.numeric_data.length > 0 && (
        <div className="space-y-1.5 pt-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block">
            Quantitative Data Points
          </span>
          <div className="flex flex-wrap gap-2">
            {item.numeric_data.map((num, idx) => (
              <div
                key={idx}
                className="rounded border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-[11px] font-mono text-zinc-200 flex items-center gap-1.5"
              >
                <span className="text-zinc-400">{num.metric_name}:</span>
                <span className="font-semibold text-white">
                  {num.value !== null && num.value !== undefined
                    ? num.value
                    : num.range_min !== null && num.range_max !== null
                    ? `[${num.range_min} - ${num.range_max}]`
                    : "Reported"}
                  {num.unit ? ` ${num.unit}` : ""}
                </span>
                {num.confidence_interval && (
                  <span className="text-[10px] text-zinc-400">({num.confidence_interval})</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Linked Source Attribution & Provenance */}
      <div className="pt-2 border-t border-zinc-800/60 flex flex-wrap items-center justify-between gap-2 text-[11px]">
        <div className="flex items-center gap-2 text-zinc-400">
          <span className="font-medium text-zinc-300">
            Source: {source?.title || item?.source_id || "Unknown Source"}
          </span>
          {source?.publisher && (
            <span className="text-zinc-500 font-mono">({source.publisher})</span>
          )}
          {source?.publication_date && (
            <span className="text-zinc-500 font-mono">&bull; {source.publication_date}</span>
          )}
        </div>

        {source && (
          <div className="flex items-center gap-2">
            <span className="rounded bg-zinc-800/60 px-1.5 py-0.5 text-[10px] font-mono text-zinc-400">
              {source.source_type}
            </span>
            {hasSafeUrl && source.url ? (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-400 hover:text-indigo-300 hover:underline font-mono inline-flex items-center gap-1 text-[11px]"
                aria-label={`Open external source: ${source.title}`}
              >
                <span>View Source</span>
                <span aria-hidden="true">&rarr;</span>
              </a>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
