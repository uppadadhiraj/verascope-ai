import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Bug, Search } from "lucide-react";
import { Layout } from "@/components/Layout";
import { StatusBadge } from "@/components/StatusBadge";
import { taskApi } from "@/api/endpoints";
import { apiErrorMessage } from "@/api/client";
import type { Task } from "@/api/types";

export function DebugPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showForm, setShowForm] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!repositoryId) return;
    taskApi.list(repositoryId).then((t) => setTasks(t.filter((x) => x.task_type === "DEBUG")));
  }, [repositoryId]);

  return (
    <Layout>
      <div className="mx-auto max-w-3xl px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-100">Debugging</h1>
            <p className="text-sm text-slate-500">
              Describe a bug and Verascope will investigate, propose a fix, and walk it through review and
              approval before touching your repository.
            </p>
          </div>
          <button className="btn-primary whitespace-nowrap" onClick={() => setShowForm((s) => !s)}>
            <Plus size={16} /> New investigation
          </button>
        </div>

        {showForm && repositoryId && (
          <NewInvestigationForm
            repositoryId={repositoryId}
            onCreated={(task) => navigate(`/repositories/${repositoryId}/debug/${task.id}`)}
          />
        )}

        <div className="space-y-2">
          {tasks.map((task) => (
            <button
              key={task.id}
              onClick={() => navigate(`/repositories/${repositoryId}/debug/${task.id}`)}
              className="card flex w-full items-center justify-between p-3.5 text-left hover:border-indigo-500/50"
            >
              <div className="flex items-center gap-2.5 overflow-hidden">
                <Bug size={15} className="flex-shrink-0 text-slate-500" />
                <span className="truncate text-sm text-slate-200">{task.title}</span>
              </div>
              <StatusBadge status={task.status} />
            </button>
          ))}
          {tasks.length === 0 && !showForm && (
            <div className="card flex flex-col items-center gap-2 p-12 text-center">
              <Search size={28} className="text-slate-600" />
              <p className="text-sm text-slate-300">This works from a specific problem, not a general scan.</p>
              <p className="max-w-md text-xs text-slate-500">
                Unlike the Security page (which proactively scans for known-risky patterns), the
                Debugger Agent investigates a bug <em>you describe</em> -- an error message, an
                unexpected status code, a stack trace, or just "X should do Y but does Z". Click
                "New investigation" and tell it what's actually wrong; it will search the repository,
                trace the relevant code, and report a root cause with evidence (or say plainly that
                the evidence was insufficient, rather than guessing).
              </p>
              <button className="btn-primary mt-2" onClick={() => setShowForm(true)}>
                <Plus size={16} /> New investigation
              </button>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}

function NewInvestigationForm({ repositoryId, onCreated }: { repositoryId: string; onCreated: (task: Task) => void }) {
  const [description, setDescription] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [stackTrace, setStackTrace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const task = await taskApi.startDebug(
        repositoryId,
        description,
        errorMessage || undefined,
        stackTrace || undefined
      );
      onCreated(task);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-6 space-y-3 p-4">
      <div>
        <label className="mb-1 block text-xs text-slate-400">What's wrong?</label>
        <textarea
          className="input min-h-[70px] resize-none"
          placeholder="Invalid JWT tokens are causing 500 errors instead of 401."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-400">Error message (optional)</label>
        <input className="input" value={errorMessage} onChange={(e) => setErrorMessage(e.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-400">Stack trace (optional)</label>
        <textarea
          className="input min-h-[60px] resize-none font-mono text-xs"
          value={stackTrace}
          onChange={(e) => setStackTrace(e.target.value)}
        />
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button className="btn-primary" type="submit" disabled={busy}>
        {busy ? "Starting..." : "Start investigation"}
      </button>
    </form>
  );
}
