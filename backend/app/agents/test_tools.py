"""Sandboxed execution tools for the Test Agent (section 25, 28, 29).

Everything here runs through docker_sandbox.run_in_sandbox against
`ctx.workspace_dir` -- never the host, never the indexed repository clone
directly.
"""
from __future__ import annotations

from app.agents.context import AgentContext
from app.services.llm.base import ToolSpec
from app.services.sandbox.docker_sandbox import DisallowedCommandError, SandboxError, run_in_sandbox
from app.services.sandbox.test_runner import detect_test_framework, run_tests


def _require_workspace(ctx: AgentContext) -> None:
    if ctx.workspace_dir is None:
        raise ValueError("No workspace is attached to this agent context -- cannot execute commands.")


def tool_run_tests(ctx: AgentContext, args: dict) -> dict:
    _require_workspace(ctx)
    test_path = args.get("test_path")
    try:
        outcome = run_tests(ctx.workspace_dir, ctx.settings, test_path=test_path)
    except ValueError as exc:
        return {"error": str(exc)}
    except SandboxError as exc:
        return {"error": str(exc)}

    return {
        "framework": outcome.framework,
        "command": outcome.command,
        "exit_code": outcome.sandbox_result.exit_code,
        "passed_count": outcome.passed_count,
        "failed_count": outcome.failed_count,
        "timed_out": outcome.sandbox_result.timed_out,
        "duration_ms": outcome.sandbox_result.duration_ms,
        "output": outcome.sandbox_result.stdout[-6000:],
    }


def tool_detect_test_framework(ctx: AgentContext, args: dict) -> dict:
    _require_workspace(ctx)
    info = detect_test_framework(ctx.workspace_dir, ctx.settings)
    if info is None:
        return {"framework": None, "note": "No supported test framework was detected."}
    return {"framework": info.framework, "command": info.command}


def tool_run_command(ctx: AgentContext, args: dict) -> dict:
    """A constrained command runner -- e.g. `pip install -r requirements.txt`
    before tests, or a linter. Still bound by the sandbox's own allowlist
    (docker_sandbox.ALLOWED_COMMAND_PREFIXES)."""
    _require_workspace(ctx)
    command = args["command"]
    try:
        result = run_in_sandbox(command, ctx.workspace_dir, ctx.settings)
    except DisallowedCommandError as exc:
        return {"error": str(exc)}
    except SandboxError as exc:
        return {"error": str(exc)}
    return {
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
        "output": result.stdout[-6000:],
        "stderr": result.stderr,
    }


TEST_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="detect_test_framework",
        description="Detect which test framework this workspace uses (pytest, Jest, JUnit, etc.).",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="run_tests",
        description="Run the workspace's test suite inside an isolated sandbox container and get pass/fail counts and output.",
        parameters={"type": "object", "properties": {"test_path": {"type": "string"}}},
    ),
    ToolSpec(
        name="run_command",
        description="Run a single allow-listed command (e.g. 'pip install -r requirements.txt', 'npm install', a linter) inside the sandbox.",
        parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    ),
]

TEST_TOOL_HANDLERS = {
    "detect_test_framework": tool_detect_test_framework,
    "run_tests": tool_run_tests,
    "run_command": tool_run_command,
}
