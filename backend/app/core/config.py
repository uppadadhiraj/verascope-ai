"""Central application configuration.

All runtime configuration is read from environment variables (via .env in
development). Nothing here should be hardcoded per-deployment; this is the
one place the rest of the app is allowed to reach for config.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "development"
    secret_key: str = "insecure-dev-secret-change-me"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"

    # --- Database ---
    database_url: str = "postgresql+psycopg://verascope:verascope@localhost:5432/verascope"

    # --- Vector store ---
    chroma_persist_dir: str = "./data/chroma"

    # --- Storage ---
    repo_storage_dir: str = "./data/repos"
    workspace_storage_dir: str = "./data/workspaces"

    # --- LLM provider ---
    llm_provider: str = "anthropic"  # anthropic | openai | ollama
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"  # plain "llama3" (3.0) has no tool-calling support in Ollama

    embedding_provider: str = "local"  # local (sentence-transformers) | openai
    openai_embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "all-MiniLM-L6-v2"

    # --- GitHub ---
    github_token: str = ""

    # --- Sandbox ---
    sandbox_image_python: str = "python:3.12-slim"
    sandbox_image_node: str = "node:20-slim"
    sandbox_timeout_seconds: int = 120
    sandbox_memory_limit: str = "512m"
    sandbox_cpu_limit: float = 1.0
    sandbox_network_disabled: bool = True
    sandbox_max_iterations: int = 5

    # --- Ingestion limits ---
    max_file_size_bytes: int = 1_000_000  # 1 MB: files larger than this are skipped for parsing/embedding
    max_repo_files: int = 20_000
    ignored_dirs: str = (
        ".git,node_modules,__pycache__,venv,.venv,env,dist,build,target,"
        "coverage,.cache,.idea,.vscode,.next,.nuxt,vendor,.pytest_cache,"
        ".mypy_cache,.ruff_cache,egg-info"
    )
    ignored_extensions: str = (
        ".png,.jpg,.jpeg,.gif,.bmp,.ico,.svg,.pdf,.zip,.tar,.gz,.7z,.rar,"
        ".mp4,.mp3,.wav,.avi,.mov,.woff,.woff2,.ttf,.eot,.otf,.exe,.dll,"
        ".so,.dylib,.bin,.pyc,.class,.jar,.lock"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ignored_dir_set(self) -> set[str]:
        return {d.strip() for d in self.ignored_dirs.split(",") if d.strip()}

    @property
    def ignored_extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.ignored_extensions.split(",") if e.strip()}

    def repo_path(self, repository_id: str) -> Path:
        return Path(self.repo_storage_dir).resolve() / repository_id

    def workspace_path(self, workspace_id: str) -> Path:
        return Path(self.workspace_storage_dir).resolve() / workspace_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
