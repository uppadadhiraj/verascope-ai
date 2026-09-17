import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Upload, Github, FolderGit2 } from "lucide-react";
import { Layout } from "@/components/Layout";
import { StatusBadge } from "@/components/StatusBadge";
import { repositoryApi } from "@/api/endpoints";
import { apiErrorMessage } from "@/api/client";
import type { Repository } from "@/api/types";

export function DashboardPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const navigate = useNavigate();

  async function refresh() {
    const data = await repositoryApi.list();
    setRepos(data);
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false));
    const interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Layout>
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-100">Repositories</h1>
            <p className="text-sm text-slate-500">Connect a repository to start analyzing, chatting, and debugging.</p>
          </div>
          <button className="btn-primary" onClick={() => setShowAdd((s) => !s)}>
            <Plus size={16} /> Add repository
          </button>
        </div>

        {showAdd && <AddRepositoryPanel onAdded={() => { setShowAdd(false); refresh(); }} />}

        {loading ? (
          <p className="text-sm text-slate-500">Loading...</p>
        ) : repos.length === 0 ? (
          <div className="card flex flex-col items-center justify-center gap-2 p-12 text-center">
            <FolderGit2 className="text-slate-600" size={32} />
            <p className="text-sm text-slate-500">No repositories yet. Add one to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {repos.map((repo) => (
              <button
                key={repo.id}
                onClick={() => navigate(`/repositories/${repo.id}`)}
                className="card p-4 text-left transition-colors hover:border-indigo-500/50"
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <span className="truncate font-medium text-slate-100">{repo.name}</span>
                  <StatusBadge status={repo.status} />
                </div>
                <p className="truncate text-xs text-slate-500">{repo.status_detail || repo.source_url || "ZIP upload"}</p>
                {repo.error_message && <p className="mt-1 truncate text-xs text-red-400">{repo.error_message}</p>}
                <div className="mt-3 flex gap-3 text-xs text-slate-500">
                  <span>{repo.file_count} files</span>
                  {repo.frameworks && repo.frameworks.length > 0 && <span>{repo.frameworks.join(", ")}</span>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}

function AddRepositoryPanel({ onAdded }: { onAdded: () => void }) {
  const [mode, setMode] = useState<"github" | "zip">("github");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleGithubSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await repositoryApi.createFromGithub(repoUrl, undefined, branch || undefined);
      onAdded();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      await repositoryApi.uploadZip(file);
      onAdded();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mb-6 p-4">
      <div className="mb-3 flex gap-2">
        <button
          className={`btn ${mode === "github" ? "bg-indigo-600 text-white" : "bg-surface-border text-slate-300"}`}
          onClick={() => setMode("github")}
        >
          <Github size={14} /> GitHub URL
        </button>
        <button
          className={`btn ${mode === "zip" ? "bg-indigo-600 text-white" : "bg-surface-border text-slate-300"}`}
          onClick={() => setMode("zip")}
        >
          <Upload size={14} /> Upload ZIP
        </button>
      </div>

      {mode === "github" ? (
        <form onSubmit={handleGithubSubmit} className="flex flex-col gap-2 sm:flex-row">
          <input
            className="input"
            placeholder="https://github.com/owner/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            required
          />
          <input
            className="input sm:w-40"
            placeholder="branch (optional)"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
          <button className="btn-primary whitespace-nowrap" type="submit" disabled={busy}>
            {busy ? "Adding..." : "Add"}
          </button>
        </form>
      ) : (
        <div>
          <input ref={fileInputRef} type="file" accept=".zip" className="hidden" onChange={handleFileChange} />
          <button className="btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={busy}>
            <Upload size={14} /> {busy ? "Uploading..." : "Choose .zip file"}
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </div>
  );
}
