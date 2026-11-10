"""Bounded UTF-8 file operations for a disposable repair workspace."""

from pathlib import Path, PureWindowsPath

from adapters.sandbox import runner
from core.models import TestResult


def safe_path(workspace: Path, requested_path: str) -> Path:
    """Reject absolute paths, traversal, and resolved workspace escapes."""
    windows = PureWindowsPath(requested_path)
    relative = Path(requested_path.replace("\\", "/"))
    if (not requested_path or relative.is_absolute() or windows.drive
            or windows.root or ".." in relative.parts):
        raise ValueError("Path must be relative without traversal")
    root = Path(workspace).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Path escapes the workspace")
    return resolved


class RepairTools:
    """Expose only file reads, file edits, and sandboxed tests."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.changed_files: list[str] = []

    def read_file(self, path: str) -> str:
        """Read a UTF-8 file inside the workspace."""
        return safe_path(self.workspace, path).read_text(encoding="utf-8")

    def edit_file(self, path: str, content: str) -> str:
        """Write UTF-8 content and record the relative path once."""
        target = safe_path(self.workspace, path)
        target.write_text(content, encoding="utf-8")
        relative = target.relative_to(self.workspace).as_posix()
        if relative not in self.changed_files:
            self.changed_files.append(relative)
        return f"Updated {relative}"

    def run_tests(self) -> TestResult:
        """Delegate evaluation execution exclusively to the Docker runner."""
        return runner.run_tests(self.workspace)
