"""Repository summary generation (section 16).

Two layers, deliberately kept separate:

1. Rule-based facts -- derived directly from scanned files, config file
   contents and detected imports. These are FACTs: no model in the loop, no
   hallucination risk.
2. An optional LLM synthesis pass that turns those facts into a short
   natural-language `purpose` paragraph and a small number of INFERENCEs.
   If it fails (no API key, provider error), ingestion still succeeds with
   the rule-based summary alone -- the LLM layer is additive, never load
   bearing.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.services.ingestion.parser.base import ExtractedImport

_FRAMEWORK_SIGNATURES: dict[str, list[str]] = {
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "django": ["django"],
    "express": ["express"],
    "nextjs": ["next"],
    "react": ["react"],
    "vue": ["vue"],
    "angular": ["@angular/core"],
    "spring": ["org.springframework", "spring-boot"],
    "nestjs": ["@nestjs/core"],
}

_DATABASE_SIGNATURES: dict[str, list[str]] = {
    "PostgreSQL": ["psycopg", "psycopg2", "asyncpg", "sqlalchemy", "pg", "postgres"],
    "MySQL": ["mysql", "pymysql", "mysql2"],
    "MongoDB": ["pymongo", "mongoose", "mongodb"],
    "SQLite": ["sqlite3", "sqlite"],
    "Redis": ["redis"],
}

_AUTH_SIGNATURES: dict[str, list[str]] = {
    "JWT": ["jwt", "jsonwebtoken", "pyjwt", "jose"],
    "OAuth": ["oauth", "authlib", "passport-oauth"],
    "Session-based": ["flask_login", "express-session", "django.contrib.auth"],
}

_TEST_FRAMEWORK_FILES: dict[str, list[str]] = {
    "pytest": ["pytest.ini", "conftest.py", "pyproject.toml"],
    "Jest": ["jest.config.js", "jest.config.ts"],
    "Vitest": ["vitest.config.ts", "vitest.config.js"],
    "JUnit": ["pom.xml", "build.gradle"],
}

_ENTRY_POINT_CANDIDATES = [
    "main.py", "app/main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "src/index.js", "index.ts", "src/index.ts", "src/main.tsx",
    "src/App.tsx", "server.js", "app.js",
    "Main.java", "src/main/java",
]


@dataclass
class FileSummaryInput:
    path: str
    language: str | None
    is_config: bool
    is_test: bool


@dataclass
class RepositorySummaryData:
    purpose: str | None = None
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    important_directories: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    api_entry_points: list[str] = field(default_factory=list)
    database: str | None = None
    authentication: str | None = None
    major_components: list[str] = field(default_factory=list)
    test_framework: str | None = None
    build_instructions: str | None = None
    important_config_files: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    inferences: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_rule_based_summary(
    files: list[FileSummaryInput],
    language_counts: dict[str, int],
    imports_by_file: dict[str, list[ExtractedImport]],
    routes: list[tuple[str, str, str]],  # (file_path, method, path)
    read_config_content: callable,
) -> RepositorySummaryData:
    """`read_config_content(path) -> str | None` lets the caller supply file
    bytes without this module knowing about disk paths / storage layout."""
    summary = RepositorySummaryData()

    summary.languages = sorted(language_counts, key=lambda l: -language_counts[l])
    summary.facts.append(f"Detected languages: {', '.join(summary.languages) or 'none'}.")

    all_text_blobs: list[str] = []
    config_paths = [f.path for f in files if f.is_config]
    summary.important_config_files = config_paths[:20]
    for path in config_paths:
        content = read_config_content(path)
        if content:
            all_text_blobs.append(content.lower())

    all_imports = " ".join(
        imp.raw.lower() for imps in imports_by_file.values() for imp in imps
    )
    corpus = " ".join(all_text_blobs) + " " + all_imports

    for framework, signatures in _FRAMEWORK_SIGNATURES.items():
        if any(sig in corpus for sig in signatures):
            summary.frameworks.append(framework)
    if summary.frameworks:
        summary.facts.append(f"Framework signatures found: {', '.join(summary.frameworks)}.")

    for db, signatures in _DATABASE_SIGNATURES.items():
        if any(re.search(rf"\b{re.escape(sig)}\b", corpus) for sig in signatures):
            summary.database = db
            summary.facts.append(f"Database dependency detected: {db}.")
            break

    for auth, signatures in _AUTH_SIGNATURES.items():
        if any(sig in corpus for sig in signatures):
            summary.authentication = auth
            summary.facts.append(f"Authentication mechanism signature detected: {auth}.")
            break

    file_paths = {f.path for f in files}
    for candidate in _ENTRY_POINT_CANDIDATES:
        if candidate in file_paths or any(p.endswith("/" + candidate) for p in file_paths):
            summary.entry_points.append(candidate)
    if summary.entry_points:
        summary.facts.append(f"Likely entry point(s): {', '.join(summary.entry_points)}.")
    else:
        summary.uncertain.append("No conventional entry point file was found by filename heuristics.")

    for test_fw, marker_files in _TEST_FRAMEWORK_FILES.items():
        if any(m in file_paths or any(p.endswith("/" + m) for p in file_paths) for m in marker_files):
            summary.test_framework = test_fw
            summary.facts.append(f"Test framework indicator found: {test_fw}.")
            break
    if any(f.is_test for f in files) and not summary.test_framework:
        summary.uncertain.append("Test files exist but the specific test framework could not be determined.")

    for file_path, method, route_path in routes:
        summary.api_entry_points.append(f"{method} {route_path} ({file_path})")
    if summary.api_entry_points:
        summary.facts.append(f"Detected {len(summary.api_entry_points)} API route declaration(s).")

    top_dirs: dict[str, int] = {}
    for f in files:
        parts = f.path.split("/")
        if len(parts) > 1:
            top_dirs[parts[0]] = top_dirs.get(parts[0], 0) + 1
    summary.important_directories = [d for d, _ in sorted(top_dirs.items(), key=lambda kv: -kv[1])[:12]]

    if "package.json" in file_paths:
        summary.build_instructions = "npm install && npm run dev (inferred from package.json)"
    elif "requirements.txt" in file_paths:
        summary.build_instructions = "pip install -r requirements.txt (inferred from requirements.txt)"
    elif "pyproject.toml" in file_paths:
        summary.build_instructions = "pip install -e . (inferred from pyproject.toml)"
    else:
        summary.uncertain.append("Build/run instructions could not be determined from repository files.")

    if not summary.purpose:
        pieces = []
        if summary.frameworks:
            pieces.append(f"a {'/'.join(summary.frameworks)} application")
        else:
            pieces.append(f"a {'/'.join(summary.languages[:2]) or 'software'} project")
        if summary.database:
            pieces.append(f"using {summary.database}")
        if summary.api_entry_points:
            pieces.append("exposing an HTTP API")
        summary.inferences.append(
            "Repository appears to be " + " ".join(pieces) + " (inferred from file structure and dependencies)."
        )

    return summary


LLM_SUMMARY_SYSTEM_PROMPT = """You are analyzing a software repository's structure to write a short, \
grounded summary. You will be given rule-derived FACTS about the repository (languages, frameworks, \
detected entry points, config files, and a README excerpt if available). \
Write ONLY:
1. A 2-4 sentence "purpose" paragraph describing what the project most likely does.
2. Up to 5 additional INFERENCE bullet points (things reasonably implied by the facts but not \
directly proven).
3. Any UNCERTAIN items you cannot determine from the given facts.

Never invent file names, function names, or capabilities not supported by the facts given. \
Respond as JSON: {"purpose": str, "inferences": [str], "uncertain": [str]}."""


def enhance_summary_with_llm(summary: RepositorySummaryData, readme_excerpt: str | None) -> RepositorySummaryData:
    """Best-effort LLM enhancement. Any failure here is swallowed by the
    caller (pipeline.py) -- a missing/broken LLM provider must never fail
    repository ingestion."""
    from app.services.llm.base import ChatMessage
    from app.services.llm.factory import get_llm_provider

    provider = get_llm_provider()
    facts_blob = "\n".join(f"- {f}" for f in summary.facts)
    user_content = f"FACTS:\n{facts_blob}\n\nLanguages: {summary.languages}\nFrameworks: {summary.frameworks}\n"
    if readme_excerpt:
        user_content += f"\nREADME excerpt:\n{readme_excerpt[:3000]}\n"

    response = provider.complete(
        messages=[ChatMessage(role="user", content=user_content)],
        system=LLM_SUMMARY_SYSTEM_PROMPT,
        max_tokens=800,
        temperature=0.1,
    )
    if not response.content:
        return summary

    parsed = _extract_json(response.content)
    if not parsed:
        return summary

    if parsed.get("purpose"):
        summary.purpose = parsed["purpose"]
    if parsed.get("inferences"):
        summary.inferences.extend(parsed["inferences"])
    if parsed.get("uncertain"):
        summary.uncertain.extend(parsed["uncertain"])
    return summary


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
