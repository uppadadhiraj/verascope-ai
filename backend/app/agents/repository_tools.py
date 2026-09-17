"""Read-only repository investigation tools (section 22, 28).

These back the Repository Agent, Debugger Agent and Planner. Every handler
returns evidence pulled from the DB/filesystem/vector store -- never
model-invented content -- which is what lets the agents' answers cite real
files and line numbers instead of hallucinating them (section 46).

Known scope limitation, stated plainly rather than silently: dependency
tracking here is import-level (file A imports file B), not a full
function-level call graph. get_callers/get_callees answer "what
files import / are imported by this file", which is enough to trace
execution paths for the MVP's debugging scenarios but is not a CALLS graph.
"""
from __future__ import annotations

from pathlib import Path

from app.agents.context import AgentContext
from app.agents.tool_args import path_arg as _path_arg
from app.models.dependency import RepositoryDependency
from app.models.file import RepositoryFile
from app.models.symbol import RepositorySymbol
from app.services.llm.base import ToolSpec
from app.services.vectorstore.base import SearchFilters

MAX_READ_LINES = 500


def _safe_repo_path(ctx: AgentContext, relative_path: str) -> Path:
    candidate = (ctx.repo_dir / relative_path).resolve()
    if not str(candidate).startswith(str(ctx.repo_dir.resolve())):
        raise ValueError(f"Path '{relative_path}' is outside the repository.")
    return candidate


def tool_list_files(ctx: AgentContext, args: dict) -> dict:
    directory = (args.get("directory") or "").strip("/")
    query = ctx.db.query(RepositoryFile).filter(RepositoryFile.repository_id == ctx.repository.id)
    if directory:
        query = query.filter(RepositoryFile.path.like(f"{directory}/%"))
    rows = query.order_by(RepositoryFile.path).limit(300).all()
    return {
        "files": [
            {"path": r.path, "language": r.language, "is_test": r.is_test, "size_bytes": r.size_bytes}
            for r in rows
        ],
        "truncated": len(rows) == 300,
    }


def tool_read_file(ctx: AgentContext, args: dict) -> dict:
    path = _path_arg(args)
    start_line = args.get("start_line")
    end_line = args.get("end_line")

    file_row = (
        ctx.db.query(RepositoryFile)
        .filter(RepositoryFile.repository_id == ctx.repository.id, RepositoryFile.path == path)
        .first()
    )
    if file_row is None:
        return {"error": f"'{path}' is not a known file in this repository."}

    abs_path = _safe_repo_path(ctx, path)
    if not abs_path.exists():
        return {"error": f"'{path}' exists in the index but not on disk (was the repository re-indexed?)."}

    lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start_line or 1)
    end = min(len(lines), end_line or len(lines))
    if end - start + 1 > MAX_READ_LINES:
        end = start + MAX_READ_LINES - 1
    snippet = "\n".join(lines[start - 1 : end])
    return {
        "path": path,
        "language": file_row.language,
        "start_line": start,
        "end_line": end,
        "total_lines": len(lines),
        "content": snippet,
    }


def tool_search_code(ctx: AgentContext, args: dict) -> dict:
    query = args["query"]
    top_k = min(int(args.get("top_k") or 8), 20)
    language = args.get("language")
    results = ctx.vector_store.search(
        repository_id=str(ctx.repository.id),
        query=query,
        top_k=top_k,
        filters=SearchFilters(language=language) if language else None,
    )
    return {
        "results": [
            {
                "file_path": r.record.file_path,
                "start_line": r.record.start_line,
                "end_line": r.record.end_line,
                "symbol": r.record.symbol,
                "chunk_type": r.record.chunk_type,
                "content": r.record.content,
                "score": round(r.score, 4),
            }
            for r in results
        ]
    }


def tool_find_symbol(ctx: AgentContext, args: dict) -> dict:
    name = args["name"]
    rows = (
        ctx.db.query(RepositorySymbol, RepositoryFile)
        .join(RepositoryFile, RepositorySymbol.file_id == RepositoryFile.id)
        .filter(RepositorySymbol.repository_id == ctx.repository.id, RepositorySymbol.name.ilike(f"%{name}%"))
        .limit(30)
        .all()
    )
    return {
        "symbols": [
            {
                "name": sym.name,
                "type": sym.symbol_type,
                "file_path": file.path,
                "start_line": sym.start_line,
                "end_line": sym.end_line,
                "signature": sym.signature,
                "parent": None,
            }
            for sym, file in rows
        ]
    }


def tool_get_dependencies(ctx: AgentContext, args: dict) -> dict:
    """Files that the given file imports (outgoing edges)."""
    path = _path_arg(args)
    file_row = _find_file(ctx, path)
    if not file_row:
        return {"error": f"'{path}' is not a known file in this repository."}

    rows = (
        ctx.db.query(RepositoryDependency, RepositoryFile)
        .outerjoin(RepositoryFile, RepositoryDependency.target_file_id == RepositoryFile.id)
        .filter(RepositoryDependency.source_file_id == file_row.id)
        .limit(100)
        .all()
    )
    return {
        "imports": [
            {
                "relationship": dep.relationship_type.value,
                "target_file": target.path if target else None,
                "raw_reference": dep.raw_reference,
                "resolved": target is not None,
            }
            for dep, target in rows
        ]
    }


def tool_get_callers(ctx: AgentContext, args: dict) -> dict:
    """Files that import the given file (incoming edges)."""
    path = _path_arg(args)
    file_row = _find_file(ctx, path)
    if not file_row:
        return {"error": f"'{path}' is not a known file in this repository."}

    rows = (
        ctx.db.query(RepositoryDependency, RepositoryFile)
        .join(RepositoryFile, RepositoryDependency.source_file_id == RepositoryFile.id)
        .filter(RepositoryDependency.target_file_id == file_row.id)
        .limit(100)
        .all()
    )
    return {"callers": [{"file_path": src.path, "relationship": dep.relationship_type.value} for dep, src in rows]}


def tool_get_file_summary(ctx: AgentContext, args: dict) -> dict:
    path = _path_arg(args)
    file_row = _find_file(ctx, path)
    if not file_row:
        return {"error": f"'{path}' is not a known file in this repository."}
    symbols = (
        ctx.db.query(RepositorySymbol)
        .filter(RepositorySymbol.file_id == file_row.id)
        .order_by(RepositorySymbol.start_line)
        .all()
    )
    return {
        "path": file_row.path,
        "language": file_row.language,
        "line_count": file_row.line_count,
        "is_test": file_row.is_test,
        "is_config": file_row.is_config,
        "parse_error": file_row.parse_error,
        "symbols": [
            {"name": s.name, "type": s.symbol_type, "start_line": s.start_line, "end_line": s.end_line}
            for s in symbols
        ],
    }


def tool_get_repository_summary(ctx: AgentContext, args: dict) -> dict:
    return ctx.repository.summary or {"note": "Repository has not been summarized yet."}


def tool_git_history(ctx: AgentContext, args: dict) -> dict:
    import git

    path = args.get("path")
    max_count = min(int(args.get("max_count") or 20), 50)
    try:
        repo = git.Repo(ctx.repo_dir)
        commits = list(repo.iter_commits(paths=path, max_count=max_count))
    except Exception as exc:
        return {"error": f"Could not read git history: {exc}"}

    return {
        "commits": [
            {
                "sha": c.hexsha[:10],
                "author": c.author.name,
                "date": c.committed_datetime.isoformat(),
                "message": c.message.strip().splitlines()[0] if c.message else "",
            }
            for c in commits
        ]
    }


def _find_file(ctx: AgentContext, path: str) -> RepositoryFile | None:
    return (
        ctx.db.query(RepositoryFile)
        .filter(RepositoryFile.repository_id == ctx.repository.id, RepositoryFile.path == path)
        .first()
    )


REPOSITORY_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_files",
        description="List files in the repository, optionally under a specific directory.",
        parameters={
            "type": "object",
            "properties": {"directory": {"type": "string", "description": "Optional directory prefix, e.g. 'app/api'."}},
        },
    ),
    ToolSpec(
        name="read_file",
        description="Read the contents of a specific repository file, optionally a line range.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="search_code",
        description="Semantic search over the repository's indexed code and docs. Use this to find relevant code by meaning, not just exact text.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"},
                "language": {"type": "string"},
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="find_symbol",
        description="Find functions/classes/methods/routes by name (substring match).",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    ),
    ToolSpec(
        name="get_dependencies",
        description="List what a given file imports (outgoing dependency edges).",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    ),
    ToolSpec(
        name="get_callers",
        description="List what files import the given file (incoming dependency edges / who depends on this file).",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    ),
    ToolSpec(
        name="get_file_summary",
        description="Get language, symbol list, and metadata for a specific file.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    ),
    ToolSpec(
        name="get_repository_summary",
        description="Get the repository-wide summary (purpose, frameworks, entry points, facts/inferences).",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="git_history",
        description="Get recent git commit history, optionally scoped to a file path.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}, "max_count": {"type": "integer"}},
        },
    ),
]

REPOSITORY_TOOL_HANDLERS = {
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "search_code": tool_search_code,
    "find_symbol": tool_find_symbol,
    "get_dependencies": tool_get_dependencies,
    "get_callers": tool_get_callers,
    "get_file_summary": tool_get_file_summary,
    "get_repository_summary": tool_get_repository_summary,
    "git_history": tool_git_history,
}
