"""Validate model actions and control an eight-decision repair attempt."""

from dataclasses import asdict
import json
from pathlib import Path, PureWindowsPath

from core.models import ModelAction, RepairResult, TestResult
from core.ports import ChatClient, RepairToolsPort
from core.prompts import case_request, system_instruction, tool_result_message


def _unique_object(pairs: list[tuple]) -> dict:
    """Reject duplicate JSON keys instead of silently overwriting them."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _parse_action(raw: str) -> ModelAction:
    """Accept exactly one object with the selected tool's string fields."""
    if not isinstance(raw, str):
        raise ValueError("Model response must be text")
    data = json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)
    if not isinstance(data, dict):
        raise ValueError("Expected one JSON object")
    fields = {
        "read_file": {"path"},
        "edit_file": {"path", "content"},
        "run_tests": set(),
    }
    tool = data.get("tool")
    if not isinstance(tool, str) or tool not in fields:
        raise ValueError("Unknown or missing tool")
    required = fields[tool] | {"tool"}
    if not required <= data.keys() or data.keys() - (required | {"summary"}):
        raise ValueError("Missing or unexpected action fields")
    if any(not isinstance(value, str) for value in data.values()):
        raise ValueError("Action fields must be strings")
    return ModelAction(tool, {key: data[key] for key in fields[tool]}, data.get("summary"))


class RepairAgent:
    """Coordinate a model and bounded tools without executing project code."""

    def __init__(self, client: ChatClient, tools: RepairToolsPort):
        self.client = client
        self.tools = tools

    def run(self, case_name: str, files: list[str], workspace: Path) -> RepairResult:
        """Return a result for success, invalid actions, errors, or budget limits."""
        workspace = Path(workspace)
        messages = [
            {"role": "system", "content": system_instruction()},
            {"role": "user", "content": case_request(case_name, files)},
        ]
        trace = [{"event": "repair_started", "case": case_name}]
        changed_files: list[str] = []
        last_test_result = None
        read_succeeded = False
        failure_observed = False
        edited = False

        def finish(passed: bool, reason: str) -> RepairResult:
            trace.append({"event": "repair_finished", "passed": passed, "reason": reason})
            return RepairResult(passed, trace, changed_files, workspace, last_test_result)

        for decision in range(1, 9):
            try:
                raw = self.client.chat([message.copy() for message in messages])
            except Exception as exc:
                return finish(False, f"Client error: {exc}")
            trace.append({"event": "model_response", "decision": decision, "response": raw})
            try:
                action = _parse_action(raw)
            except (ValueError, TypeError, RecursionError) as exc:
                return finish(False, f"Invalid model response: {exc}")
            messages.append({"role": "assistant", "content": raw})
            status = "ok"
            test_passed = False
            if action.tool == "edit_file" and not (read_succeeded and failure_observed):
                status = "policy_error"
                observation = "Policy error: editing requires a successful file read and a failing test."
            else:
                try:
                    if action.tool == "read_file":
                        observation = self.tools.read_file(**action.arguments)
                        read_succeeded = True
                    elif action.tool == "edit_file":
                        observation = self.tools.edit_file(**action.arguments)
                        edited = True
                        relative = PureWindowsPath(action.arguments["path"]).as_posix()
                        if relative not in changed_files:
                            changed_files.append(relative)
                    else:
                        result = self.tools.run_tests()
                        if not isinstance(result, TestResult):
                            raise TypeError("run_tests must return TestResult")
                        last_test_result = result
                        observation = json.dumps(asdict(result))
                        test_passed = result.passed
                        if not result.passed:
                            failure_observed = True
                except Exception as exc:
                    status = "tool_error"
                    observation = f"Tool error: {exc}"
            trace.append({"event": "tool_result", "tool": action.tool,
                          "status": status, "observation": observation,
                          "summary": action.summary})
            messages.append({"role": "user", "content": tool_result_message(action.tool, observation)})
            if test_passed:
                if edited:
                    return finish(True, "Tests passed after a valid repair edit")
                return finish(False, "No reproducible bug: tests passed before any edit")
        return finish(False, "Eight-decision budget exhausted")
