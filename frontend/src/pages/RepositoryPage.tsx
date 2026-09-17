import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { StatusBadge } from "@/components/StatusBadge";
import { repositoryApi } from "@/api/endpoints";
import type { Repository, RepositorySummary } from "@/api/types";

const STAGES: Array<Repository["status"]> = [
  "CLONING",
  "SCANNING",
  "PARSING",
  "EMBEDDING",
  "SUMMARIZING",
  "READY",
];

export function RepositoryPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [repo, setRepo] = useState<Repository | null>(null);
  const [summary, setSummary] = useState<RepositorySummary | null>(null);

  useEffect(() => {
    if (!repositoryId) return;
    let cancelled = false;

    async function poll() {
      const r = await repositoryApi.get(repositoryId!);
      if (cancelled) return;
      setRepo(r);
      if (r.status === "READY") {
        const s = await repositoryApi.summary(repositoryId!).catch(() => null);
        if (!cancelled) setSummary(s);
      }
    }

    poll();
    const interval = setInterval(() => {
      if (repo?.status !== "READY" && repo?.status !== "FAILED") poll();
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryId, repo?.status]);

  if (!repo) {
    return (
      <Layout>
        <div className="p-8 text-sm text-slate-500">Loading...</div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="mx-auto max-w-4xl px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-100">{repo.name}</h1>
            <p className="text-sm text-slate-500">{repo.source_url || "Uploaded via ZIP"}</p>
          </div>
          <StatusBadge status={repo.status} />
        </div>

        {repo.status !== "READY" && repo.status !== "FAILED" && (
          <div className="card mb-6 p-4">
            <p className="mb-3 text-sm text-slate-400">{repo.status_detail}</p>
            <div className="flex gap-1">
              {STAGES.map((stage) => {
                const currentIdx = STAGES.indexOf(repo.status);
                const stageIdx = STAGES.indexOf(stage);
                const done = stageIdx < currentIdx || repo.status === "READY";
                const active = stageIdx === currentIdx;
                return (
                  <div
                    key={stage}
                    className={`h-1.5 flex-1 rounded-full ${
                      done ? "bg-emerald-500" : active ? "bg-amber-500" : "bg-surface-border"
                    }`}
                  />
                );
              })}
            </div>
          </div>
        )}

        {repo.status === "FAILED" && (
          <div className="card mb-6 border-red-500/30 p-4">
            <p className="text-sm font-medium text-red-400">Ingestion failed</p>
            <p className="mt-1 text-sm text-slate-400">{repo.error_message}</p>
          </div>
        )}

        {summary && (
          <div className="space-y-4">
            {summary.purpose && (
              <div className="card p-4">
                <h2 className="mb-1 text-sm font-semibold text-slate-200">Purpose</h2>
                <p className="text-sm text-slate-400">{summary.purpose}</p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <InfoCard label="Languages" values={summary.languages} />
              <InfoCard label="Frameworks" values={summary.frameworks} />
              <InfoCard label="Entry points" values={summary.entry_points} mono />
              <InfoCard label="Database" values={summary.database ? [summary.database] : []} />
              <InfoCard label="Authentication" values={summary.authentication ? [summary.authentication] : []} />
              <InfoCard label="Test framework" values={summary.test_framework ? [summary.test_framework] : []} />
            </div>

            {summary.api_entry_points.length > 0 && (
              <div className="card p-4">
                <h2 className="mb-2 text-sm font-semibold text-slate-200">API Endpoints</h2>
                <ul className="space-y-1 font-mono text-xs text-slate-400">
                  {summary.api_entry_points.slice(0, 20).map((ep) => (
                    <li key={ep}>{ep}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <EvidenceCard title="Facts" items={summary.facts} tone="text-emerald-400" />
              <EvidenceCard title="Inferences" items={summary.inferences} tone="text-amber-400" />
              <EvidenceCard title="Uncertain" items={summary.uncertain} tone="text-slate-500" />
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}

function InfoCard({ label, values, mono }: { label: string; values: string[]; mono?: boolean }) {
  if (!values || values.length === 0) return null;
  return (
    <div className="card p-3">
      <div className="mb-1 text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className={`text-sm text-slate-300 ${mono ? "font-mono text-xs" : ""}`}>{values.join(", ")}</div>
    </div>
  );
}

function EvidenceCard({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="card p-3">
      <div className={`mb-2 text-xs font-semibold uppercase ${tone}`}>{title}</div>
      <ul className="space-y-1.5 text-xs text-slate-400">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
