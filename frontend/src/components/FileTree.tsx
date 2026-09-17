import { useState } from "react";
import { ChevronRight, ChevronDown, File, Folder } from "lucide-react";
import type { FileTreeNode } from "@/api/types";

function TreeNode({
  node,
  onSelect,
  selectedPath,
  depth,
}: {
  node: FileTreeNode;
  onSelect: (path: string) => void;
  selectedPath: string | null;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 1);

  if (node.type === "directory") {
    return (
      <div>
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-sm text-slate-300 hover:bg-surface-border"
          style={{ paddingLeft: `${depth * 14 + 6}px` }}
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          <Folder size={13} className="text-indigo-400" />
          <span className="truncate">{node.name}</span>
        </button>
        {open &&
          node.children.map((child) => (
            <TreeNode key={child.path} node={child} onSelect={onSelect} selectedPath={selectedPath} depth={depth + 1} />
          ))}
      </div>
    );
  }

  const isSelected = selectedPath === node.path;
  return (
    <button
      onClick={() => onSelect(node.path)}
      className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-sm hover:bg-surface-border ${
        isSelected ? "bg-indigo-600/20 text-indigo-300" : "text-slate-400"
      }`}
      style={{ paddingLeft: `${depth * 14 + 20}px` }}
    >
      <File size={13} />
      <span className="truncate">{node.name}</span>
    </button>
  );
}

export function FileTree({
  nodes,
  onSelect,
  selectedPath,
}: {
  nodes: FileTreeNode[];
  onSelect: (path: string) => void;
  selectedPath: string | null;
}) {
  return (
    <div className="py-1">
      {nodes.map((node) => (
        <TreeNode key={node.path} node={node} onSelect={onSelect} selectedPath={selectedPath} depth={0} />
      ))}
    </div>
  );
}
