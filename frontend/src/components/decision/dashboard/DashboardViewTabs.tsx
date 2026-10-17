"use client";

import React from "react";

export type DashboardViewType = "overview" | "explore" | "action" | "details";

interface DashboardViewTabsProps {
  activeView: DashboardViewType;
  onViewChange: (view: DashboardViewType) => void;
  scenarioCount?: number;
  actionCount?: number;
  onPrint?: () => void;
  onReset?: () => void;
}

interface TabConfig {
  id: DashboardViewType;
  label: string;
  badge?: string;
  iconSvg: React.ReactNode;
}

export function DashboardViewTabs({
  activeView,
  onViewChange,
  scenarioCount = 3,
  actionCount,
  onPrint,
  onReset,
}: DashboardViewTabsProps) {
  const tabs: TabConfig[] = [
    {
      id: "overview",
      label: "Overview",
      badge: "Concise",
      iconSvg: (
        <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="9" />
          <rect x="14" y="3" width="7" height="5" />
          <rect x="14" y="12" width="7" height="9" />
          <rect x="3" y="16" width="7" height="5" />
        </svg>
      ),
    },
    {
      id: "explore",
      label: "Explore",
      badge: `${scenarioCount} Scenarios`,
      iconSvg: (
        <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
        </svg>
      ),
    },
    {
      id: "action",
      label: "Action Plan",
      badge: actionCount ? `${actionCount} Actions` : undefined,
      iconSvg: (
        <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 11 12 14 22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
      ),
    },
    {
      id: "details",
      label: "Details & Audit",
      badge: "6 Stages",
      iconSvg: (
        <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      ),
    },
  ];

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let nextIndex = index;
    if (e.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (e.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else {
      return;
    }

    e.preventDefault();
    onViewChange(tabs[nextIndex].id);
    const nextBtn = document.getElementById(`tab-${tabs[nextIndex].id}`);
    nextBtn?.focus();
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3.5 pb-2.5 border-b border-zinc-800/80 print:hidden">
      {/* Tab Navigation List */}
      <div
        role="tablist"
        aria-label="Decision Dashboard Views"
        className="flex items-center gap-1.5 p-1 rounded-xl border border-zinc-800 bg-zinc-900/70 overflow-x-auto max-w-full scrollbar-thin"
      >
        {tabs.map((tab, idx) => {
          const isActive = activeView === tab.id;

          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onViewChange(tab.id)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              className={`inline-flex items-center gap-2.5 px-3.5 py-2 sm:px-4 sm:py-2.5 rounded-lg text-xs sm:text-sm font-semibold transition-all cursor-pointer whitespace-nowrap focus:outline-none focus:ring-2 focus:ring-emerald-500/40 ${
                isActive
                  ? "bg-zinc-800/90 text-white shadow-md border border-zinc-700 ring-1 ring-emerald-500/30"
                  : "text-zinc-300 hover:text-white hover:bg-zinc-800/60"
              }`}
            >
              <span className={`shrink-0 transition-colors ${isActive ? "text-emerald-400" : "text-zinc-400"}`}>
                {tab.iconSvg}
              </span>
              <span className="tracking-tight">{tab.label}</span>
              {tab.badge && (
                <span
                  className={`text-[10px] sm:text-[11px] font-mono px-2 py-0.5 rounded-md font-medium tracking-tight border transition-colors ${
                    isActive
                      ? "bg-zinc-700/80 text-zinc-100 border-zinc-600/60"
                      : "bg-zinc-950/80 text-zinc-400 border-zinc-800/80"
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Auxiliary Actions (Export/Print & Reset) */}
      <div className="flex items-center gap-2.5 shrink-0">
        {onPrint && (
          <button
            type="button"
            onClick={onPrint}
            className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-800/90 px-3.5 py-2 sm:px-4 sm:py-2.5 text-xs sm:text-sm font-semibold text-zinc-100 hover:bg-zinc-750 hover:text-white hover:border-zinc-600 transition-all cursor-pointer shadow-sm focus:outline-none focus:ring-2 focus:ring-zinc-500/50"
            title="Export or print concise report"
          >
            <svg
              className="h-4 w-4 text-zinc-300 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="6 9 6 2 18 2 18 9" />
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
              <rect x="6" y="14" width="12" height="8" />
            </svg>
            <span>Export Report</span>
          </button>
        )}

        {onReset && (
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-950/40 px-3.5 py-2 sm:px-4 sm:py-2.5 text-xs sm:text-sm font-semibold text-emerald-300 hover:bg-emerald-900/50 hover:text-emerald-200 hover:border-emerald-500/60 transition-all cursor-pointer shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            title="Start a new strategic analysis"
          >
            <svg
              className="h-4 w-4 text-emerald-400 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>New Analysis</span>
          </button>
        )}
      </div>
    </div>
  );
}
