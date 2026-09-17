"""The ingestion pipeline (section 2 diagram):

Repository -> Scanner -> Language Detection -> Parser -> File & Symbol
Metadata -> Dependency Analysis -> Chunking -> Embeddings -> Vector KB ->
Repository Summary -> READY

Every phase updates `Repository.status`/`status_detail` so the frontend can
show real ingestion progress (section 7). A failure in any phase sets
status=FAILED with a specific `error_message` -- never a silent hang and
never a generic failure (section 45).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.dependency import RepositoryDependency
from app.models.enums import RelationshipType, RepositoryStatus
from app.models.file import RepositoryFile
from app.models.repository import Repository
from app.models.symbol import RepositorySymbol
from app.services.ingestion import dependency_resolver, summary as summary_service
from app.services.ingestion.chunker import chunk_file
from app.services.ingestion.parser import parse_file
from app.services.ingestion.scanner import ScannedFile, scan_repository
from app.services.vectorstore.base import VectorRecord
from app.services.vectorstore.chroma_store import get_vector_store

logger = get_logger(__name__)


class IngestionFailed(Exception):
    pass


def run_ingestion_pipeline(db: Session, repository: Repository, settings: Settings) -> None:
    root = settings.repo_path(str(repository.id))
    try:
        _set_status(db, repository, RepositoryStatus.SCANNING, "Scanning repository files")

        # Clear this repository's OLD file/symbol/dependency rows before
        # inserting new ones (section 48: rescan must not leave stale data
        # around). Critical bug found live: this was missing entirely --
        # first-time ingestion always "worked" because there was nothing to
        # conflict with, but the very first rescan of any repository failed
        # outright with a UniqueViolation on (repository_id, path), because
        # only the vector store had an equivalent delete-before-reindex step
        # (_embed_repository below). RepositorySymbol and
        # RepositoryDependency both have ON DELETE CASCADE foreign keys to
        # RepositoryFile, so deleting the files cascades correctly.
        db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository.id).delete(
            synchronize_session=False
        )
        db.commit()

        scan_result = scan_repository(root, settings)
        if not scan_result.files:
            raise IngestionFailed("No files were found in the repository after applying ignore rules.")

        file_rows = _persist_files(db, repository, scan_result.files)

        _set_status(db, repository, RepositoryStatus.PARSING, "Parsing source files and extracting symbols")
        parsed_by_path, imports_by_file, language_by_file = _parse_and_persist_symbols(
            db, repository, scan_result.files, file_rows
        )

        _persist_dependencies(db, repository, imports_by_file, language_by_file, file_rows)

        _set_status(db, repository, RepositoryStatus.EMBEDDING, "Building the semantic vector index")
        _embed_repository(repository, scan_result.files, parsed_by_path)

        _set_status(db, repository, RepositoryStatus.SUMMARIZING, "Generating repository summary")
        _generate_and_store_summary(
            db, repository, scan_result.files, language_by_file, imports_by_file, parsed_by_path, root
        )

        repository.status = RepositoryStatus.READY
        repository.status_detail = "Repository ready"
        repository.error_message = None
        repository.file_count = len(scan_result.files)
        repository.total_size_bytes = sum(f.size_bytes for f in scan_result.files)
        repository.last_indexed_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        logger.info("ingestion_completed", repository_id=str(repository.id), files=len(scan_result.files))

    except IngestionFailed as exc:
        _fail(db, repository, str(exc))
    except Exception as exc:  # noqa: BLE001 -- must convert to a stored, user-visible failure
        logger.error("ingestion_unexpected_error", repository_id=str(repository.id), error=str(exc))
        _fail(db, repository, f"Unexpected error during ingestion: {exc}")


def _set_status(db: Session, repository: Repository, status: RepositoryStatus, detail: str) -> None:
    repository.status = status
    repository.status_detail = detail
    db.commit()
    logger.info("ingestion_phase", repository_id=str(repository.id), status=status.value, detail=detail)


def _fail(db: Session, repository: Repository, message: str) -> None:
    # If the exception that got us here came from a failed flush/commit
    # (e.g. a UniqueViolation), the session's transaction is left in a
    # "pending rollback" state -- any further statement, commit included,
    # raises PendingRollbackError until it's explicitly rolled back. Found
    # live: without this, a mid-transaction DB error would silently prevent
    # THIS commit from ever recording status=FAILED, leaving the repository
    # stuck at whatever status it last reached (e.g. SCANNING) forever, with
    # no error ever surfaced to the user -- precisely the "silent hang"
    # this module's own docstring says must never happen.
    db.rollback()
    repository.status = RepositoryStatus.FAILED
    repository.error_message = message
    repository.status_detail = "Ingestion failed"
    db.commit()


def _persist_files(
    db: Session, repository: Repository, scanned: list[ScannedFile]
) -> dict[str, RepositoryFile]:
    rows: dict[str, RepositoryFile] = {}
    for sf in scanned:
        row = RepositoryFile(
            repository_id=repository.id,
            path=sf.path,
            language=sf.language,
            size_bytes=sf.size_bytes,
            line_count=sf.line_count,
            content_hash=sf.content_hash,
            is_test=sf.is_test,
            is_config=sf.is_config,
            is_documentation=sf.is_documentation,
            is_binary=sf.is_binary,
            skipped_reason=sf.skipped_reason,
        )
        db.add(row)
        rows[sf.path] = row
    db.flush()
    return rows


def _parse_and_persist_symbols(
    db: Session,
    repository: Repository,
    scanned: list[ScannedFile],
    file_rows: dict[str, RepositoryFile],
):
    from app.services.ingestion.parser.base import ParsedFile

    parsed_by_path: dict[str, ParsedFile] = {}
    imports_by_file: dict[str, list] = {}
    language_by_file: dict[str, str | None] = {}

    for sf in scanned:
        language_by_file[sf.path] = sf.language
        if sf.skipped_reason:
            continue
        try:
            content = sf.absolute_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            file_rows[sf.path].parse_error = f"unreadable: {exc}"
            continue

        parsed = parse_file(sf.language, content)
        parsed_by_path[sf.path] = parsed
        imports_by_file[sf.path] = parsed.imports

        if parsed.error:
            file_rows[sf.path].parse_error = parsed.error
            continue  # section 11: a parse failure skips symbol extraction for THIS file only

        file_row = file_rows[sf.path]
        class_symbol_ids: dict[str, uuid.UUID] = {}

        # Pass 1: classes/interfaces first so methods can reference their parent id.
        for sym in parsed.symbols:
            if sym.symbol_type in ("class", "interface"):
                row = RepositorySymbol(
                    repository_id=repository.id,
                    file_id=file_row.id,
                    name=sym.name,
                    symbol_type=sym.symbol_type,
                    language=sf.language or "unknown",
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    signature=sym.signature,
                    docstring=sym.docstring,
                )
                db.add(row)
                db.flush()
                class_symbol_ids[sym.name] = row.id

        # Pass 2: everything else, linked to its parent class if we have one.
        for sym in parsed.symbols:
            if sym.symbol_type in ("class", "interface"):
                continue
            parent_id = class_symbol_ids.get(sym.parent_name) if sym.parent_name else None
            row = RepositorySymbol(
                repository_id=repository.id,
                file_id=file_row.id,
                parent_symbol_id=parent_id,
                name=sym.name,
                symbol_type=sym.symbol_type,
                language=sf.language or "unknown",
                start_line=sym.start_line,
                end_line=sym.end_line,
                signature=sym.signature,
                docstring=sym.docstring,
                route_path=sym.route_path,
                http_method=sym.http_method,
            )
            db.add(row)

    db.flush()
    db.commit()
    return parsed_by_path, imports_by_file, language_by_file


def _persist_dependencies(
    db: Session,
    repository: Repository,
    imports_by_file: dict[str, list],
    language_by_file: dict[str, str | None],
    file_rows: dict[str, RepositoryFile],
) -> None:
    resolved = dependency_resolver.resolve_imports(imports_by_file, language_by_file)
    for edge in resolved:
        source_row = file_rows.get(edge.source_file)
        if not source_row:
            continue
        target_row = file_rows.get(edge.target_file) if edge.target_file else None
        db.add(
            RepositoryDependency(
                repository_id=repository.id,
                relationship_type=RelationshipType.IMPORTS,
                source_file_id=source_row.id,
                target_file_id=target_row.id if target_row else None,
                raw_reference=edge.raw,
            )
        )
    db.commit()


def _embed_repository(repository: Repository, scanned: list[ScannedFile], parsed_by_path: dict) -> None:
    store = get_vector_store()
    store.delete_repository(str(repository.id))

    records: list[VectorRecord] = []
    for sf in scanned:
        if sf.skipped_reason:
            continue
        parsed = parsed_by_path.get(sf.path)
        symbols = parsed.symbols if parsed else []
        try:
            content = sf.absolute_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks = chunk_file(content, sf.language, symbols)
        for i, chunk in enumerate(chunks):
            records.append(
                VectorRecord(
                    id=f"{repository.id}:{sf.path}:{i}",
                    repository_id=str(repository.id),
                    file_path=sf.path,
                    language=sf.language,
                    chunk_type=chunk.chunk_type,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    content=chunk.content,
                    symbol=chunk.symbol,
                )
            )

    batch_size = 128
    for i in range(0, len(records), batch_size):
        store.upsert(records[i : i + batch_size])


def _generate_and_store_summary(
    db: Session,
    repository: Repository,
    scanned: list[ScannedFile],
    language_by_file: dict[str, str | None],
    imports_by_file: dict[str, list],
    parsed_by_path: dict,
    root,
) -> None:
    language_counts: dict[str, int] = {}
    for sf in scanned:
        if sf.language:
            language_counts[sf.language] = language_counts.get(sf.language, 0) + 1

    file_inputs = [
        summary_service.FileSummaryInput(
            path=sf.path, language=sf.language, is_config=sf.is_config, is_test=sf.is_test
        )
        for sf in scanned
    ]

    routes: list[tuple[str, str, str]] = []
    for path, parsed in parsed_by_path.items():
        for sym in parsed.symbols:
            if sym.symbol_type == "route" and sym.route_path:
                routes.append((path, sym.http_method or "GET", sym.route_path))

    def read_config_content(path: str) -> str | None:
        try:
            return (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    data = summary_service.build_rule_based_summary(
        file_inputs, language_counts, imports_by_file, routes, read_config_content
    )

    readme_excerpt = None
    for candidate in ("README.md", "readme.md", "Readme.md"):
        readme_excerpt = read_config_content(candidate)
        if readme_excerpt:
            break

    try:
        data = summary_service.enhance_summary_with_llm(data, readme_excerpt)
    except Exception as exc:  # noqa: BLE001 -- LLM enhancement is best-effort only
        logger.warning("summary_llm_enhancement_failed", repository_id=str(repository.id), error=str(exc))
        data.uncertain.append("AI-generated purpose summary unavailable (LLM provider error).")

    repository.summary = data.to_dict()
    repository.languages = language_counts
    repository.frameworks = data.frameworks
    db.commit()
