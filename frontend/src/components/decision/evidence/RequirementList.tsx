"use client";

import React, { useMemo } from "react";
import type { EvidencePackage } from "@/types";
import { RequirementCard } from "./RequirementCard";
import { EvidenceItemCard } from "./EvidenceItemCard";

interface RequirementListProps {
  pkg: EvidencePackage;
}

export function RequirementList({ pkg }: RequirementListProps) {
  // 1. Build deterministic O(1) lookup maps
  const { requirementEvidenceMap, entityLevelLinks } = useMemo(() => {
    const sourcesMap = new Map(pkg.sources.map((s) => [s.id, s]));
    const itemsMap = new Map(pkg.items.map((i) => [i.id, i]));

    // Map requirement_id -> array of { link, item, source }
    const reqMap = new Map<
      string,
      Array<{
        link: typeof pkg.claim_links[0];
        item?: typeof pkg.items[0];
        source?: typeof pkg.sources[0];
      }>
    >();

    // Initialize map for all requirements
    for (const req of pkg.requirements) {
      reqMap.set(req.id, []);
    }

    // Separate links: strictly join on requirement_id when present
    const unassignedLinks: Array<{
      link: typeof pkg.claim_links[0];
      item?: typeof pkg.items[0];
      source?: typeof pkg.sources[0];
    }> = [];

    for (const link of pkg.claim_links) {
      const item = itemsMap.get(link.evidence_item_id);
      const source = item ? sourcesMap.get(item.source_id) : undefined;
      const joinedObj = { link, item, source };

      if (link.requirement_id && reqMap.has(link.requirement_id)) {
        reqMap.get(link.requirement_id)!.push(joinedObj);
      } else {
        // Link has null requirement_id (or unrecognized ID); do not guess requirement ownership
        unassignedLinks.push(joinedObj);
      }
    }

    return {
      sourcesById: sourcesMap,
      itemsById: itemsMap,
      requirementEvidenceMap: reqMap,
      entityLevelLinks: unassignedLinks,
    };
  }, [pkg]);

  return (
    <div className="space-y-6">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
            Factual Grounding
          </span>
          <h3 className="text-lg font-semibold text-white tracking-tight">
            Evidence by Requirement ({pkg.requirements.length})
          </h3>
        </div>
        <span className="text-xs text-zinc-400">
          Evaluates hypotheses against consulted external and internal sources
        </span>
      </div>

      {/* Requirement Cards List */}
      {pkg.requirements.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-900/20 p-6 text-center text-xs text-zinc-500">
          No evidence requirements were derived for this decision.
        </div>
      ) : (
        <div className="space-y-4">
          {pkg.requirements.map((req) => (
            <RequirementCard
              key={req.id}
              requirement={req}
              linkedEvidence={requirementEvidenceMap.get(req.id) || []}
            />
          ))}
        </div>
      )}

      {/* Separate Section for Entity-Level / Null-Requirement Links (Requirement 6) */}
      {entityLevelLinks.length > 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 space-y-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-sky-400" />
              <h4 className="text-sm font-semibold text-white tracking-tight">
                Entity-Level Evidence ({entityLevelLinks.length})
              </h4>
            </div>
            <p className="text-xs text-zinc-400 mt-1">
              Findings mapped directly to decision entities without specific requirement bindings.
              Preserved separately to avoid false attribution or duplication across requirements.
            </p>
          </div>

          <div className="space-y-3">
            {entityLevelLinks.map(({ link, item, source }) => (
              <div key={link.id} className="space-y-1.5">
                <span className="text-[11px] font-mono text-zinc-500 block">
                  Target Entity: {link.target_entity_type} ({link.target_entity_id})
                </span>
                <EvidenceItemCard link={link} item={item} source={source} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
