"""Select an instructor case and repair only its disposable copy."""

from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

from core.models import RepairResult
from core.repair_agent import RepairAgent


CASES = frozenset({"arithmetic", "balanced_brackets", "median", "multi_function", "unique_words"})


class RepairService:
    """Validate case selection and orchestrate injected workspace and agent factories."""

    def __init__(self, create_workspace: Callable[[str], Path],
                 create_agent: Callable[[str, Path], RepairAgent],
                 on_event: Callable[[dict], None] | None = None):
        self.create_workspace = create_workspace
        self.create_agent = create_agent
        self.on_event = on_event

    def repair(self, project: str) -> RepairResult:
        """Reject arbitrary paths before copying and repairing an allowed case."""
        windows = PureWindowsPath(project)
        path = PurePosixPath(project.replace("\\", "/"))
        if (windows.drive or windows.root or path.is_absolute()
                or ".." in path.parts or len(path.parts) != 2
                or path.parts[0] != "evals" or path.parts[1] not in CASES):
            raise ValueError("Select one of the five instructor projects as evals/<case>")
        case = path.parts[1]
        evals = Path(__file__).resolve().parents[1] / "evals"
        source = evals / case
        if not source.is_dir() or source.is_symlink() or source.resolve().parent != evals.resolve():
            raise ValueError("Project must be a supplied directory inside evals")
        workspace = self.create_workspace(case)
        files = sorted(p.relative_to(workspace).as_posix()
                       for p in workspace.rglob("*") if p.is_file())
        agent = self.create_agent(case, workspace)
        if self.on_event:
            self.on_event({"event": "repair_started", "case": case})
        result = agent.run(case, files, workspace)
        if self.on_event:
            self.on_event(result.trace[-1])
        return result
