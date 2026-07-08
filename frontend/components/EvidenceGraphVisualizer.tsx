"use client";

import { GitBranch, Network, RadioTower } from "lucide-react";
import { useMemo, useState } from "react";

type RecordValue = Record<string, unknown>;

const nodeStyles: Record<string, { fill: string; stroke: string; text: string; radius: number }> = {
  claim: { fill: "#0f766e", stroke: "#5eead4", text: "Claim", radius: 32 },
  evidence: { fill: "#1d4ed8", stroke: "#93c5fd", text: "Evidence", radius: 24 },
  source: { fill: "#7c2d12", stroke: "#fdba74", text: "Source", radius: 22 },
  verdict: { fill: "#166534", stroke: "#86efac", text: "Verdict", radius: 26 },
  independence_cluster: { fill: "#6d28d9", stroke: "#c4b5fd", text: "Cluster", radius: 22 },
};

function isRecord(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(source: RecordValue, keys: string[], fallback: string): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return fallback;
}

function shorten(value: string, max = 36): string {
  return value.length > max ? `${value.slice(0, max - 1)}...` : value;
}

function getNestedValue(source: RecordValue, path: string): string | null {
  const parts = path.split(".");
  let value: unknown = source;

  for (const part of parts) {
    if (!isRecord(value)) return null;
    value = value[part];
  }

  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return null;
}

function describeNode(node: { type: string; label: string; data: RecordValue }) {
  const detailsByType: Record<string, string[]> = {
    claim: ["data.claim_text", "data.subject", "data.predicate", "data.object"],
    evidence: ["data.title", "data.url", "data.evidence_text"],
    source: ["data.source_id", "data.url", "data.reliability"],
    verdict: ["label", "data.reason", "data.confidence"],
    independence_cluster: ["data.cluster", "data.reason", "data.corroboration_discount"],
  };

  const detail = (detailsByType[node.type] ?? ["label"])
    .map((path) => (path === "label" ? node.label : getNestedValue(node.data, path)))
    .find((value) => value && value.trim());

  return detail ?? node.label;
}

function parseGraph(graph: RecordValue | null) {
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes.filter(isRecord) : [];
  const rawEdges = Array.isArray(graph?.edges) ? graph.edges.filter(isRecord) : [];

  const nodes = rawNodes.slice(0, 28).map((node, index) => {
    const type = readString(node, ["node_type", "type"], "evidence");
    const style = nodeStyles[type] ?? nodeStyles.evidence;
    return {
      id: readString(node, ["node_id", "id"], `node-${index}`),
      type,
      label: readString(node, ["label", "title", "name"], type),
      data: node,
      x: 0,
      y: 0,
      radius: style.radius,
    };
  });

  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = rawEdges
    .map((edge, index) => ({
      id: readString(edge, ["edge_id", "id"], `edge-${index}`),
      type: readString(edge, ["edge_type", "type"], "related"),
      label: readString(edge, ["label"], "related"),
      sourceId: readString(edge, ["source_node_id", "source", "from"], ""),
      targetId: readString(edge, ["target_node_id", "target", "to"], ""),
      data: edge,
    }))
    .filter((edge) => nodeIds.has(edge.sourceId) && nodeIds.has(edge.targetId))
    .slice(0, 42);

  const claims = nodes.filter((node) => node.type === "claim");
  const ordered = [
    ...claims,
    ...nodes.filter((node) => node.type === "verdict"),
    ...nodes.filter((node) => node.type === "evidence"),
    ...nodes.filter((node) => node.type === "source"),
    ...nodes.filter((node) => node.type === "independence_cluster"),
    ...nodes.filter((node) => !nodeStyles[node.type]),
  ];

  const centerX = 430;
  const centerY = 245;
  const ringRadius = ordered.length > 12 ? 185 : 160;

  ordered.forEach((node, index) => {
    if (node.type === "claim" && claims.length === 1) {
      node.x = centerX;
      node.y = centerY;
      return;
    }

    const angle = -Math.PI / 2 + (index / Math.max(ordered.length, 1)) * Math.PI * 2;
    const typeOffset = node.type === "source" ? 38 : node.type === "verdict" ? -38 : 0;
    const radius = node.type === "claim" ? 72 : ringRadius + typeOffset;
    node.x = centerX + Math.cos(angle) * radius;
    node.y = centerY + Math.sin(angle) * radius;
  });

  return { nodes: ordered, edges };
}

export function EvidenceGraphVisualizer({ graph }: { graph: RecordValue | null }) {
  const { nodes, edges } = useMemo(() => parseGraph(graph), [graph]);
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [activeEdgeId, setActiveEdgeId] = useState<string | null>(null);

  const activeNode = activeNodeId ? nodeById.get(activeNodeId) : null;
  const activeEdge = activeEdgeId ? edges.find((edge) => edge.id === activeEdgeId) : null;

  if (nodes.length === 0) {
    return (
      <div className="grid min-h-80 place-items-center border border-dashed border-slate-700 bg-slate-950/40 p-8 text-center">
        <div>
          <Network className="mx-auto h-10 w-10 text-slate-500" aria-hidden="true" />
          <p className="mt-4 text-sm font-medium text-slate-200">Graph will appear when evidence relationships are returned.</p>
          <p className="mt-2 text-sm leading-6 text-slate-500">Claims, verdicts, evidence, sources, and independence clusters render as linked nodes.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden border border-slate-800 bg-slate-950/50">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-100">
          <RadioTower className="h-4 w-4 text-cyan-300" aria-hidden="true" />
          Relationship Map
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <GitBranch className="h-4 w-4 text-amber-300" aria-hidden="true" />
          {nodes.length} nodes / {edges.length} links
        </div>
      </div>

      <div className="relative">
        <svg viewBox="0 0 860 500" role="img" aria-label="Evidence graph visualization" className="h-[340px] w-full md:h-[460px]">
          <defs>
            <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect width="860" height="500" fill="#020617" />
          <g opacity="0.26">
            {Array.from({ length: 9 }).map((_, index) => (
              <circle key={index} cx="430" cy="245" r={48 + index * 26} fill="none" stroke="#334155" strokeWidth="1" />
            ))}
          </g>
          <g>
            {edges.map((edge) => {
              const source = nodeById.get(edge.sourceId);
              const target = nodeById.get(edge.targetId);
              if (!source || !target) return null;
              const curve = source.x < target.x ? 42 : -42;
              const path = `M ${source.x} ${source.y} Q ${(source.x + target.x) / 2} ${(source.y + target.y) / 2 + curve} ${target.x} ${target.y}`;
              const isActive = activeEdgeId === edge.id;
              return (
                <path
                  key={edge.id}
                  d={path}
                  fill="none"
                  stroke={isActive ? "#fbbf24" : "#64748b"}
                  strokeOpacity={isActive ? "0.92" : "0.58"}
                  strokeWidth={isActive ? "4" : "2"}
                  className="cursor-help transition-all"
                  onMouseEnter={() => {
                    setActiveEdgeId(edge.id);
                    setActiveNodeId(null);
                  }}
                  onMouseLeave={() => setActiveEdgeId(null)}
                />
              );
            })}
          </g>
          <g>
            {nodes.map((node) => {
              const style = nodeStyles[node.type] ?? nodeStyles.evidence;
              const isActive = activeNodeId === node.id;
              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x} ${node.y})`}
                  className="cursor-help outline-none"
                  tabIndex={0}
                  onFocus={() => {
                    setActiveNodeId(node.id);
                    setActiveEdgeId(null);
                  }}
                  onBlur={() => setActiveNodeId(null)}
                  onMouseEnter={() => {
                    setActiveNodeId(node.id);
                    setActiveEdgeId(null);
                  }}
                  onMouseLeave={() => setActiveNodeId(null)}
                >
                  <circle r={node.radius + (isActive ? 14 : 8)} fill={style.stroke} opacity={isActive ? "0.18" : "0.08"} />
                  <circle r={node.radius} fill={style.fill} stroke={isActive ? "#ffffff" : style.stroke} strokeWidth={isActive ? "3" : "2"} filter="url(#nodeGlow)" />
                  <text y="4" textAnchor="middle" className="fill-white text-[10px] font-semibold uppercase">
                    {style.text}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="grid gap-3 border-t border-slate-800 p-4 md:grid-cols-[1fr_1.2fr]">
        <div className="flex flex-wrap gap-2">
          {Object.entries(nodeStyles).map(([type, style]) => (
            <span key={type} className="inline-flex items-center gap-2 border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
              <span className="h-2.5 w-2.5" style={{ backgroundColor: style.stroke }} />
              {style.text}
            </span>
          ))}
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="border border-cyan-300/20 bg-cyan-300/10 px-3 py-2 sm:col-span-2">
            {activeNode ? (
              <>
                <p className="text-xs uppercase text-cyan-200">{activeNode.type.replaceAll("_", " ")}</p>
                <p className="mt-1 text-sm font-medium text-white">{shorten(activeNode.label, 72)}</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">{shorten(describeNode(activeNode), 180)}</p>
              </>
            ) : activeEdge ? (
              <>
                <p className="text-xs uppercase text-amber-200">{activeEdge.type.replaceAll("_", " ")}</p>
                <p className="mt-1 text-sm font-medium text-white">{activeEdge.label}</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  {shorten(`${nodeById.get(activeEdge.sourceId)?.label ?? activeEdge.sourceId} -> ${nodeById.get(activeEdge.targetId)?.label ?? activeEdge.targetId}`, 180)}
                </p>
              </>
            ) : (
              <>
                <p className="text-xs uppercase text-slate-500">Hover a node or link</p>
                <p className="mt-1 text-sm text-slate-200">Inspect the claim, evidence, source, verdict, cluster, and stance relationships.</p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
