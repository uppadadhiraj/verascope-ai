const COLORS: Record<string, string> = {
  READY: "bg-emerald-500/15 text-emerald-400",
  COMPLETED: "bg-emerald-500/15 text-emerald-400",
  PASSED: "bg-emerald-500/15 text-emerald-400",
  APPROVED: "bg-emerald-500/15 text-emerald-400",
  VALIDATED: "bg-emerald-500/15 text-emerald-400",

  PENDING: "bg-slate-500/15 text-slate-300",
  PROPOSED: "bg-slate-500/15 text-slate-300",

  CLONING: "bg-amber-500/15 text-amber-400",
  SCANNING: "bg-amber-500/15 text-amber-400",
  PARSING: "bg-amber-500/15 text-amber-400",
  EMBEDDING: "bg-amber-500/15 text-amber-400",
  SUMMARIZING: "bg-amber-500/15 text-amber-400",
  IN_PROGRESS: "bg-amber-500/15 text-amber-400",
  RUNNING: "bg-amber-500/15 text-amber-400",
  APPLIED: "bg-amber-500/15 text-amber-400",
  TESTED: "bg-amber-500/15 text-amber-400",

  FAILED: "bg-red-500/15 text-red-400",
  ERROR: "bg-red-500/15 text-red-400",
  TIMEOUT: "bg-red-500/15 text-red-400",
  REJECTED: "bg-red-500/15 text-red-400",
  BLOCKED: "bg-red-500/15 text-red-400",

  CRITICAL: "bg-red-600/20 text-red-400",
  HIGH: "bg-orange-500/15 text-orange-400",
  MEDIUM: "bg-amber-500/15 text-amber-400",
  LOW: "bg-slate-500/15 text-slate-300",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = COLORS[status] || "bg-slate-500/15 text-slate-300";
  return <span className={`badge ${cls}`}>{status.replace(/_/g, " ")}</span>;
}
