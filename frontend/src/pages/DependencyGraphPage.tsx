import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ForceGraph2D, { type ForceGraphMethods, type NodeObject } from "react-force-graph-2d";
import { Network, RotateCcw, Search, X } from "lucide-react";
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
const HIDDEN_COLOR = "#1c212e";

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
  const [search, setSearch] = useState("");
  const [hiddenLanguages, setHiddenLanguages] = useState<Set<string>>(new Set());
  const [testsHidden, setTestsHidden] = useState(false);
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

  // Languages actually present (excluding test files, which always render
  // as TEST_COLOR regardless of language) -- drives the legend and its
  // filter toggles, so a legend entry never appears for a color nothing on
  // screen actually uses.
  const languagesPresent = useMemo(() => {
    if (!graph) return [];
    const set = new Set<string>();
    for (const n of graph.nodes) {
      if (n.language && !n.is_test) set.add(n.language);
    }
    return [...set].sort();
  }, [graph]);

  const hasTestFiles = useMemo(() => graph?.nodes.some((n) => n.is_test) ?? false, [graph]);

  const toggleLanguage = (lang: string) => {
    setHiddenLanguages((prev) => {
      const next = new Set(prev);
      if (next.has(lang)) next.delete(lang);
      else next.add(lang);
      return next;
    });
  };

  const graphData = useMemo(() => {
    if (!graph) return { nodes: [] as GraphNode[], links: [] };
    const visible = new Set<string>();
    const nodes: GraphNode[] = [];
    for (const n of graph.nodes) {
      if (n.is_test && testsHidden) continue;
      if (!n.is_test && n.language && hiddenLanguages.has(n.language)) continue;
      visible.add(n.id);
      nodes.push({
        id: n.id,
        language: n.language,
        isTest: n.is_test,
        degree: n.in_degree + n.out_degree,
      });
    }
    const links = graph.edges
      .filter((e) => visible.has(e.source) && visible.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, relationship: e.relationship }));
    return { nodes, links };
  }, [graph, hiddenLanguages, testsHidden]);

  // Directional adjacency (who THIS file imports vs who imports THIS file)
  // -- kept separate from the undirected `neighbors` map below because
  // "imports" and "imported by" answer genuinely different questions about
  // a file, and collapsing them into one count threw that distinction away.
  const directedNeighbors = useMemo(() => {
    const map = new Map<string, { in: Set<string>; out: Set<string> }>();
    if (!graph) return map;
    const touch = (id: string) => {
      if (!map.has(id)) map.set(id, { in: new Set(), out: new Set() });
      return map.get(id)!;
    };
    for (const e of graph.edges) {
      touch(e.source).out.add(e.target);
      touch(e.target).in.add(e.source);
    }
    return map;
  }, [graph]);

  const neighbors = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const [id, dirs] of directedNeighbors) {
      map.set(id, new Set([...dirs.in, ...dirs.out]));
    }
    return map;
  }, [directedNeighbors]);

  // The files with the most total connections -- a quick answer to "what's
  // the central/riskiest file in this codebase" without having to eyeball
  // node sizes in a dense force layout.
  const topFiles = useMemo(() => {
    if (!graph) return [];
    return [...graph.nodes]
      .map((n) => ({ id: n.id, inDegree: n.in_degree, outDegree: n.out_degree, degree: n.in_degree + n.out_degree }))
      .filter((n) => n.degree > 0)
      .sort((a, b) => b.degree - a.degree)
      .slice(0, 8);
  }, [graph]);

  const searchMatches = useMemo(() => {
    if (!search.trim() || !graph) return [];
    const q = search.trim().toLowerCase();
    return graph.nodes.filter((n) => n.id.toLowerCase().includes(q)).slice(0, 8);
  }, [search, graph]);

  const jumpToNode = (id: string) => {
    setSelected(id);
    setSearch("");
    const node = graphData.nodes.find((n) => n.id === id);
    if (node && typeof node.x === "number" && typeof node.y === "number") {
      fgRef.current?.centerAt(node.x, node.y, 600);
      fgRef.current?.zoom(5, 600);
    }
  };

  const rawIsEmpty = graph !== null && graph.nodes.length === 0;
  const filteredToEmpty = graph !== null && graph.nodes.length > 0 && graphData.nodes.length === 0;
  const hasActiveFilter = hiddenLanguages.size > 0 || testsHidden;

  return (
    <Layout>
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between gap-4 border-b border-surface-border px-6 py-3">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-slate-100">Dependency Graph</h1>
            <p className="text-xs text-slate-500">
              {graph
                ? `${graph.nodes.length} files, ${graph.edges.length} import relationships${graph.truncated ? " (truncated for display)" : ""} -- structural imports only, not a runtime call/data-flow trace.`
                : "Loading..."}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="relative">
              <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Find a file..."
                disabled={!graph}
                className="w-48 rounded-md border border-surface-border bg-surface-raised py-1.5 pl-8 pr-7 text-xs text-slate-200 placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  <X size={13} />
                </button>
              )}
              {searchMatches.length > 0 && (
                <div className="absolute right-0 top-full z-20 mt-1 w-72 rounded-md border border-surface-border bg-surface-raised shadow-lg">
                  {searchMatches.map((n) => (
                    <button
                      key={n.id}
                      onClick={() => jumpToNode(n.id)}
                      className="block w-full truncate px-3 py-1.5 text-left font-mono text-[11px] text-slate-300 hover:bg-surface-border"
                    >
                      {n.id}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="btn-secondary" onClick={() => fgRef.current?.zoomToFit(400, 40)} disabled={!graph}>
              <RotateCcw size={14} /> Reset view
            </button>
          </div>
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
          {rawIsEmpty && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <Network size={28} className="text-slate-600" />
              <p className="text-sm text-slate-500">
                No resolvable import relationships were found between files in this repository.
              </p>
            </div>
          )}

          {filteredToEmpty && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <Network size={28} className="text-slate-600" />
              <p className="text-sm text-slate-500">All files are hidden by the current legend filter.</p>
              <button
                className="btn-secondary mt-1"
                onClick={() => {
                  setHiddenLanguages(new Set());
                  setTestsHidden(false);
                }}
              >
                Clear filter
              </button>
            </div>
          )}

          {graph && !rawIsEmpty && !filteredToEmpty && size.width > 0 && size.height > 0 && (
            <ForceGraph2D
              ref={fgRef}
              width={size.width}
              height={size.height}
              graphData={graphData}
              backgroundColor="#0b0e14"
              nodeId="id"
              nodeLabel={(n) => {
                const node = n as GraphNode;
                const dirs = directedNeighbors.get(node.id);
                return `${node.id} -- imports ${dirs?.out.size ?? 0}, imported by ${dirs?.in.size ?? 0}`;
              }}
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

          {(languagesPresent.length > 0 || hasTestFiles) && (
            <div className="card absolute right-4 top-4 max-w-[13rem] p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Legend</span>
                {hasActiveFilter && (
                  <button
                    onClick={() => {
                      setHiddenLanguages(new Set());
                      setTestsHidden(false);
                    }}
                    className="text-[10px] text-indigo-400 hover:text-indigo-300"
                  >
                    Reset
                  </button>
                )}
              </div>
              <div className="flex flex-col gap-1">
                {languagesPresent.map((lang) => {
                  const hidden = hiddenLanguages.has(lang);
                  return (
                    <button
                      key={lang}
                      onClick={() => toggleLanguage(lang)}
                      className="flex items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-surface-border"
                      title={hidden ? `Show ${lang} files` : `Hide ${lang} files`}
                    >
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: hidden ? HIDDEN_COLOR : LANGUAGE_COLORS[lang] || DEFAULT_COLOR }}
                      />
                      <span className={`truncate text-[11px] ${hidden ? "text-slate-600 line-through" : "text-slate-300"}`}>
                        {lang}
                      </span>
                    </button>
                  );
                })}
                {hasTestFiles && (
                  <button
                    onClick={() => setTestsHidden((v) => !v)}
                    className="flex items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-surface-border"
                    title={testsHidden ? "Show test files" : "Hide test files"}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: testsHidden ? HIDDEN_COLOR : TEST_COLOR }}
                    />
                    <span className={`truncate text-[11px] ${testsHidden ? "text-slate-600 line-through" : "text-slate-300"}`}>
                      test files
                    </span>
                  </button>
                )}
              </div>
            </div>
          )}

          {topFiles.length > 0 && (
            <div className="card absolute left-4 top-4 max-w-[16rem] p-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Most connected files
              </div>
              <div className="flex flex-col gap-1">
                {topFiles.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => jumpToNode(f.id)}
                    className="flex items-center justify-between gap-2 rounded px-1 py-0.5 text-left hover:bg-surface-border"
                    title={f.id}
                  >
                    <span className="truncate font-mono text-[11px] text-slate-300">{f.id.split("/").pop()}</span>
                    <span className="shrink-0 rounded bg-surface-border px-1.5 py-0.5 text-[10px] text-slate-400">
                      {f.degree}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {selected && (
            <div className="card absolute bottom-4 left-4 max-w-sm p-3">
              <div className="mb-2 font-mono text-xs text-indigo-300">{selected}</div>
              <div className="flex flex-col gap-2 text-xs text-slate-400">
                <div>
                  <span className="text-slate-500">Imports ({directedNeighbors.get(selected)?.out.size ?? 0}):</span>
                  {(directedNeighbors.get(selected)?.out.size ?? 0) === 0 ? (
                    <span className="ml-1 text-slate-600">none</span>
                  ) : (
                    <div className="mt-1 flex flex-col gap-0.5">
                      {[...(directedNeighbors.get(selected)?.out ?? [])].slice(0, 5).map((id) => (
                        <button
                          key={id}
                          onClick={() => jumpToNode(id)}
                          className="truncate rounded px-1 py-0.5 text-left font-mono text-[11px] text-slate-400 hover:bg-surface-border hover:text-slate-200"
                        >
                          {id}
                        </button>
                      ))}
                      {(directedNeighbors.get(selected)?.out.size ?? 0) > 5 && (
                        <span className="px-1 text-[10px] text-slate-600">
                          +{(directedNeighbors.get(selected)?.out.size ?? 0) - 5} more
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div>
                  <span className="text-slate-500">Imported by ({directedNeighbors.get(selected)?.in.size ?? 0}):</span>
                  {(directedNeighbors.get(selected)?.in.size ?? 0) === 0 ? (
                    <span className="ml-1 text-slate-600">none</span>
                  ) : (
                    <div className="mt-1 flex flex-col gap-0.5">
                      {[...(directedNeighbors.get(selected)?.in ?? [])].slice(0, 5).map((id) => (
                        <button
                          key={id}
                          onClick={() => jumpToNode(id)}
                          className="truncate rounded px-1 py-0.5 text-left font-mono text-[11px] text-slate-400 hover:bg-surface-border hover:text-slate-200"
                        >
                          {id}
                        </button>
                      ))}
                      {(directedNeighbors.get(selected)?.in.size ?? 0) > 5 && (
                        <span className="px-1 text-[10px] text-slate-600">
                          +{(directedNeighbors.get(selected)?.in.size ?? 0) - 5} more
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
              <p className="mt-2 text-[10px] text-slate-600">
                Right-click any node to open it in Explorer, click empty space to clear selection.
              </p>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
