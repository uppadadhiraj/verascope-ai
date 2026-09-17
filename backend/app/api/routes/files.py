from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_repository
from app.core.config import get_settings
from app.db.session import get_db
from app.models.dependency import RepositoryDependency
from app.models.file import RepositoryFile
from app.models.repository import Repository
from app.models.symbol import RepositorySymbol
from app.schemas.file import (
    CodeSearchResult,
    DependencyGraph,
    DependencyGraphEdge,
    DependencyGraphNode,
    FileContentRead,
    FileRead,
    FileTreeNode,
    SymbolRead,
)
from app.services.vectorstore.base import SearchFilters
from app.services.vectorstore.chroma_store import get_vector_store

MAX_GRAPH_EDGES = 1500

router = APIRouter(prefix="/repositories/{repository_id}", tags=["files"])


@router.get("/files", response_model=list[FileRead])
def list_files(
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
    directory: str | None = Query(default=None),
) -> list[FileRead]:
    query = db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository.id)
    if directory:
        query = query.filter(RepositoryFile.path.like(f"{directory.strip('/')}/%"))
    rows = query.order_by(RepositoryFile.path).all()
    return [FileRead.model_validate(r) for r in rows]


@router.get("/files/tree", response_model=list[FileTreeNode])
def get_file_tree(
    repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> list[FileTreeNode]:
    rows = (
        db.query(RepositoryFile)
        .filter(RepositoryFile.repository_id == repository.id)
        .order_by(RepositoryFile.path)
        .all()
    )
    root: dict = {}
    for r in rows:
        parts = r.path.split("/")
        node = root
        for i, part in enumerate(parts):
            is_file = i == len(parts) - 1
            node.setdefault("_children", {})
            if part not in node["_children"]:
                node["_children"][part] = {
                    "name": part,
                    "path": "/".join(parts[: i + 1]),
                    "type": "file" if is_file else "directory",
                    "language": r.language if is_file else None,
                    "_children": {},
                }
            node = node["_children"][part]

    def to_nodes(container: dict) -> list[FileTreeNode]:
        children = container.get("_children", {})
        return [
            FileTreeNode(
                name=v["name"], path=v["path"], type=v["type"], language=v["language"], children=to_nodes(v)
            )
            for v in sorted(children.values(), key=lambda x: (x["type"] != "directory", x["name"]))
        ]

    return to_nodes(root)


@router.get("/files/content", response_model=FileContentRead)
def get_file_content(
    path: str,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> FileContentRead:
    file_row = (
        db.query(RepositoryFile)
        .filter(RepositoryFile.repository_id == repository.id, RepositoryFile.path == path)
        .first()
    )
    if file_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{path}' not found in this repository.")
    if file_row.is_binary:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{path}' is a binary file and cannot be displayed as text.")

    settings = get_settings()
    abs_path = settings.repo_path(str(repository.id)) / path
    if not str(abs_path.resolve()).startswith(str(settings.repo_path(str(repository.id)).resolve())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path.")
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"'{path}' is indexed but missing on disk.")

    content = abs_path.read_text(encoding="utf-8", errors="replace")
    return FileContentRead(path=path, language=file_row.language, content=content, line_count=file_row.line_count)


@router.get("/files/symbols", response_model=list[SymbolRead])
def get_file_symbols(
    path: str,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> list[SymbolRead]:
    file_row = (
        db.query(RepositoryFile)
        .filter(RepositoryFile.repository_id == repository.id, RepositoryFile.path == path)
        .first()
    )
    if file_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{path}' not found in this repository.")
    rows = db.query(RepositorySymbol).filter(RepositorySymbol.file_id == file_row.id).order_by(RepositorySymbol.start_line).all()
    return [SymbolRead.model_validate(r) for r in rows]


@router.get("/symbols/search", response_model=list[SymbolRead])
def search_symbols(
    q: str,
    repository: Repository = Depends(get_owned_repository),
    db: Session = Depends(get_db),
) -> list[SymbolRead]:
    rows = (
        db.query(RepositorySymbol)
        .filter(RepositorySymbol.repository_id == repository.id, RepositorySymbol.name.ilike(f"%{q}%"))
        .limit(50)
        .all()
    )
    return [SymbolRead.model_validate(r) for r in rows]


@router.get("/search", response_model=list[CodeSearchResult])
def search_code(
    q: str,
    top_k: int = 10,
    language: str | None = None,
    repository: Repository = Depends(get_owned_repository),
) -> list[CodeSearchResult]:
    store = get_vector_store()
    results = store.search(
        repository_id=str(repository.id),
        query=q,
        top_k=min(top_k, 30),
        filters=SearchFilters(language=language) if language else None,
    )
    return [
        CodeSearchResult(
            file_path=r.record.file_path,
            start_line=r.record.start_line,
            end_line=r.record.end_line,
            symbol=r.record.symbol,
            chunk_type=r.record.chunk_type,
            content=r.record.content,
            score=r.score,
        )
        for r in results
    ]


@router.get("/dependency-graph", response_model=DependencyGraph)
def get_dependency_graph(
    repository: Repository = Depends(get_owned_repository), db: Session = Depends(get_db)
) -> DependencyGraph:
    """Real, extracted IMPORTS edges between files in this repository --
    rendered by the frontend as an actual graph rather than asked of an LLM,
    which cannot reliably "draw" a diagram in a text response and has no
    reason to when the ground truth is already sitting in Postgres."""
    rows = (
        db.query(RepositoryDependency, RepositoryFile)
        .join(RepositoryFile, RepositoryDependency.source_file_id == RepositoryFile.id)
        .filter(
            RepositoryDependency.repository_id == repository.id,
            RepositoryDependency.target_file_id.isnot(None),
        )
        .limit(MAX_GRAPH_EDGES + 1)
        .all()
    )
    truncated = len(rows) > MAX_GRAPH_EDGES
    rows = rows[:MAX_GRAPH_EDGES]

    target_ids = {dep.target_file_id for dep, _src in rows}
    target_files = {f.id: f for f in db.query(RepositoryFile).filter(RepositoryFile.id.in_(target_ids)).all()} if target_ids else {}

    degree: dict[str, dict[str, int]] = {}

    def touch(path: str) -> dict[str, int]:
        return degree.setdefault(path, {"in": 0, "out": 0})

    edges: list[DependencyGraphEdge] = []
    file_meta: dict[str, RepositoryFile] = {}
    for dep, source_file in rows:
        target_file = target_files.get(dep.target_file_id)
        if target_file is None:
            continue
        file_meta[source_file.path] = source_file
        file_meta[target_file.path] = target_file
        touch(source_file.path)["out"] += 1
        touch(target_file.path)["in"] += 1
        edges.append(
            DependencyGraphEdge(
                source=source_file.path, target=target_file.path, relationship=dep.relationship_type.value
            )
        )

    nodes = [
        DependencyGraphNode(
            id=path,
            language=f.language,
            is_test=f.is_test,
            in_degree=degree.get(path, {}).get("in", 0),
            out_degree=degree.get(path, {}).get("out", 0),
        )
        for path, f in file_meta.items()
    ]

    return DependencyGraph(nodes=nodes, edges=edges, truncated=truncated)
