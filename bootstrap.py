"""Assemble the scripted provider, Docker-backed tools, and repair service."""

from collections.abc import Callable
from dataclasses import asdict
import json
from pathlib import Path

from adapters.models.scripted import ScriptedClient
from adapters.models.ollama import OllamaClient
from adapters.sandbox.repair_tools import RepairTools
from adapters.sandbox.runner import create_workspace
from core.models import TestResult
from core.repair_agent import RepairAgent
from core.repair_service import RepairService


# Fixed replacements for the five teaching fixtures; never execute their code here.
REPAIRS = {
    "arithmetic": ("calculator.py", "return left - right", "return left + right"),
    "balanced_brackets": ("brackets.py", "            stack.pop()",
                          "            if stack.pop() != pairs[character]:\n                return False"),
    "median": ("statistics_tools.py", "    return ordered[middle]",
               "    if len(ordered) % 2 == 0:\n        return (ordered[middle - 1] + ordered[middle]) / 2\n    return ordered[middle]"),
    "multi_function": ("text_tools.py", "normalize_name(name).upper()", "normalize_name(name).title()"),
    "unique_words": ("word_tools.py", "sorted(set(text.lower().split()))",
                     "list(dict.fromkeys(text.lower().split()))"),
}


def scripted_replies(case: str, workspace: Path) -> list[str]:
    """Prepare separate inspection, reproduction, edit, and verification cards."""
    filename, old, new = REPAIRS[case]
    original = (workspace / filename).read_text(encoding="utf-8")
    if original.count(old) != 1:
        raise ValueError(f"Scripted repair does not match the supplied {case} fixture")
    actions = [
        {"tool": "read_file", "path": f"test_{filename}", "summary": "Inspect the test"},
        {"tool": "read_file", "path": filename, "summary": "Inspect the source"},
        {"tool": "run_tests", "summary": "Reproduce the failure"},
        {"tool": "edit_file", "path": filename, "content": original.replace(old, new),
         "summary": "Apply the focused repair"},
        {"tool": "run_tests", "summary": "Verify the repair"},
    ]
    return [json.dumps(action) for action in actions]


class _VisibleClient:
    """Publish model replies without validating or rejecting their actions."""

    def __init__(self, client, emit):
        self.client, self.emit = client, emit
        self.decision = 0
        self.summary = None

    def chat(self, messages):
        reply = self.client.chat(messages)
        self.decision += 1
        self.emit({"event": "model_response", "decision": self.decision, "response": reply})
        # Optional display metadata only; malformed replies still reach RepairAgent.
        self.summary = None
        try:
            metadata = json.loads(reply)
            if isinstance(metadata, dict) and isinstance(metadata.get("summary"), str):
                self.summary = metadata["summary"]
        except (ValueError, TypeError, RecursionError):
            pass
        return reply


class _VisibleTools:
    """Publish observations from the real tools as each call finishes."""

    def __init__(self, tools, client, emit):
        self.tools, self.client, self.emit = tools, client, emit

    def _call(self, tool, **arguments):
        try:
            result = getattr(self.tools, tool)(**arguments)
        except Exception as exc:
            self.emit({"event": "tool_result", "tool": tool, "status": "tool_error",
                       "observation": f"Tool error: {exc}", "summary": self.client.summary})
            raise
        observation = json.dumps(asdict(result)) if isinstance(result, TestResult) else result
        self.emit({"event": "tool_result", "tool": tool, "status": "ok",
                   "observation": observation, "summary": self.client.summary})
        return result

    def read_file(self, path: str) -> str:
        return self._call("read_file", path=path)

    def edit_file(self, path: str, content: str) -> str:
        return self._call("edit_file", path=path, content=content)

    def run_tests(self) -> TestResult:
        return self._call("run_tests")


def build_service(provider: str = "scripted",
                  on_event: Callable[[dict], None] | None = None,
                  model: str | None = None, temperature: float = 0.0) -> RepairService:
    """Connect the selected chat provider and real tools for each repair attempt."""
    if provider not in {"scripted", "ollama"}:
        raise ValueError("Provider must be scripted or ollama")

    def create_agent(case: str, workspace: Path) -> RepairAgent:
        client = (ScriptedClient(scripted_replies(case, workspace)) if provider == "scripted"
                  else OllamaClient(model=model, temperature=temperature))
        tools = RepairTools(workspace)
        if on_event:
            client = _VisibleClient(client, on_event)
            tools = _VisibleTools(tools, client, on_event)
        return RepairAgent(client, tools)

    return RepairService(create_workspace, create_agent, on_event)
