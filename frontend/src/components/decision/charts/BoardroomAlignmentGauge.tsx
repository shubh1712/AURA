"use client";

import React, { useMemo } from "react";
import type { ReasoningBoard, PerspectiveType } from "@/types";

interface BoardroomAlignmentGaugeProps {
  board?: ReasoningBoard | null;
}

interface PerspectiveMetrics {
  type: PerspectiveType;
  title: string;
  icon: string;
  favorableCount: number;
  unfavorableCount: number;
  neutralCount: number;
  concernsCount: number;
  opportunitiesCount: number;
  summary: string;
  stance: "favorable" | "conditional" | "critical";
  stanceLabel: string;
}

const PERSPECTIVE_CONFIG: Record<
  PerspectiveType,
  { title: string; icon: string; borderAccent: string }
> = {
  growth: {
    title: "Growth & Market",
    icon: "↗",
    borderAccent: "border-sky-500/40 text-sky-400",
  },
  finance: {
    title: "Finance & ROI",
    icon: "💰",
    borderAccent: "border-emerald-500/40 text-emerald-400",
  },
  customer: {
    title: "Customer & Brand",
    icon: "👥",
    borderAccent: "border-purple-500/40 text-purple-400",
  },
  risk: {
    title: "Risk & Compliance",
    icon: "🛡",
    borderAccent: "border-amber-500/40 text-amber-400",
  },
};

export function BoardroomAlignmentGauge({ board }: BoardroomAlignmentGaugeProps) {
  const perspectives = board?.perspectives;

  const data = useMemo(() => {
    if (!perspectives || perspectives.length === 0) {
      return null;
    }

    let totalFavorable = 0;
    let totalUnfavorable = 0;
    let totalNeutral = 0;

    const list: PerspectiveMetrics[] = perspectives.map((p) => {
      const args = p.arguments || [];
      const fav = args.filter((a) => a.direction === "favorable").length;
      const unfav = args.filter((a) => a.direction === "unfavorable").length;
      const neu = args.filter(
        (a) => a.direction === "neutral" || a.direction === "mixed"
      ).length;

      totalFavorable += fav;
      totalUnfavorable += unfav;
      totalNeutral += neu;

      const cfg = PERSPECTIVE_CONFIG[p.perspective_type] || {
        title: p.perspective_type.toUpperCase(),
        icon: "⚖",
        borderAccent: "border-zinc-700 text-zinc-300",
      };

      let stance: "favorable" | "conditional" | "critical" = "conditional";
      let stanceLabel = "Balanced / Conditional";

      if (fav > unfav) {
        stance = "favorable";
        stanceLabel = "Net Favorable";
      } else if (unfav > fav) {
        stance = "critical";
        stanceLabel = "Net Vigilant";
      }

      return {
        type: p.perspective_type,
        title: cfg.title,
        icon: cfg.icon,
        favorableCount: fav,
        unfavorableCount: unfav,
        neutralCount: neu,
        concernsCount: (p.concerns || []).length,
        opportunitiesCount: (p.opportunities || []).length,
        summary: p.summary || "",
        stance,
        stanceLabel,
      };
    });

    const totalArgs = totalFavorable + totalUnfavorable + totalNeutral;
    const favPct = totalArgs > 0 ? Math.round((totalFavorable / totalArgs) * 100) : 0;
    const unfavPct = totalArgs > 0 ? Math.round((totalUnfavorable / totalArgs) * 100) : 0;
    const neuPct = totalArgs > 0 ? Math.max(0, 100 - favPct - unfavPct) : 0;

    return {
      metrics: list,
      totalFavorable,
      totalUnfavorable,
      totalNeutral,
      totalArgs,
      favPct,
      unfavPct,
      neuPct,
      agreements: board?.synthesis?.areas_of_agreement || [],
      disagreementsCount: (board?.disagreements || []).length,
    };
  }, [board, perspectives]);

  if (!data || data.totalArgs === 0) {
    return null;
  }

  return (
    <div
      className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-5 sm:p-6 space-y-5 text-zinc-100 shadow-sm"
      role="region"
      aria-label="AI Boardroom Consensus and Perspective Alignment"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-zinc-800/80">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold">
              Deliberation Consensus
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </div>
          <h3 className="text-base sm:text-lg font-bold text-white tracking-tight mt-0.5">
            AI Boardroom Alignment &amp; Argument Distribution
          </h3>
          <p className="text-xs text-zinc-400 mt-0.5 font-sans leading-relaxed">
            Synthesis across 4 specialized analytical perspectives (Growth, Finance, Customer, Risk) evaluating baseline viability.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] font-mono text-zinc-300 bg-zinc-900 px-2.5 py-1 rounded-md border border-zinc-800">
            {data.totalArgs} Evaluated Arguments
          </span>
          {data.disagreementsCount > 0 && (
            <span className="text-[11px] font-mono text-amber-300 bg-amber-950/40 px-2.5 py-1 rounded-md border border-amber-800/60">
              {data.disagreementsCount} Debated Points
            </span>
          )}
        </div>
      </div>

      {/* 100% Horizontal Stacked Argument Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-zinc-400 flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Favorable: <strong className="text-emerald-300">{data.favPct}%</strong> ({data.totalFavorable})
          </span>
          <span className="text-zinc-400 flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-sky-400" />
            Neutral/Mixed: <strong className="text-sky-300">{data.neuPct}%</strong> ({data.totalNeutral})
          </span>
          <span className="text-zinc-400 flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-400" />
            Vigilant/Opposing: <strong className="text-rose-300">{data.unfavPct}%</strong> ({data.totalUnfavorable})
          </span>
        </div>

        {/* Stacked Progress Bar */}
        <div
          className="h-3 w-full bg-zinc-900 rounded-full overflow-hidden flex shadow-inner border border-zinc-800"
          role="progressbar"
          aria-label="Boardroom consensus argument distribution"
          aria-valuenow={data.favPct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          {data.favPct > 0 && (
            <div
              style={{ width: `${data.favPct}%` }}
              className="bg-emerald-500 hover:bg-emerald-400 transition-all duration-300"
              title={`Favorable: ${data.favPct}% (${data.totalFavorable} arguments)`}
            />
          )}
          {data.neuPct > 0 && (
            <div
              style={{ width: `${data.neuPct}%` }}
              className="bg-sky-500 hover:bg-sky-400 transition-all duration-300"
              title={`Neutral/Mixed: ${data.neuPct}% (${data.totalNeutral} arguments)`}
            />
          )}
          {data.unfavPct > 0 && (
            <div
              style={{ width: `${data.unfavPct}%` }}
              className="bg-rose-500 hover:bg-rose-400 transition-all duration-300"
              title={`Vigilant/Opposing: ${data.unfavPct}% (${data.totalUnfavorable} arguments)`}
            />
          )}
        </div>
      </div>

      {/* 4 Perspective Stance Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 pt-1">
        {data.metrics.map((p) => {
          const cfg = PERSPECTIVE_CONFIG[p.type];

          const stanceColor =
            p.stance === "favorable"
              ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60"
              : p.stance === "critical"
              ? "bg-rose-950/60 text-rose-300 border-rose-800/60"
              : "bg-sky-950/60 text-sky-300 border-sky-800/60";

          return (
            <div
              key={p.type}
              className="rounded-xl border border-zinc-800/90 bg-zinc-900/40 p-3.5 space-y-2.5 flex flex-col justify-between hover:border-zinc-700 transition-colors"
            >
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-semibold text-white tracking-tight flex items-center gap-1.5">
                    <span className="text-sm">{p.icon}</span>
                    {cfg?.title || p.title}
                  </span>
                  <span
                    className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase font-bold ${stanceColor}`}
                  >
                    {p.stanceLabel}
                  </span>
                </div>

                {p.summary && (
                  <p className="text-[11px] text-zinc-300 line-clamp-2 leading-relaxed font-sans">
                    {p.summary}
                  </p>
                )}
              </div>

              {/* Arguments breakdown strip */}
              <div className="pt-2 border-t border-zinc-800/70 flex items-center justify-between text-[10px] font-mono text-zinc-400">
                <span className="text-emerald-400 font-semibold">
                  +{p.favorableCount} Pro
                </span>
                <span className="text-zinc-500">|</span>
                <span className="text-rose-400 font-semibold">
                  -{p.unfavorableCount} Con
                </span>
                <span className="text-zinc-500">|</span>
                <span className="text-zinc-400">
                  {p.concernsCount} Concerns
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Synthesis Areas of Agreement Pills */}
      {data.agreements.length > 0 && (
        <div className="pt-2 border-t border-zinc-800/80 space-y-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold block">
            Core Boardroom Consensus Points
          </span>
          <div className="flex flex-wrap gap-2">
            {data.agreements.slice(0, 3).map((agree, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1.5 text-xs text-zinc-200 bg-zinc-900/80 border border-zinc-800 px-3 py-1 rounded-lg"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                <span className="leading-snug">{agree}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
