import { useState } from "react";
import { Check, X, MessageCircleWarning } from "lucide-react";
import type { Approval } from "@/api/types";
import { StatusBadge } from "./StatusBadge";
import { DiffViewer } from "./DiffViewer";

const TITLES: Record<string, string> = {
  CODE_CHANGE: "Approve proposed fix",
  GIT_OPERATION: "Approve branch + commit",
  PR_CREATION: "Approve pull request creation",
};

export function ApprovalPanel({
  approval,
  onDecide,
}: {
  approval: Approval;
  onDecide: (status: "APPROVED" | "REJECTED" | "CHANGES_REQUESTED", comment?: string) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const snap = approval.summary_snapshot || {};

  async function decide(status: "APPROVED" | "REJECTED" | "CHANGES_REQUESTED") {
    setBusy(status);
    try {
      await onDecide(status, comment || undefined);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">
          {TITLES[approval.approval_type] || approval.approval_type}
        </h3>
        <StatusBadge status={approval.status} />
      </div>

      <div className="space-y-3 text-sm">
        {snap.problem && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Problem</div>
            <p className="text-slate-300">{snap.problem}</p>
          </div>
        )}
        {snap.root_cause && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Root Cause</div>
            <p className="text-slate-300">{snap.root_cause}</p>
          </div>
        )}
        {snap.proposed_fix && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Proposed Fix</div>
            <p className="text-slate-300">{snap.proposed_fix}</p>
          </div>
        )}
        {snap.affected_files && snap.affected_files.length > 0 && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Files Affected</div>
            <ul className="list-inside list-disc text-slate-300">
              {snap.affected_files.map((f: string) => (
                <li key={f} className="font-mono text-xs">
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}
        {snap.files_changed && snap.files_changed.length > 0 && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Files Changed</div>
            <ul className="list-inside list-disc text-slate-300">
              {snap.files_changed.map((f: string) => (
                <li key={f} className="font-mono text-xs">
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}
        {snap.review?.summary && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Code Review</div>
            <p className="text-slate-300">
              <span className="mr-1 font-semibold">{snap.review.overall_assessment}:</span>
              {snap.review.summary}
            </p>
          </div>
        )}
        {snap.diff && (
          <div>
            <div className="mb-1 text-xs font-medium uppercase text-slate-500">Diff</div>
            <DiffViewer diff={snap.diff} />
          </div>
        )}
        {snap.branch_name && (
          <div>
            <div className="text-xs font-medium uppercase text-slate-500">Branch</div>
            <p className="font-mono text-xs text-slate-300">
              {snap.branch_name} <span className="text-slate-500">from</span> {snap.base_branch}
            </p>
          </div>
        )}
      </div>

      {approval.status === "PENDING" ? (
        <div className="mt-4 space-y-2 border-t border-surface-border pt-3">
          <textarea
            className="input min-h-[60px] resize-none"
            placeholder="Optional comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="flex gap-2">
            <button className="btn-primary" disabled={busy !== null} onClick={() => decide("APPROVED")}>
              <Check size={14} /> Approve
            </button>
            <button className="btn-secondary" disabled={busy !== null} onClick={() => decide("CHANGES_REQUESTED")}>
              <MessageCircleWarning size={14} /> Request changes
            </button>
            <button className="btn-danger" disabled={busy !== null} onClick={() => decide("REJECTED")}>
              <X size={14} /> Reject
            </button>
          </div>
        </div>
      ) : (
        approval.comment && <p className="mt-3 border-t border-surface-border pt-3 text-xs text-slate-500">Comment: {approval.comment}</p>
      )}
    </div>
  );
}
