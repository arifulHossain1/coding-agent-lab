"""Shared data containers for repair actions and results."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TestResult:
    """The outcome and captured output of a sandboxed test run."""

    __test__ = False

    passed: bool
    output: str
    returncode: int


@dataclass
class ModelAction:
    """One requested tool call with an optional public summary."""

    tool: str
    arguments: dict[str, Any]
    summary: str | None = None


@dataclass
class RepairResult:
    """The repair outcome, public trace, and disposable workspace."""

    passed: bool
    trace: list[dict[str, Any]]
    changed_files: list[str]
    workspace: Path
    last_test_result: TestResult | None = None
