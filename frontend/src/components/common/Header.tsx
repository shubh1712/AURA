import React from "react";

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center space-x-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white shadow-md shadow-indigo-500/20">
            A
          </div>
          <div>
            <span className="text-base font-bold tracking-tight text-white">
              AURA
            </span>
            <span className="ml-2 text-xs text-zinc-400 hidden sm:inline-block">
              Decision Intelligence
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <span className="inline-flex items-center rounded-full bg-indigo-950/60 px-2.5 py-1 text-xs font-medium text-indigo-400 border border-indigo-800/50">
            Day 1 Architecture
          </span>
          <span className="inline-flex items-center rounded-full bg-zinc-800/60 px-2.5 py-1 text-xs text-zinc-400 border border-zinc-700/50">
            v0.0.1-pre-alpha
          </span>
        </div>
      </div>
    </header>
  );
}
