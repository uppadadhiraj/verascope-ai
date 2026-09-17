from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    agent_runs,
    approvals,
    auth,
    changes,
    chat,
    files,
    findings,
    git,
    repositories,
    tasks,
    test_runs,
)
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.app_env)

app = FastAPI(
    title="Verascope",
    description="AI Repository Intelligence & Autonomous Debugging Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(repositories.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(changes.router, prefix="/api")
app.include_router(test_runs.router, prefix="/api")
app.include_router(findings.router, prefix="/api")
app.include_router(approvals.router, prefix="/api")
app.include_router(agent_runs.router, prefix="/api")
app.include_router(git.router, prefix="/api")


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "service": "verascope-backend"}
