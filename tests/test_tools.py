"""Safety checks using inert files and fake Docker execution."""

from pathlib import Path
import subprocess

import pytest

from adapters.sandbox import runner
from adapters.sandbox.repair_tools import RepairTools, safe_path
from core.models import TestResult


def test_read_and_edit_records_once(tmp_path):
    file = tmp_path / "sample.txt"
    file.write_text("original", encoding="utf-8")
    tools = RepairTools(tmp_path)
    assert tools.read_file("sample.txt") == "original"
    tools.edit_file("sample.txt", "café")
    tools.edit_file("./sample.txt", "updated")
    assert file.read_text(encoding="utf-8") == "updated"
    assert tools.changed_files == ["sample.txt"]


@pytest.mark.parametrize("path", ["/secret", "C:\\secret", "C:secret", "\\\\host\\share", "../secret", "folder/../secret", "..\\secret"])
def test_unsafe_paths_rejected(tmp_path, path):
    tools = RepairTools(tmp_path)
    with pytest.raises(ValueError):
        tools.read_file(path)
    with pytest.raises(ValueError):
        tools.edit_file(path, "bad")
    assert tools.changed_files == []


def test_resolved_escape_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires OS privileges")
    with pytest.raises(ValueError):
        safe_path(workspace, "link/secret.txt")


def test_resolved_escape_without_symlink_privileges(tmp_path, monkeypatch):
    original_resolve = Path.resolve
    escaped = tmp_path.parent / "outside.txt"

    def fake_resolve(path, *args, **kwargs):
        if path == tmp_path / "link.txt":
            return escaped
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(ValueError, match="escapes"):
        safe_path(tmp_path, "link.txt")


def test_run_tests_delegates(tmp_path, monkeypatch):
    calls = []
    expected = TestResult(False, "failure", 1)

    def fake_run(workspace):
        calls.append(workspace)
        return expected

    monkeypatch.setattr(runner, "run_tests", fake_run)
    assert RepairTools(tmp_path).run_tests() is expected
    assert calls == [tmp_path.resolve()]


@pytest.mark.parametrize("returncode", [0, 1, 5])
def test_docker_boundary(tmp_path, monkeypatch, returncode):
    def fake_run(command, **kwargs):
        assert command[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert command.count("--mount") == 1
        assert command[command.index("--mount") + 1] == (
            f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly"
        )
        assert command[-6:] == ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        assert kwargs == dict(capture_output=True, text=True, timeout=60)
        return subprocess.CompletedProcess(command, returncode, "out", "err")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.run_tests(tmp_path) == TestResult(returncode == 0, "outerr", returncode)


def test_workspace_copy_under_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    first = runner.create_workspace("arithmetic")
    second = runner.create_workspace("arithmetic")
    assert first != second
    assert first.parent == tmp_path / ".cache" / "coding-agent-lab"
    source = Path(runner.__file__).resolve().parents[2] / "evals" / "arithmetic"
    for original in source.rglob("*"):
        if original.is_file():
            copied = first / original.relative_to(source)
            assert copied.read_bytes() == original.read_bytes()
            copied.write_bytes(b"changed copy")
            assert original.read_bytes() != b"changed copy"


@pytest.mark.parametrize("case", ["", "..", "../arithmetic", "/arithmetic", "C:arithmetic", "missing-case"])
def test_invalid_case_rejected(case):
    with pytest.raises(ValueError):
        runner.create_workspace(case)
