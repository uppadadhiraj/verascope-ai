import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ForceGraph2D, { type ForceGraphMethods, type NodeObject } from "react-force-graph-2d";
import { Network, RotateCcw } from "lucide-react";
import { Layout } from "@/components/Layout";
import { filesApi } from "@/api/endpoints";
import type { DependencyGraph } from "@/api/types";

const LANGUAGE_COLORS: Record<string, string> = {
  python: "#3776ab",
  javascript: "#f0db4f",
  typescript: "#3178c6",
  java: "#e76f00",
  c: "#5c6bc0",
  cpp: "#00599c",
  sql: "#8b5cf6",
  html: "#e34c26",
  css: "#563d7c",
};
const DEFAULT_COLOR = "#64748b";
const TEST_COLOR = "#22c55e";

interface GraphNode extends NodeObject {
  id: string;
  language: string | null;
  isTest: boolean;
  degree: number;
}

export function DependencyGraphPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const navigate = useNavigate();
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const fgRef = useRef<ForceGraphMethods<GraphNode> | undefined>(undefined);

  // ForceGraph2D can auto-detect its container size, but that detection is
  // unreliable inside a flex layout like this one (the container can still
  // report 0x0 on first measurement) -- measuring it ourselves and passing
  // explicit width/height is the robust fix, not a guess.
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        // Only update state on a real change (rounded to whole pixels).
        // Belt-and-suspenders alongside the min-h-0/min-w-0/overflow-hidden
        // fix above: this guarantees this component can never re-render
        // (and reset the canvas, dropping the current zoom/pan) in
        // response to its own sub-pixel measurement noise.
        setSize((prev) => {
          const w = Math.round(width);
          const h = Math.round(height);
          return prev.width === w && prev.height === h ? prev : { width: w, height: h };
        });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!repositoryId) return;
    filesApi.dependencyGraph(repositoryId).then(setGraph);
  }, [repositoryId]);

  const graphData = useMemo(() => {
    if (!graph) return { nodes: [] as GraphNode[], links: [] };
    return {
      nodes: graph.nodes.map(
        (n): GraphNode => ({
          id: n.id,
          language: n.language,
          isTest: n.is_test,
          degree: n.in_degree + n.out_degree,
        })
      ),
      links: graph.edges.map((e) => ({ source: e.source, target: e.target, relationship: e.relationship })),
    };
  }, [graph]);

  const neighbors = useMemo(() => {
    const map = new Map<string, Set<string>>();
    if (!graph) return map;
    for (const e of graph.edges) {
      if (!map.has(e.source)) map.set(e.source, new Set());
      if (!map.has(e.target)) map.set(e.target, new Set());
      map.get(e.source)!.add(e.target);
      map.get(e.target)!.add(e.source);
    }
    return map;
  }, [graph]);

  const isEmpty = graph !== null && graph.nodes.length === 0;

  return (
    <Layout>
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-surface-border px-6 py-3">
          <div>
            <h1 className="text-sm font-semibold text-slate-100">Dependency Graph</h1>
            <p className="text-xs text-slate-500">
              {graph
                ? `${graph.nodes.length} files, ${graph.edges.length} import relationships${graph.truncated ? " (truncated for display)" : ""} -- structural imports only, not a runtime call/data-flow trace.`
                : "Loading..."}
            </p>
          </div>
          <button className="btn-secondary" onClick={() => fgRef.current?.zoomToFit(400, 40)} disabled={!graph}>
            <RotateCcw size={14} /> Reset view
          </button>
        </div>

        {/* This container is ALWAYS mounted (never conditionally created by
            an early return) so the ResizeObserver above attaches once and
            keeps reporting real dimensions for the graph's whole lifetime.
            min-h-0/min-w-0 override flexbox's default min-height/min-width:
            auto -- without them, a flex-1 child can be forced to GROW to
            fit its content (the canvas, sized in pixels to match this very
            container), which re-fires the ResizeObserver, which resizes the
            canvas again -- a feedback loop that also resets the zoom/pan
            transform on every tick, which is what made zoom-based node
            resizing look broken. overflow-hidden closes the last escape
            hatch for content to affect this box's own size. */}
        <div ref={containerRef} className="relative flex-1 min-h-0 min-w-0 overflow-hidden">
          {isEmpty && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <Network size={28} className="text-slate-600" />
              <p className="text-sm text-slate-500">
                No resolvable import relationships were found between files in this repository.
              </p>
            </div>
          )}

          {graph && !isEmpty && size.width > 0 && size.height > 0 && (
            <ForceGraph2D
              ref={fgRef}
              width={size.width}
              height={size.height}
              graphData={graphData}
              backgroundColor="#0b0e14"
              nodeId="id"
              nodeLabel={(n) => `${n.id} (${(n as GraphNode).degree} connections)`}
              nodeVal={(n) => 2 + Math.sqrt((n as GraphNode).degree || 1)}
              nodeColor={(n) => {
                const node = n as GraphNode;
                if (selected && node.id !== selected && !neighbors.get(selected)?.has(node.id)) return "#2a3040";
                if (node.isTest) return TEST_COLOR;
                return (node.language && LANGUAGE_COLORS[node.language]) || DEFAULT_COLOR;
              }}
              linkColor={(l) => {
                if (!selected) return "rgba(148,163,184,0.25)";
                const src = typeof l.source === "object" ? (l.source as GraphNode).id : l.source;
                const tgt = typeof l.target === "object" ? (l.target as GraphNode).id : l.target;
                return src === selected || tgt === selected ? "rgba(99,102,241,0.9)" : "rgba(148,163,184,0.08)";
              }}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              linkWidth={1}
              enableZoomInteraction
              enablePanInteraction
              enableNodeDrag
              onNodeClick={(n) => {
                const node = n as GraphNode;
                setSelected((cur) => (cur === node.id ? null : node.id));
              }}
              onNodeRightClick={(n) => {
                navigate(`/repositories/${repositoryId}/explorer`, { state: { openPath: (n as GraphNode).id } });
              }}
              onBackgroundClick={() => setSelected(null)}
              cooldownTicks={100}
              onEngineStop={() => fgRef.current?.zoomToFit(400, 40)}
            />
          )}

          {selected && (
            <div className="card absolute bottom-4 left-4 max-w-sm p-3">
              <div className="mb-1 font-mono text-xs text-indigo-300">{selected}</div>
              <p className="text-xs text-slate-500">
                {neighbors.get(selected)?.size || 0} connected file(s). Left-click another node to inspect it,
                right-click any node to open it in Explorer, click empty space to clear selection.
              </p>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
