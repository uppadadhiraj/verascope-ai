import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { Search } from "lucide-react";
import { Layout } from "@/components/Layout";
import { FileTree } from "@/components/FileTree";
import { CodeViewer } from "@/components/CodeViewer";
import { filesApi } from "@/api/endpoints";
import type { CodeSearchResult, FileContent, FileTreeNode, SymbolRead } from "@/api/types";

export function ExplorerPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const location = useLocation();
  const [tree, setTree] = useState<FileTreeNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<FileContent | null>(null);
  const [symbols, setSymbols] = useState<SymbolRead[]>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CodeSearchResult[] | null>(null);
  const [highlight, setHighlight] = useState<{ start: number; end: number } | undefined>();

  useEffect(() => {
    if (!repositoryId) return;
    filesApi.tree(repositoryId).then(setTree);
  }, [repositoryId]);

  useEffect(() => {
    const openPath = (location.state as { openPath?: string } | null)?.openPath;
    if (openPath) openFile(openPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  async function openFile(path: string, range?: { start: number; end: number }) {
    if (!repositoryId) return;
    setSelectedPath(path);
    setHighlight(range);
    const [content, syms] = await Promise.all([
      filesApi.content(repositoryId, path),
      filesApi.symbols(repositoryId, path),
    ]);
    setFileContent(content);
    setSymbols(syms);
  }

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!repositoryId || !query.trim()) return;
    const results = await filesApi.searchCode(repositoryId, query);
    setSearchResults(results as CodeSearchResult[]);
  }

  return (
    <Layout>
      <div className="flex h-full">
        <div className="flex w-64 flex-shrink-0 flex-col border-r border-surface-border">
          <form onSubmit={runSearch} className="border-b border-surface-border p-2">
            <div className="relative">
              <Search size={14} className="absolute left-2 top-2.5 text-slate-500" />
              <input
                className="input pl-7 text-xs"
                placeholder="Semantic search..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
          </form>
          <div className="flex-1 overflow-y-auto">
            {searchResults ? (
              <div className="p-2">
                <button className="mb-2 text-xs text-indigo-400 hover:underline" onClick={() => setSearchResults(null)}>
                  ← back to tree
                </button>
                {searchResults.map((r, i) => (
                  <button
                    key={i}
                    onClick={() => openFile(r.file_path, { start: r.start_line, end: r.end_line })}
                    className="mb-2 block w-full rounded border border-surface-border p-2 text-left hover:border-indigo-500/50"
                  >
                    <div className="truncate font-mono text-xs text-indigo-300">{r.file_path}</div>
                    <div className="text-xs text-slate-500">
                      {r.symbol || `L${r.start_line}-${r.end_line}`} · {(r.score * 100).toFixed(0)}%
                    </div>
                  </button>
                ))}
                {searchResults.length === 0 && <p className="p-2 text-xs text-slate-500">No results.</p>}
              </div>
            ) : (
              <FileTree nodes={tree} onSelect={(p) => openFile(p)} selectedPath={selectedPath} />
            )}
          </div>
        </div>

        <div className="flex flex-1 flex-col overflow-hidden">
          {fileContent ? (
            <>
              <div className="flex items-center justify-between border-b border-surface-border px-4 py-2">
                <span className="font-mono text-xs text-slate-400">{fileContent.path}</span>
                <span className="text-xs text-slate-600">{fileContent.line_count} lines</span>
              </div>
              <div className="flex flex-1 overflow-hidden">
                <div className="flex-1 overflow-auto">
                  <CodeViewer content={fileContent.content} language={fileContent.language} highlightRange={highlight} />
                </div>
                {symbols.length > 0 && (
                  <div className="w-56 flex-shrink-0 overflow-y-auto border-l border-surface-border p-3">
                    <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Symbols</div>
                    <div className="space-y-1">
                      {symbols.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setHighlight({ start: s.start_line, end: s.end_line })}
                          className="block w-full truncate rounded px-1.5 py-1 text-left text-xs text-slate-400 hover:bg-surface-border"
                        >
                          <span className="mr-1 text-slate-600">{s.symbol_type}</span>
                          {s.name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-600">
              Select a file to view its contents
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
