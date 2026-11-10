"""Repair-loop checks with scripted replies and inert fake tools."""

import pytest

from adapters.models.scripted import ScriptedClient
from core.models import RepairResult, TestResult
from core.repair_agent import RepairAgent


READ = '{"tool":"read_file","path":"source.py"}'
TEST = '{"tool":"run_tests"}'
EDIT = '{"tool":"edit_file","path":"source.py","content":"fixed"}'
FAIL = TestResult(False, "assertion failed", 1)
PASS = TestResult(True, "passed", 0)


class FakeTools:
    """Record calls and supply predetermined outcomes without execution."""

    def __init__(self, results=(), errors=()):
        self.results = iter(results)
        self.errors = set(errors)
        self.calls = []

    def _call(self, tool):
        self.calls.append(tool)
        if tool in self.errors:
            raise ValueError("Blocked or missing file")

    def read_file(self, path):
        self._call("read_file")
        return "original"

    def edit_file(self, path, content):
        self._call("edit_file")
        return "updated"

    def run_tests(self):
        self._call("run_tests")
        return next(self.results)


class RecordingClient(ScriptedClient):
    """Capture the conversation supplied on each decision."""

    def __init__(self, replies):
        super().__init__(replies)
        self.histories = []

    def chat(self, messages):
        self.histories.append(messages)
        return super().chat(messages)


def run(tmp_path, replies, tools):
    return RepairAgent(ScriptedClient(replies), tools).run("example", ["source.py"], tmp_path)


def test_success_and_history(tmp_path):
    client = RecordingClient([READ, TEST, EDIT, TEST])
    tools = FakeTools([FAIL, PASS])
    result = RepairAgent(client, tools).run("example", ["source.py"], tmp_path)
    assert result.passed
    assert result.last_test_result == PASS
    assert result.changed_files == ["source.py"]
    assert result.workspace == tmp_path
    assert tools.calls == ["read_file", "run_tests", "edit_file", "run_tests"]
    assert [event["event"] for event in result.trace] == (
        ["repair_started"] + ["model_response", "tool_result"] * 4 + ["repair_finished"]
    )
    assert client.histories[0][0]["role"] == "system"
    assert "example" in client.histories[0][1]["content"]
    assert "source.py" in client.histories[0][1]["content"]
    assert client.histories[1][2] == {"role": "assistant", "content": READ}
    assert "original" in client.histories[1][3]["content"]
    assert "assertion failed" in client.histories[2][-1]["content"]


@pytest.mark.parametrize("reply", [
    "not json", "{}", "[]", "null", "```json\n{}\n```", TEST + TEST,
    "prose " + TEST, TEST + " trailing prose",
    '{"tool":"run_tests","tool":"read_file"}',
    '{"tool":"shell"}', '{"tool":"read_file"}',
    '{"tool":"edit_file","path":"source.py"}',
    '{"tool":"run_tests","path":"source.py"}',
    '{"tool":"read_file","path":12}',
    '{"tool":"edit_file","path":"source.py","content":null}',
    '{"tool":"run_tests","summary":null}',
    '{"tool":"run_tests","extra":NaN}',
    '{"tool":[]}', '{"tool":"run_tests","summary":"a","summary":"b"}',
])
def test_invalid_reply_calls_no_tools(tmp_path, reply):
    tools = FakeTools()
    result = run(tmp_path, [reply], tools)
    assert not result.passed
    assert tools.calls == []
    assert "Invalid model response" in result.trace[-1]["reason"]


@pytest.mark.parametrize("prefix,results", [([], []), ([READ], []), ([TEST], [FAIL])])
def test_premature_edit_rejected_and_visible(tmp_path, prefix, results):
    tools = FakeTools(results)
    client = RecordingClient(prefix + [EDIT, "invalid"])
    result = RepairAgent(client, tools).run("example", [], tmp_path)
    assert not result.passed
    assert "edit_file" not in tools.calls
    assert result.changed_files == []
    assert any(event.get("status") == "policy_error" for event in result.trace)
    assert "Policy error" in client.histories[-1][-1]["content"]


def test_policy_error_can_recover(tmp_path):
    result = run(tmp_path, [EDIT, READ, TEST, EDIT, TEST], FakeTools([FAIL, PASS]))
    assert result.passed


def test_budget_exhaustion(tmp_path):
    client = RecordingClient([READ] * 9)
    tools = FakeTools()
    result = RepairAgent(client, tools).run("example", [], tmp_path)
    assert not result.passed
    assert len(client.histories) == len(tools.calls) == 8
    assert "budget exhausted" in result.trace[-1]["reason"]


def test_passing_baseline_is_not_repair(tmp_path):
    tools = FakeTools([PASS])
    result = run(tmp_path, [READ, TEST, EDIT], tools)
    assert not result.passed
    assert result.last_test_result == PASS
    assert "No reproducible bug" in result.trace[-1]["reason"]
    assert tools.calls == ["read_file", "run_tests"]


def test_client_error_returns_result(tmp_path):
    result = run(tmp_path, [], FakeTools())
    assert isinstance(result, RepairResult)
    assert not result.passed
    assert result.last_test_result is None
    assert "Client error" in result.trace[-1]["reason"]


@pytest.mark.parametrize("tool,prefix,replies,results", [
    ("read_file", [], [READ, TEST, EDIT], [FAIL]),
    ("run_tests", [READ], [TEST, EDIT], []),
    ("edit_file", [READ, TEST], [EDIT, TEST], [FAIL, PASS]),
])
def test_tool_errors_do_not_supply_repair_evidence(tmp_path, tool, prefix, replies, results):
    tools = FakeTools(results, errors=[tool])
    client = RecordingClient(prefix + replies + ["invalid"])
    result = RepairAgent(client, tools).run("example", [], tmp_path)
    assert not result.passed
    assert result.changed_files == []
    assert any(event.get("status") == "tool_error" for event in result.trace)
    assert any("Tool error" in message["content"]
               for history in client.histories for message in history if message["role"] == "user")


def test_repeated_edits_record_path_once(tmp_path):
    result = run(tmp_path, [READ, TEST, EDIT, EDIT, TEST], FakeTools([FAIL, PASS]))
    assert result.passed
    assert result.changed_files == ["source.py"]


def test_failed_verification_keeps_latest_result(tmp_path):
    result = run(tmp_path, [READ, TEST, EDIT, TEST], FakeTools([FAIL, FAIL]))
    assert not result.passed
    assert result.last_test_result == FAIL
