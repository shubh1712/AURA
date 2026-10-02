import React from "react";

export function DecisionHero() {
  return (
    <section className="text-center pt-8 pb-4 sm:pt-12 sm:pb-6">
      <div className="inline-flex items-center justify-center space-x-2 rounded-full border border-zinc-800 bg-zinc-900/50 px-3.5 py-1 text-xs text-zinc-400 mb-5">
        <span className="font-mono text-zinc-300 font-semibold tracking-wide">AURA</span>
        <span className="text-zinc-600">&bull;</span>
        <span>Decision Engine</span>
      </div>

      <h1 className="text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight text-white">
        AURA
      </h1>

      <p className="mt-3 text-base sm:text-lg text-zinc-400 max-w-xl mx-auto font-normal leading-relaxed">
        Decision intelligence for complex choices.
      </p>
    </section>
  );
}
