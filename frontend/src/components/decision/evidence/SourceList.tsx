"use client";

import React from "react";
import type { Source } from "@/types";

interface SourceListProps {
  sources: Source[];
}

function checkSafeUrl(rawUrl?: string | null): boolean {
  if (!rawUrl) return false;
  try {
    const parsed = new URL(rawUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 sm:p-6 space-y-4 text-zinc-100 shadow-sm">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-zinc-800/80">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
            Source Provenance Directory
          </span>
          <h3 className="text-lg font-semibold text-white tracking-tight mt-0.5">
            Consulted Sources ({sources.length})
          </h3>
        </div>
        <span className="text-xs text-zinc-400">
          Sources retrieved during evidence research with provenance metadata
        </span>
      </div>

      {/* Sources Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {sources.map((src) => {
          const isUrlSafe = checkSafeUrl(src.url);

          return (
            <div
              key={src.id}
              className="rounded-lg border border-zinc-800/80 bg-zinc-950/60 p-4 space-y-2.5 text-xs flex flex-col justify-between"
            >
              <div className="space-y-1.5">
                {/* Source Type Badge & Identifier */}
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-300 border border-zinc-700">
                    {src.source_type}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-500">{src.id}</span>
                </div>

                {/* Title */}
                <h4 className="font-medium text-white text-sm leading-snug break-words">
                  {src.title}
                </h4>
              </div>

              {/* Publisher & Metadata */}
              <div className="pt-2 border-t border-zinc-800/50 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-400">
                <div className="flex items-center gap-2">
                  {src.publisher && <span className="font-medium text-zinc-300">{src.publisher}</span>}
                  {src.publication_date && (
                    <span className="font-mono text-zinc-500">&bull; {src.publication_date}</span>
                  )}
                </div>

                {/* Safe Outbound URL */}
                {isUrlSafe && src.url ? (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-400 hover:text-indigo-300 hover:underline font-mono inline-flex items-center gap-1 text-[11px]"
                    aria-label={`Open external publication: ${src.title}`}
                  >
                    <span>Inspect</span>
                    <span aria-hidden="true">&rarr;</span>
                  </a>
                ) : (
                  <span className="text-zinc-600 font-mono text-[10px]">No external URL</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
