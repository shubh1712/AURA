"use client";

import React from "react";
import type { EvidencePackage } from "@/types";

interface EvidenceQualityDistributionProps {
  pkg?: EvidencePackage | null;
}

export function EvidenceQualityDistribution({ pkg }: EvidenceQualityDistributionProps) {
  if (!pkg) return null;

  const totalReqs = pkg.requirements?.length || 0;
  const fulfilled = pkg.requirements?.filter((r) => r.status === "fulfilled").length || 0;
  const contested = pkg.requirements?.filter((r) => r.status === "contested").length || 0;
  const pending = pkg.requirements?.filter((r) => r.status === "pending").length || 0;
  const unsupported = pkg.requirements?.filter((r) => r.status === "unsupported").length || 0;

  const fulfilledPct = totalReqs > 0 ? (fulfilled / totalReqs) * 100 : 0;
  const contestedPct = totalReqs > 0 ? (contested / totalReqs) * 100 : 0;
  const pendingPct = totalReqs > 0 ? (pending / totalReqs) * 100 : 0;
  const unsupportedPct = totalReqs > 0 ? (unsupported / totalReqs) * 100 : 0;

  const sources = pkg.sources || [];

  return (
    <div
      className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-5 space-y-4"
      role="region"
      aria-label="Evidence Quality Distribution"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400 font-semibold">
            Empirical Integrity
          </span>
          <h4 className="text-sm font-semibold text-white tracking-tight mt-0.5">
            Source-Quality Distribution &amp; Evidence Directory
          </h4>
        </div>
        <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
          {sources.length} Verified {sources.length === 1 ? "Source" : "Sources"}
        </span>
      </div>

      {/* Distribution Segmented Bar */}
      {totalReqs > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-zinc-400">Requirement Fulfillment Distribution</span>
            <span className="text-emerald-400 font-bold">
              {fulfilled} of {totalReqs} fulfilled ({fulfilledPct.toFixed(0)}%)
            </span>
          </div>

          <div className="h-3 w-full rounded overflow-hidden flex bg-zinc-900">
            {fulfilledPct > 0 && (
              <div
                style={{ width: `${fulfilledPct}%` }}
                className="bg-emerald-500 h-full"
                title={`${fulfilled} Fulfilled`}
              />
            )}
            {pendingPct > 0 && (
              <div
                style={{ width: `${pendingPct}%` }}
                className="bg-amber-500 h-full"
                title={`${pending} Pending`}
              />
            )}
            {contestedPct > 0 && (
              <div
                style={{ width: `${contestedPct}%` }}
                className="bg-rose-500 h-full"
                title={`${contested} Contested`}
              />
            )}
            {unsupportedPct > 0 && (
              <div
                style={{ width: `${unsupportedPct}%` }}
                className="bg-zinc-600 h-full"
                title={`${unsupported} Unsupported`}
              />
            )}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-3 text-[10px] font-mono text-zinc-400 pt-0.5">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span>Fulfilled ({fulfilled})</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-amber-500" />
              <span>Pending ({pending})</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              <span>Contested ({contested})</span>
            </span>
            {unsupported > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-zinc-600" />
                <span>Unsupported ({unsupported})</span>
              </span>
            )}
          </div>
        </div>
      )}

      {/* Concise Source Cards */}
      <div className="space-y-2 pt-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
          Authoritative Sources Consulted
        </span>
        {sources.length === 0 ? (
          <p className="text-xs text-zinc-500 italic">No external sources cited.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {sources.slice(0, 6).map((src) => (
              <div
                key={src.id}
                className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-2.5 space-y-1 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-zinc-200 truncate">{src.title}</span>
                  <span className="text-[10px] font-mono text-zinc-400 uppercase bg-zinc-950 px-1.5 py-0.2 rounded border border-zinc-800">
                    {src.source_type}
                  </span>
                </div>
                {src.url && (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] text-sky-400 hover:text-sky-300 hover:underline truncate block"
                  >
                    {src.url}
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
