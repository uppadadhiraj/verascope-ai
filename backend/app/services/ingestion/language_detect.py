"""Extension-based language detection (section 10).

Simple and deterministic on purpose: the spec's language list is small and
extension mapping is unambiguous for it. Adding a language later is a
one-line addition to EXTENSION_LANGUAGE_MAP.
"""
from __future__ import annotations

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".rst": "markdown",
    ".sh": "shell",
    ".bash": "shell",
    ".ps1": "powershell",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
}

# Languages with real AST/structured symbol extraction (see parser/).
# Everything else still gets scanned, chunked and embedded -- just without
# function/class-level symbol extraction.
PARSEABLE_LANGUAGES = {"python", "javascript", "typescript", "java", "c", "cpp"}

CONFIG_FILENAMES = {
    "package.json", "package-lock.json", "pyproject.toml", "requirements.txt",
    "poetry.lock", "pipfile", "setup.py", "setup.cfg", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", ".env.example", "tsconfig.json",
    "webpack.config.js", "vite.config.ts", "vite.config.js", "alembic.ini",
    "pom.xml", "build.gradle", "cmakelists.txt", "makefile", ".gitignore",
    "nginx.conf", "procfile",
}

DOC_EXTENSIONS = {".md", ".rst", ".txt"}


def detect_language(file_path: str) -> str | None:
    lower = file_path.lower()
    for ext, lang in EXTENSION_LANGUAGE_MAP.items():
        if lower.endswith(ext):
            return lang
    return None


def is_config_file(file_path: str) -> bool:
    from pathlib import PurePosixPath

    name = PurePosixPath(file_path).name.lower()
    return name in CONFIG_FILENAMES


def is_documentation_file(file_path: str) -> bool:
    lower = file_path.lower()
    return any(lower.endswith(ext) for ext in DOC_EXTENSIONS)


def is_test_file(file_path: str) -> bool:
    lower = file_path.lower()
    parts = lower.replace("\\", "/").split("/")
    if any(p in ("test", "tests", "__tests__", "spec") for p in parts):
        return True
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
        or name.endswith("test.java")
    )
