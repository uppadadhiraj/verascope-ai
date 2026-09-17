import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ShieldAlert, ScanLine, CheckCircle2 } from "lucide-react";
import { Layout } from "@/components/Layout";
import { StatusBadge } from "@/components/StatusBadge";
import { findingsApi, repositoryApi } from "@/api/endpoints";
import type { Finding } from "@/api/types";

export function SecurityPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [scanning, setScanning] = useState(false);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const scanStartedAt = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    if (!repositoryId) return null;
    const [rows, repo] = await Promise.all([findingsApi.list(repositoryId), repositoryApi.get(repositoryId)]);
    setFindings(rows);
    setLastScanAt(repo.last_security_scan_at);
    return repo.last_security_scan_at;
  }, [repositoryId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function scan() {
    if (!repositoryId) return;
    setScanning(true);
    scanStartedAt.current = lastScanAt;
    await findingsApi.triggerScan(repositoryId);

    // Poll instead of a single fixed-delay refresh (a repository scan can
    // legitimately take longer than a few seconds) -- stop once
    // last_security_scan_at actually advances past what it was before this
    // scan started, which is the real, unambiguous "the scan finished"
    // signal rather than guessing at a timeout.
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const newScanAt = await refresh();
      if (newScanAt && newScanAt !== scanStartedAt.current) break;
    }
    setScanning(false);
  }

  async function updateStatus(findingId: string, status: string) {
    if (!repositoryId) return;
    await findingsApi.updateStatus(repositoryId, findingId, status);
    refresh();
  }

  return (
    <Layout>
      <div className="mx-auto max-w-3xl px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-100">Security Findings</h1>
            <p className="text-sm text-slate-500">Pattern-based static analysis, grounded in actual matched code.</p>
          </div>
          <button className="btn-primary" onClick={scan} disabled={scanning}>
            <ScanLine size={16} /> {scanning ? "Scanning..." : "Run scan"}
          </button>
        </div>

        {findings.length === 0 ? (
          <div className="card flex flex-col items-center gap-2 p-12 text-center">
            {lastScanAt ? (
              <>
                <CheckCircle2 size={28} className="text-emerald-500" />
                <p className="text-sm text-slate-300">
                  Scan complete -- no issues found by the current rule set.
                </p>
                <p className="text-xs text-slate-500">
                  Last scanned {new Date(lastScanAt).toLocaleString()}. This checks for a specific,
                  documented set of patterns (hardcoded secrets, unsafe eval/exec, weak crypto, and
                  similar) -- a clean result means none of those specific patterns matched, not a
                  full security audit.
                </p>
              </>
            ) : (
              <>
                <ShieldAlert size={28} className="text-slate-600" />
                <p className="text-sm text-slate-500">Not scanned yet. Click "Run scan" to check for common issues.</p>
              </>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {lastScanAt && (
              <p className="text-xs text-slate-500">Last scanned {new Date(lastScanAt).toLocaleString()}</p>
            )}
            {findings.map((f) => (
              <div key={f.id} className="card p-4">
                <div className="mb-1.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={f.severity} />
                    <span className="text-sm font-medium text-slate-200">{f.finding_type.replace(/_/g, " ")}</span>
                  </div>
                  <select
                    value={f.status}
                    onChange={(e) => updateStatus(f.id, e.target.value)}
                    className="rounded bg-surface-border px-2 py-1 text-xs text-slate-300"
                  >
                    {["OPEN", "ACKNOWLEDGED", "RESOLVED", "FALSE_POSITIVE"].map((s) => (
                      <option key={s} value={s}>
                        {s.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="font-mono text-xs text-slate-500">
                  {f.file_path}
                  {f.start_line ? `:${f.start_line}` : ""}
                </p>
                <pre className="mt-2 overflow-x-auto rounded bg-surface p-2 font-mono text-xs text-slate-400">{f.evidence}</pre>
                <p className="mt-2 text-sm text-slate-300">{f.explanation}</p>
                {f.impact && <p className="mt-1 text-xs text-slate-500">Impact: {f.impact}</p>}
                {f.remediation && <p className="mt-1 text-xs text-emerald-400/80">Fix: {f.remediation}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
