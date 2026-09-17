"""Test framework detection + execution (section 25, 29).

Detection is filename/manifest based (real signals, not guesses); execution
always happens through docker_sandbox.run_in_sandbox so test code -- which
may itself be buggy or, worse, attacker-modified in a compromised repo --
never runs on the host.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.services.sandbox.docker_sandbox import SandboxResult, run_in_sandbox


@dataclass
class TestFrameworkInfo:
    framework: str
    command: str
    image: str


def detect_test_framework(workspace_dir: Path, settings: Settings) -> TestFrameworkInfo | None:
    files = {p.name for p in workspace_dir.glob("*")}
    has_py_tests = any(workspace_dir.rglob("test_*.py")) or any(workspace_dir.rglob("*_test.py"))

    if "pytest.ini" in files or "conftest.py" in files or (has_py_tests and _requirements_mentions(workspace_dir, "pytest")):
        return TestFrameworkInfo("pytest", "pytest -q --tb=short", settings.sandbox_image_python)
    if "pyproject.toml" in files and _pyproject_mentions_pytest(workspace_dir):
        return TestFrameworkInfo("pytest", "pytest -q --tb=short", settings.sandbox_image_python)
    if has_py_tests:
        return TestFrameworkInfo(
            "unittest", "python -m unittest discover -s . -p test_*.py -q", settings.sandbox_image_python
        )

    package_json = workspace_dir / "package.json"
    if package_json.exists():
        content = package_json.read_text(encoding="utf-8", errors="replace")
        if '"vitest"' in content:
            return TestFrameworkInfo("Vitest", "npx vitest run --reporter=default", settings.sandbox_image_node)
        if '"jest"' in content:
            return TestFrameworkInfo("Jest", "npx jest --ci", settings.sandbox_image_node)
        if '"test"' in content:
            return TestFrameworkInfo("npm-test", "npm test --silent", settings.sandbox_image_node)

    if "pom.xml" in files:
        return TestFrameworkInfo("JUnit/Maven", "mvn -q -B test", "maven:3.9-eclipse-temurin-17")
    if "build.gradle" in files or "build.gradle.kts" in files:
        return TestFrameworkInfo("JUnit/Gradle", "gradle test --console=plain", "gradle:8-jdk17")

    return None


def _requirements_mentions(workspace_dir: Path, package: str) -> bool:
    req = workspace_dir / "requirements.txt"
    if req.exists():
        return package in req.read_text(encoding="utf-8", errors="replace").lower()
    return False


def _pyproject_mentions_pytest(workspace_dir: Path) -> bool:
    pyproject = workspace_dir / "pyproject.toml"
    if pyproject.exists():
        return "pytest" in pyproject.read_text(encoding="utf-8", errors="replace").lower()
    return False


@dataclass
class TestExecutionOutcome:
    sandbox_result: SandboxResult
    framework: str
    command: str
    passed_count: int | None
    failed_count: int | None


def run_tests(
    workspace_dir: Path,
    settings: Settings,
    framework_info: TestFrameworkInfo | None = None,
    test_path: str | None = None,
) -> TestExecutionOutcome:
    info = framework_info or detect_test_framework(workspace_dir, settings)
    if info is None:
        raise ValueError("No supported test framework could be detected in this workspace.")

    command = info.command
    if test_path:
        command = f"{command} {test_path}"

    result = run_in_sandbox(command, workspace_dir, settings, image=info.image)
    passed, failed = _parse_counts(info.framework, result.stdout)
    return TestExecutionOutcome(
        sandbox_result=result, framework=info.framework, command=command, passed_count=passed, failed_count=failed
    )


_PYTEST_SUMMARY = re.compile(r"(\d+)\s+passed(?:,\s*(\d+)\s+failed)?")
_PYTEST_FAILED_ONLY = re.compile(r"(\d+)\s+failed")
_JEST_SUMMARY = re.compile(r"Tests:\s+(?:(\d+)\s+failed,\s*)?(?:(\d+)\s+skipped,\s*)?(\d+)\s+passed")
_JUNIT_SUMMARY = re.compile(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)")


def _parse_counts(framework: str, output: str) -> tuple[int | None, int | None]:
    if framework in ("pytest",):
        m = _PYTEST_SUMMARY.search(output)
        if m:
            passed = int(m.group(1))
            failed = int(m.group(2)) if m.group(2) else 0
            return passed, failed
        m2 = _PYTEST_FAILED_ONLY.search(output)
        if m2:
            return 0, int(m2.group(1))
    elif framework in ("Jest", "Vitest"):
        m = _JEST_SUMMARY.search(output)
        if m:
            failed = int(m.group(1)) if m.group(1) else 0
            passed = int(m.group(3))
            return passed, failed
    elif framework.startswith("JUnit"):
        m = _JUNIT_SUMMARY.search(output)
        if m:
            total, failures, errors = int(m.group(1)), int(m.group(2)), int(m.group(3))
            failed = failures + errors
            return total - failed, failed
    return None, None
