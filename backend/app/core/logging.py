"""Structured logging setup.

Security-sensitive values (tokens, passwords, API keys) must never be passed
into log calls. Call sites are responsible for that; this module only wires
up the renderer.
"""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(app_env: str = "development") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if app_env == "development":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


REDACT_KEYS = {
    "password",
    "hashed_password",
    "api_key",
    "secret_key",
    "token",
    "access_token",
    "github_token",
    "anthropic_api_key",
    "openai_api_key",
}


def redact(data: dict) -> dict:
    """Shallow-redact known-sensitive keys before logging a dict."""
    return {k: ("***REDACTED***" if k.lower() in REDACT_KEYS else v) for k, v in data.items()}
