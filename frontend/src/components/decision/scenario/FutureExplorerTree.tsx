"use client";

import React, { useMemo } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  Handle,
  Position,
  type Node,
  type Edge,
} from "@xyflow/react";
import type { FutureScenario, ScenarioType } from "@/types";
import { getScenarioConfig, formatScenarioProbability } from "@/lib/scenarioHelpers";

interface FutureExplorerTreeProps {
  decisionTitle: string;
  scenarios: FutureScenario[];
  selectedScenarioType: ScenarioType;
  onSelectScenario: (type: ScenarioType) => void;
}

// -----------------------------------------------------------------------------
// Custom Node Components
// -----------------------------------------------------------------------------

interface DecisionRootNodeData {
  title: string;
}

function DecisionRootNode({ data }: { data: DecisionRootNodeData }) {
  return (
    <div
      role="region"
      aria-label="Root Decision Anchor"
      className="w-64 rounded-xl border border-zinc-700 bg-zinc-900/90 p-3.5 text-zinc-100 shadow-xl backdrop-blur-sm print:bg-white print:border-zinc-300 print:text-black"
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800 print:border-zinc-200">
        <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-emerald-400 print:text-zinc-700">
          Decision Root
        </span>
        <span className="h-2 w-2 rounded-full bg-emerald-400" />
      </div>
      <p className="text-xs font-semibold text-white print:text-black line-clamp-3 leading-snug">
        {data.title}
      </p>
      <span className="block text-[10px] text-zinc-400 print:text-zinc-600 mt-2 font-mono">
        Stages 1–4 Deliberation Base
      </span>
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2.5 !h-2.5 !bg-emerald-400 !border-2 !border-zinc-900"
      />
    </div>
  );
}

interface ScenarioBranchNodeData {
  scenario: FutureScenario;
  isSelected: boolean;
  onSelect: (type: ScenarioType) => void;
}

function ScenarioBranchNode({ data }: { data: ScenarioBranchNodeData }) {
  const { scenario, isSelected, onSelect } = data;
  const config = getScenarioConfig(scenario.scenario_type);
  const formattedProb = formatScenarioProbability(scenario.probability);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      aria-label={`${config.label} scenario branch: ${scenario.name}, probability ${formattedProb}`}
      onClick={() => onSelect(scenario.scenario_type)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(scenario.scenario_type);
        }
      }}
      className={`w-64 rounded-xl border p-3.5 text-left transition-all cursor-pointer shadow-lg backdrop-blur-sm print:bg-white print:border-zinc-300 print:text-black ${
        isSelected
          ? `${config.activeBorderClass} ${config.activeBgClass}`
          : `${config.borderClass} ${config.bgClass} opacity-85 hover:opacity-100`
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className={`!w-2.5 !h-2.5 !border-2 !border-zinc-900 ${config.dotClass}`}
      />

      <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-zinc-800/80 print:border-zinc-200">
        <span
          className={`text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded ${config.badgeClass} print:bg-zinc-100 print:text-black`}
        >
          {config.label}
        </span>
        <div className="flex items-center gap-1">
          <span
            className={`text-sm font-extrabold font-mono ${config.textClass} print:text-black`}
          >
            {formattedProb}
          </span>
        </div>
      </div>

      <p className="text-xs font-semibold text-white print:text-black line-clamp-2 leading-snug">
        {scenario.name}
      </p>

      <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-zinc-800/50 print:border-zinc-200 text-[10px] text-zinc-400 print:text-zinc-600 font-mono">
        <span>{scenario.timeline?.length ?? 0} Milestones</span>
        <span>{scenario.key_events?.length ?? 0} Events</span>
      </div>
    </div>
  );
}

const nodeTypes = {
  decisionRoot: DecisionRootNode,
  scenarioBranch: ScenarioBranchNode,
};

// -----------------------------------------------------------------------------
// FutureExplorerTree Main Component
// -----------------------------------------------------------------------------

export function FutureExplorerTree({
  decisionTitle,
  scenarios,
  selectedScenarioType,
  onSelectScenario,
}: FutureExplorerTreeProps) {
  // Sort scenarios so Optimistic is top, Base Case is middle, Pessimistic is bottom
  const orderedScenarios = useMemo(() => {
    const map = new Map<ScenarioType, FutureScenario>();
    scenarios.forEach((s) => map.set(s.scenario_type, s));
    return [
      map.get("optimistic") || scenarios[0],
      map.get("base_case") || scenarios[1],
      map.get("pessimistic") || scenarios[2],
    ].filter(Boolean) as FutureScenario[];
  }, [scenarios]);

  // Construct React Flow nodes
  const nodes = useMemo<Node[]>(() => {
    const list: Node[] = [
      {
        id: "root-decision",
        type: "decisionRoot",
        position: { x: 30, y: 130 },
        data: { title: decisionTitle },
        selectable: false,
        draggable: false,
      },
    ];

    // Branch nodes Y coordinates: Optimistic (top), Base (center), Pessimistic (bottom)
    const yOffsets = [20, 140, 260];

    orderedScenarios.forEach((scen, idx) => {
      list.push({
        id: `scenario-${scen.scenario_type}`,
        type: "scenarioBranch",
        position: { x: 380, y: yOffsets[idx] ?? 140 },
        data: {
          scenario: scen,
          isSelected: selectedScenarioType === scen.scenario_type,
          onSelect: onSelectScenario,
        },
        selectable: true,
        draggable: false,
      });
    });

    return list;
  }, [decisionTitle, orderedScenarios, selectedScenarioType, onSelectScenario]);

  // Construct connecting bezier edges
  const edges = useMemo<Edge[]>(() => {
    return orderedScenarios.map((scen) => {
      const isSelected = selectedScenarioType === scen.scenario_type;
      const config = getScenarioConfig(scen.scenario_type);
      return {
        id: `edge-root-${scen.scenario_type}`,
        source: "root-decision",
        target: `scenario-${scen.scenario_type}`,
        type: "default",
        animated: isSelected,
        style: {
          stroke: config.accentHex,
          strokeWidth: isSelected ? 3 : 1.75,
          opacity: isSelected ? 1.0 : 0.65,
        },
      };
    });
  }, [orderedScenarios, selectedScenarioType]);

  return (
    <div
      aria-label="Future Explorer Tree Canvas"
      className="space-y-4"
    >
      {/* 1. Accessible Trajectory Selector Tabs (Responsive / Keyboard Navigation) */}
      <div
        role="tablist"
        aria-label="Future Scenario Trajectories"
        className="flex items-center gap-2 p-1 rounded-xl bg-zinc-950/80 border border-zinc-800/80 overflow-x-auto print:hidden"
      >
        <span className="text-xs font-mono uppercase tracking-wider text-zinc-400 px-3 py-1 font-semibold whitespace-nowrap">
          Trajectories:
        </span>
        {orderedScenarios.map((scen) => {
          const config = getScenarioConfig(scen.scenario_type);
          const isSelected = selectedScenarioType === scen.scenario_type;
          const formattedProb = formatScenarioProbability(scen.probability);

          return (
            <button
              key={scen.scenario_type}
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-controls={`scenario-panel-${scen.scenario_type}`}
              onClick={() => onSelectScenario(scen.scenario_type)}
              className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                isSelected
                  ? `${config.activeBorderClass} ${config.badgeClass} text-white font-semibold shadow-sm`
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent"
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${config.dotClass}`} />
              <span>{config.label}</span>
              <span className="font-mono text-[11px] opacity-80">
                ({formattedProb})
              </span>
            </button>
          );
        })}
      </div>

      {/* 2. Interactive React Flow Canvas */}
      <div className="relative h-[390px] w-full rounded-xl border border-zinc-800 bg-zinc-950/90 shadow-inner overflow-hidden print:hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          proOptions={{ hideAttribution: true }}
          minZoom={0.5}
          maxZoom={1.5}
        >
          <Background color="#27272a" gap={20} size={1} />
          <Controls
            showInteractive={false}
            className="!bg-zinc-900 !border-zinc-800 !fill-zinc-300 [&>button]:!border-zinc-800 [&>button]:!bg-zinc-900 [&>button:hover]:!bg-zinc-800"
          />
        </ReactFlow>
      </div>

      {/* 3. Print-Friendly Static Tree Grid Fallback (Never clipped or blank on export) */}
      <div className="hidden print:block space-y-3 pt-2">
        <h4 className="text-xs font-mono uppercase tracking-wider text-black font-bold">
          Future Scenario Trajectories
        </h4>
        <div className="grid grid-cols-3 gap-3">
          {orderedScenarios.map((scen) => {
            const config = getScenarioConfig(scen.scenario_type);
            const prob = formatScenarioProbability(scen.probability);
            return (
              <div
                key={scen.scenario_type}
                className="border border-zinc-300 rounded-lg p-3 bg-zinc-50 space-y-1"
              >
                <div className="flex justify-between items-center text-xs font-bold font-mono">
                  <span>{config.label.toUpperCase()}</span>
                  <span>{prob}</span>
                </div>
                <div className="text-xs font-semibold text-black">{scen.name}</div>
                <div className="text-[11px] text-zinc-600 line-clamp-2">
                  {scen.narrative}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
