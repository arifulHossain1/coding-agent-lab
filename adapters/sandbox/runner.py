"""Create disposable case copies and run their tests only through Docker."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from core.models import TestResult


def create_workspace(case: str) -> Path:
    """Copy one supplied evaluation case into a unique home-directory folder."""
    evals = Path(__file__).resolve().parents[2] / "evals"
    if not case or case in {".", ".."} or any(c in case for c in "/\\:"):
        raise ValueError("Select a case name, not a path")
    source = evals / case
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Unknown evaluation case")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Evaluation cases must not contain symlinks")
    cache = Path.home() / ".cache" / "coding-agent-lab"
    cache.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"{case}-", dir=cache))
    shutil.copytree(source, workspace, dirs_exist_ok=True)
    workspace.chmod(0o755)
    return workspace


def run_tests(workspace: Path) -> TestResult:
    """Run pytest in a short-lived, offline container with one read-only mount."""
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    command = [
        "docker", "run", "--rm", "--network", "none",
        "--mount", f"type=bind,source={workspace},target=/workspace,readonly",
        "--workdir", "/workspace", "coding-agent-lab-runner",
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return TestResult(False, "Docker test run timed out after 60 seconds.", 124)
    except OSError as exc:
        return TestResult(False, f"Unable to start Docker: {exc}", 127)
    return TestResult(result.returncode == 0, result.stdout + result.stderr, result.returncode)
