"""Implementation-independent capabilities used by the repair agent."""

from typing import Any, Protocol

from core.models import TestResult


class ChatClient(Protocol):
    """Provide model replies for a conversation."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the model's text reply to the messages."""
        ...


class RepairToolsPort(Protocol):
    """Read, edit, and test a copied project through bounded tools."""

    def read_file(self, path: str) -> str:
        """Return the contents of a workspace-relative file."""
        ...

    def edit_file(self, path: str, content: str) -> str:
        """Replace a workspace-relative file and return an observation."""
        ...

    def run_tests(self) -> TestResult:
        """Run the copied project's tests in a sandbox."""
        ...


class TraceRecorder(Protocol):
    """Optionally record public repair events."""

    def record(self, event: str, payload: dict[str, Any]) -> None:
        """Record an event name and its public data."""
        ...
