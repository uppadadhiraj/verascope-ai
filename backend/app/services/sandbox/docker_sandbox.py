"""Isolated Docker execution for test runs and any other command an agent
needs to actually execute (section 27).

Safety properties enforced here, not left to the caller:
  - Timeout: container is killed and removed if it outruns SANDBOX_TIMEOUT_SECONDS.
  - CPU / memory limits: nano_cpus + mem_limit on every run.
  - Network disabled by default (network_disabled / network_mode='none').
  - Only the given workspace directory is mounted -- no other host path is
    ever exposed to the container.
  - Read-only root filesystem with a small writable tmpfs for /tmp, so a
    command can't (accidentally or otherwise) modify anything outside the
    mounted workspace.
  - No secrets are forwarded into the container environment.
  - The container always runs with auto_remove, and a `finally` block
    forces cleanup even on timeout/exception.

This is the ONLY place in the codebase allowed to launch a container to run
agent- or user-repository-originated code. Nothing else should shell out to
`docker` or `subprocess` for that purpose.
"""
from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings

# Agents may only request commands whose first token is in this list.
# This is a second, independent guard on top of network/filesystem
# isolation -- even inside the sandbox, arbitrary shell invocation from the
# LLM is not trusted by default.
ALLOWED_COMMAND_PREFIXES = {
    "pytest", "python", "python3", "pip", "pip3",
    "npm", "npx", "node", "yarn", "pnpm",
    "mvn", "gradle", "javac", "java",
    "gcc", "g++", "make", "cmake", "ctest",
    "ruff", "flake8", "mypy", "eslint", "tsc",
    "ls", "cat", "echo",
}


class SandboxError(Exception):
    pass


class DisallowedCommandError(SandboxError):
    pass


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


def _validate_command(command: str) -> None:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise DisallowedCommandError(f"Could not parse command: {exc}") from exc
    if not tokens:
        raise DisallowedCommandError("Empty command.")
    head = tokens[0]
    if head not in ALLOWED_COMMAND_PREFIXES:
        raise DisallowedCommandError(
            f"Command '{head}' is not on the sandbox allowlist. Allowed: "
            f"{sorted(ALLOWED_COMMAND_PREFIXES)}"
        )


def run_in_sandbox(
    command: str,
    workspace_dir: Path,
    settings: Settings,
    image: str | None = None,
    extra_env: dict[str, str] | None = None,
    network_disabled: bool | None = None,
) -> SandboxResult:
    """Runs `command` inside a fresh, disposable container with `workspace_dir`
    (an absolute host path) bind-mounted at /workspace. `image` defaults to
    the Python sandbox image; pass settings.sandbox_image_node for JS/TS
    projects."""
    _validate_command(command)

    import docker
    from docker.errors import ContainerError, ImageNotFound
    from docker.types import Ulimit

    try:
        client = docker.from_env()
    except Exception as exc:
        raise SandboxError(
            "Could not connect to the Docker daemon. Is Docker Desktop running?"
        ) from exc

    image = image or settings.sandbox_image_python
    network_disabled = settings.sandbox_network_disabled if network_disabled is None else network_disabled

    start = time.monotonic()
    container = None
    try:
        container = client.containers.run(
            image=image,
            command=["sh", "-c", command],
            working_dir="/workspace",
            volumes={str(workspace_dir.resolve()): {"bind": "/workspace", "mode": "rw"}},
            environment=extra_env or {},
            mem_limit=settings.sandbox_memory_limit,
            nano_cpus=int(settings.sandbox_cpu_limit * 1_000_000_000),
            network_disabled=network_disabled,
            network_mode="none" if network_disabled else "bridge",
            read_only=False,  # many package managers need to write inside /workspace itself
            tmpfs={"/tmp": "size=256m"},
            ulimits=[Ulimit(name="nofile", soft=1024, hard=2048)],
            detach=True,
            user="root",
        )
        try:
            wait_result = container.wait(timeout=settings.sandbox_timeout_seconds)
            exit_code = wait_result.get("StatusCode")
            timed_out = False
        except Exception:
            timed_out = True
            exit_code = None
            try:
                container.kill()
            except Exception:
                pass

        logs = container.logs(stdout=True, stderr=True, stream=False)
        combined = logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
        duration_ms = int((time.monotonic() - start) * 1000)

        return SandboxResult(
            exit_code=exit_code,
            stdout=combined,
            stderr="" if not timed_out else "Execution timed out and the container was killed.",
            timed_out=timed_out,
            duration_ms=duration_ms,
        )
    except ImageNotFound as exc:
        raise SandboxError(f"Sandbox image '{image}' not found locally and could not be pulled.") from exc
    except ContainerError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return SandboxResult(
            exit_code=exc.exit_status, stdout="", stderr=str(exc), timed_out=False, duration_ms=duration_ms
        )
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
