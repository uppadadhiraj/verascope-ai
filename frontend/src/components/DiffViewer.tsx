interface DiffLine {
  type: "add" | "remove" | "context" | "hunk" | "meta";
  content: string;
}

function parseDiff(diffText: string): DiffLine[] {
  return diffText.split("\n").map((line) => {
    if (line.startsWith("+++") || line.startsWith("---")) return { type: "meta", content: line };
    if (line.startsWith("@@")) return { type: "hunk", content: line };
    if (line.startsWith("+")) return { type: "add", content: line };
    if (line.startsWith("-")) return { type: "remove", content: line };
    return { type: "context", content: line };
  });
}

const STYLES: Record<DiffLine["type"], string> = {
  add: "bg-emerald-500/10 text-emerald-300",
  remove: "bg-red-500/10 text-red-300",
  hunk: "bg-indigo-500/10 text-indigo-300",
  meta: "text-slate-500",
  context: "text-slate-300",
};

export function DiffViewer({ diff, fileLabel }: { diff: string; fileLabel?: string }) {
  if (!diff || !diff.trim()) {
    return <div className="p-4 text-sm text-slate-500">No diff available.</div>;
  }
  const lines = parseDiff(diff);

  return (
    <div className="overflow-hidden rounded-md border border-surface-border">
      {fileLabel && (
        <div className="border-b border-surface-border bg-surface-raised px-3 py-1.5 font-mono text-xs text-slate-400">
          {fileLabel}
        </div>
      )}
      <pre className="max-h-[600px] overflow-auto bg-surface p-0 font-mono text-xs leading-5">
        {lines.map((line, i) => (
          <div key={i} className={`whitespace-pre px-3 ${STYLES[line.type]}`}>
            {line.content || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}
