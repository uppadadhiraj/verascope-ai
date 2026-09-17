import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, Circle, CircleDot, XCircle, GitBranch, ExternalLink, PlayCircle } from "lucide-react";
import { Layout } from "@/components/Layout";
import { StatusBadge } from "@/components/StatusBadge";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { DiffViewer } from "@/components/DiffViewer";
import { taskApi, approvalsApi, changesApi, testsApi, gitApi } from "@/api/endpoints";
import { apiErrorMessage } from "@/api/client";
import type { Approval, CodeChange, DiffSummary, PullRequest, Task, TestRun } from "@/api/types";

const STEP_ICON: Record<string, JSX.Element> = {
  COMPLETED: <CheckCircle2 size={15} className="text-emerald-400" />,
  IN_PROGRESS: <CircleDot size={15} className="text-amber-400" />,
  FAILED: <XCircle size={15} className="text-red-400" />,
  BLOCKED: <XCircle size={15} className="text-red-400" />,
  PENDING: <Circle size={15} className="text-slate-600" />,
};

export function TaskDetailPage() {
  const { repositoryId, taskId } = useParams<{ repositoryId: string; taskId: string }>();
  const [task, setTask] = useState<Task | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [diff, setDiff] = useState<DiffSummary | null>(null);
  const [testRuns, setTestRuns] = useState<TestRun[]>([]);
  const [pullRequests, setPullRequests] = useState<PullRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!repositoryId || !taskId) return;
    const [t, a, tr, pr] = await Promise.all([
      taskApi.get(repositoryId, taskId),
      approvalsApi.list(repositoryId, taskId),
      testsApi.forTask(repositoryId, taskId),
      gitApi.listPullRequests(repositoryId, taskId).catch(() => []),
    ]);
    setTask(t);
    setApprovals(a);
    setTestRuns(tr);
    setPullRequests(pr);
    if (t.status !== "PENDING") {
      const d = await changesApi.diff(repositoryId, taskId).catch(() => null);
      setDiff(d);
    }
  }, [repositoryId, taskId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3500);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!task || !repositoryId || !taskId) {
    return (
      <Layout>
        <div className="p-8 text-sm text-slate-500">Loading...</div>
      </Layout>
    );
  }

  const codeChangeApproval = approvals.find((a) => a.approval_type === "CODE_CHANGE");
  const gitApproval = approvals.find((a) => a.approval_type === "GIT_OPERATION");
  const prApproval = approvals.find((a) => a.approval_type === "PR_CREATION");
  const hasChanges = (diff?.changes.length || 0) > 0;
  const fixNotYetStarted = codeChangeApproval?.status === "APPROVED" && !hasChanges;
  const latestPR = pullRequests[0];

  async function decide(approval: Approval, status: "APPROVED" | "REJECTED" | "CHANGES_REQUESTED", comment?: string) {
    await approvalsApi.decide(repositoryId!, approval.id, status, comment);
    await refresh();
  }

  async function runFix() {
    setBusyAction("fix");
    setError(null);
    try {
      await taskApi.startFix(repositoryId!, taskId!);
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusyAction(null);
    }
  }

  async function createBranch() {
    setBusyAction("branch");
    setError(null);
    try {
      await gitApi.createBranch(repositoryId!, taskId!);
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusyAction(null);
    }
  }

  async function openPR() {
    setBusyAction("pr");
    setError(null);
    try {
      await gitApi.openPullRequest(repositoryId!, taskId!);
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <Layout>
      <div className="mx-auto max-w-3xl space-y-5 px-8 py-8">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <h1 className="text-lg font-semibold text-slate-100">{task.title}</h1>
            <StatusBadge status={task.status} />
          </div>
          {task.description && <p className="text-sm text-slate-500">{task.description}</p>}
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        {task.steps && task.steps.length > 0 && (
          <div className="card p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Plan</h2>
            <div className="space-y-2">
              {task.steps.map((step) => (
                <div key={step.id} className="flex items-start gap-2.5">
                  {STEP_ICON[step.status] || STEP_ICON.PENDING}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-300">{step.description}</p>
                    {step.evidence && <p className="mt-0.5 truncate text-xs text-slate-500">{step.evidence}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {task.root_cause !== undefined && (task.root_cause || task.evidence_status) && (
          <div className="card p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200">Root Cause</h2>
              {task.evidence_status && <StatusBadge status={task.evidence_status} />}
            </div>
            <p className="text-sm text-slate-300">{task.root_cause || "Not yet determined."}</p>
            {task.confidence_notes && <p className="mt-2 text-xs text-slate-500">{task.confidence_notes}</p>}
            {task.evidence && task.evidence.length > 0 && (
              <ul className="mt-3 space-y-1 border-t border-surface-border pt-2">
                {task.evidence.map((e, i) => (
                  <li key={i} className="font-mono text-xs text-slate-500">
                    {e.file_path}
                    {e.start_line ? `:${e.start_line}` : ""}
                    {e.note ? <span className="ml-2 font-sans text-slate-600">— {e.note}</span> : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {codeChangeApproval && <ApprovalPanel approval={codeChangeApproval} onDecide={(s, c) => decide(codeChangeApproval, s, c)} />}

        {fixNotYetStarted && (
          <button className="btn-primary" onClick={runFix} disabled={busyAction !== null}>
            <PlayCircle size={16} /> {busyAction === "fix" ? "Running Fix Agent..." : "Run Fix Agent + Tests"}
          </button>
        )}

        {testRuns.length > 0 && (
          <div className="card p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Test Runs</h2>
            <div className="space-y-2">
              {testRuns.map((run) => (
                <div key={run.id} className="flex items-center justify-between rounded border border-surface-border p-2.5 text-sm">
                  <div>
                    <div className="text-slate-300">
                      Iteration {run.iteration} · {run.framework || "unknown"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {run.passed_count ?? "?"} passed, {run.failed_count ?? "?"} failed · {run.duration_ms}ms
                    </div>
                  </div>
                  <StatusBadge status={run.status} />
                </div>
              ))}
            </div>
          </div>
        )}

        {diff && hasChanges && (
          <div className="card p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Diff</h2>
            <div className="mb-2 flex gap-3 text-xs text-slate-500">
              {diff.files_created.length > 0 && <span>{diff.files_created.length} created</span>}
              {diff.files_modified.length > 0 && <span>{diff.files_modified.length} modified</span>}
              {diff.files_deleted.length > 0 && <span>{diff.files_deleted.length} deleted</span>}
            </div>
            <div className="space-y-3">
              {diff.changes.map((c: CodeChange) => (
                <DiffViewer key={c.id} diff={c.diff || ""} fileLabel={`${c.file_path} (${c.change_type})`} />
              ))}
            </div>
          </div>
        )}

        {gitApproval && <ApprovalPanel approval={gitApproval} onDecide={(s, c) => decide(gitApproval, s, c)} />}

        {gitApproval?.status === "APPROVED" && !latestPR && (
          <button className="btn-primary" onClick={createBranch} disabled={busyAction !== null}>
            <GitBranch size={16} /> {busyAction === "branch" ? "Creating branch..." : "Create Branch & Commit"}
          </button>
        )}

        {latestPR && (
          <div className="card p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-200">Git</h2>
            <p className="font-mono text-xs text-slate-400">
              {latestPR.branch_name} → {latestPR.base_branch}
            </p>
            {latestPR.commit_sha && <p className="mt-1 font-mono text-xs text-slate-500">commit {latestPR.commit_sha.slice(0, 10)}</p>}
            <div className="mt-2">
              <StatusBadge status={latestPR.status} />
            </div>
            {latestPR.pr_url && (
              <a
                href={latestPR.pr_url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-sm text-indigo-400 hover:underline"
              >
                View pull request <ExternalLink size={13} />
              </a>
            )}
          </div>
        )}

        {prApproval && <ApprovalPanel approval={prApproval} onDecide={(s, c) => decide(prApproval, s, c)} />}

        {prApproval?.status === "APPROVED" && latestPR?.status !== "PR_CREATED" && (
          <button className="btn-primary" onClick={openPR} disabled={busyAction !== null}>
            <GitBranch size={16} /> {busyAction === "pr" ? "Opening pull request..." : "Open Pull Request"}
          </button>
        )}
      </div>
    </Layout>
  );
}
