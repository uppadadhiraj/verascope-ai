import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Bot, ChevronDown, ChevronRight } from "lucide-react";
import { Layout } from "@/components/Layout";
import { StatusBadge } from "@/components/StatusBadge";
import { agentRunsApi } from "@/api/endpoints";
import type { AgentRun } from "@/api/types";

export function AgentHistoryPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [expanded, setExpanded] = useState<Record<string, AgentRun>>({});

  useEffect(() => {
    if (!repositoryId) return;
    agentRunsApi.list(repositoryId).then(setRuns);
    const interval = setInterval(() => agentRunsApi.list(repositoryId).then(setRuns), 5000);
    return () => clearInterval(interval);
  }, [repositoryId]);

  async function toggle(run: AgentRun) {
    if (expanded[run.id]) {
      setExpanded((e) => {
        const next = { ...e };
        delete next[run.id];
        return next;
      });
      return;
    }
    const detail = await agentRunsApi.get(repositoryId!, run.id);
    setExpanded((e) => ({ ...e, [run.id]: detail }));
  }

  return (
    <Layout>
      <div className="mx-auto max-w-4xl px-8 py-8">
        <h1 className="mb-1 text-xl font-semibold text-slate-100">Agent History</h1>
        <p className="mb-6 text-sm text-slate-500">Every agent run, tool call, and token usage -- fully observable.</p>

        <div className="space-y-2">
          {runs.map((run) => {
            const isOpen = !!expanded[run.id];
            const detail = expanded[run.id];
            return (
              <div key={run.id} className="card overflow-hidden">
                <button
                  onClick={() => toggle(run)}
                  className="flex w-full items-center justify-between p-3.5 text-left hover:bg-surface-border/40"
                >
                  <div className="flex items-center gap-2.5">
                    {isOpen ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />}
                    <Bot size={15} className="text-indigo-400" />
                    <span className="text-sm font-medium capitalize text-slate-200">{run.agent_name} agent</span>
                    <span className="text-xs text-slate-600">{new Date(run.started_at).toLocaleString()}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span>{run.total_tokens} tokens</span>
                    {run.latency_ms && <span>{run.latency_ms}ms</span>}
                    <StatusBadge status={run.status} />
                  </div>
                </button>
                {isOpen && detail && (
                  <div className="border-t border-surface-border p-3.5">
                    {detail.error_message && <p className="mb-2 text-sm text-red-400">{detail.error_message}</p>}
                    {detail.output_summary && <p className="mb-3 text-sm text-slate-300">{detail.output_summary}</p>}
                    <div className="space-y-1.5">
                      {(detail.tool_calls || []).map((tc) => (
                        <div key={tc.id} className="rounded border border-surface-border p-2 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-indigo-300">{tc.tool_name}</span>
                            <span className={tc.status === "error" ? "text-red-400" : "text-slate-500"}>
                              {tc.duration_ms}ms
                            </span>
                          </div>
                          {tc.arguments && (
                            <pre className="mt-1 overflow-x-auto text-slate-500">
                              {JSON.stringify(tc.arguments).slice(0, 200)}
                            </pre>
                          )}
                        </div>
                      ))}
                      {(!detail.tool_calls || detail.tool_calls.length === 0) && (
                        <p className="text-xs text-slate-600">No tool calls.</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {runs.length === 0 && <p className="text-sm text-slate-600">No agent runs yet.</p>}
        </div>
      </div>
    </Layout>
  );
}
