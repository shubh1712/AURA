"use client";

import React, { useEffect, useState } from "react";
import { checkHealth } from "@/lib/api";

export function Header() {
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let isMounted = true;
    checkHealth()
      .then(() => {
        if (isMounted) setBackendOnline(true);
      })
      .catch(() => {
        if (isMounted) setBackendOnline(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <header className="w-full border-b border-zinc-800/80 bg-zinc-950/70 backdrop-blur-md sticky top-0 z-40">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* AURA Logo and Brand */}
        <div className="flex items-center space-x-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 bg-zinc-900 font-mono text-sm font-semibold tracking-wider text-zinc-100 shadow-sm">
            Δ
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-base font-semibold tracking-tight text-white font-mono">
              AURA
            </span>
            <span className="text-xs text-zinc-400 hidden sm:inline">
              Decision Intelligence
            </span>
          </div>
        </div>

        {/* Backend Connectivity Status */}
        <div className="flex items-center space-x-3 text-xs">
          <div className="inline-flex items-center space-x-2 rounded-full border border-zinc-800 bg-zinc-900/60 px-3 py-1 text-zinc-300">
            <span
              className={`h-2 w-2 rounded-full ${
                backendOnline === true
                  ? "bg-emerald-400"
                  : backendOnline === false
                  ? "bg-amber-400"
                  : "bg-zinc-500 animate-pulse"
              }`}
            />
            <span className="text-[11px] font-medium tracking-wide">
              {backendOnline === true
                ? "FastAPI Engine Online"
                : backendOnline === false
                ? "Backend Offline (Port 8000)"
                : "Connecting to Engine..."}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
