import { useMemo } from "react";
import type { LineageResponse } from "../api/types";

const LAYER_COLORS: Record<string, string> = {
  source: "#64748b",
  staging: "#10b981",
  dimension: "#8b5cf6",
  fact: "#f59e0b",
  mart: "#ec4899",
  other: "#3b82f6",
};

const COLUMN_WIDTH = 220;
const ROW_HEIGHT = 56;
const NODE_WIDTH = 180;
const NODE_HEIGHT = 36;
const PADDING = 24;

interface PositionedNode {
  name: string;
  layer: string;
  depth: number;
  row: number;
  x: number;
  y: number;
}

function layoutGraph(lineage: LineageResponse) {
  const nodeNames = Object.keys(lineage.nodes);
  const allNames = new Set<string>(nodeNames);
  for (const info of Object.values(lineage.nodes)) {
    for (const parent of info.parents) {
      allNames.add(parent);
    }
  }

  const depthCache = new Map<string, number>();
  const visiting = new Set<string>();

  function depthOf(name: string): number {
    if (depthCache.has(name)) return depthCache.get(name)!;
    const info = lineage.nodes[name];
    if (!info || info.parents.length === 0 || visiting.has(name)) {
      depthCache.set(name, 0);
      return 0;
    }
    visiting.add(name);
    const maxParentDepth = Math.max(...info.parents.map((p) => depthOf(p)));
    visiting.delete(name);
    const depth = maxParentDepth + 1;
    depthCache.set(name, depth);
    return depth;
  }

  const columns = new Map<number, string[]>();
  for (const name of allNames) {
    const depth = depthOf(name);
    if (!columns.has(depth)) columns.set(depth, []);
    columns.get(depth)!.push(name);
  }

  const positioned: PositionedNode[] = [];
  for (const [depth, names] of columns) {
    names.sort();
    names.forEach((name, row) => {
      const layer = lineage.nodes[name]?.layer ?? "source";
      positioned.push({
        name,
        layer,
        depth,
        row,
        x: PADDING + depth * COLUMN_WIDTH,
        y: PADDING + row * ROW_HEIGHT,
      });
    });
  }

  const maxDepth = Math.max(0, ...positioned.map((n) => n.depth));
  const maxRows = Math.max(1, ...Array.from(columns.values()).map((names) => names.length));

  const edges: { from: PositionedNode; to: PositionedNode }[] = [];
  const byName = new Map(positioned.map((n) => [n.name, n]));
  for (const [name, info] of Object.entries(lineage.nodes)) {
    const to = byName.get(name);
    if (!to) continue;
    for (const parent of info.parents) {
      const from = byName.get(parent);
      if (from) edges.push({ from, to });
    }
  }

  return {
    positioned,
    edges,
    width: PADDING * 2 + (maxDepth + 1) * COLUMN_WIDTH,
    height: PADDING * 2 + maxRows * ROW_HEIGHT,
  };
}

export default function LineageGraph({ lineage }: { lineage: LineageResponse }) {
  const { positioned, edges, width, height } = useMemo(() => layoutGraph(lineage), [lineage]);

  return (
    <div className="table-scroll">
      <svg width={Math.max(width, 400)} height={Math.max(height, 200)} style={{ minWidth: "100%" }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
          </marker>
        </defs>

        {edges.map((edge, idx) => {
          const x1 = edge.from.x + NODE_WIDTH;
          const y1 = edge.from.y + NODE_HEIGHT / 2;
          const x2 = edge.to.x;
          const y2 = edge.to.y + NODE_HEIGHT / 2;
          const midX = (x1 + x2) / 2;
          return (
            <path
              key={idx}
              d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke="#475569"
              strokeWidth={1.5}
              markerEnd="url(#arrow)"
            />
          );
        })}

        {positioned.map((node) => (
          <g key={node.name} transform={`translate(${node.x}, ${node.y})`}>
            <rect
              width={NODE_WIDTH}
              height={NODE_HEIGHT}
              rx={8}
              fill="#0f172a"
              stroke={LAYER_COLORS[node.layer] ?? LAYER_COLORS.other}
              strokeWidth={2}
            />
            <text x={10} y={NODE_HEIGHT / 2 + 4} fill="#f8fafc" fontSize={11.5}>
              {node.name.length > 22 ? `${node.name.slice(0, 20)}…` : node.name}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
