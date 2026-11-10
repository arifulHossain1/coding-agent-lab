"""Terminal entry point for scripted sandboxed repairs."""

import argparse
import json
import sys
from textwrap import indent

from bootstrap import build_service


def _display_text(value: object) -> str:
    """Keep labels on one line and avoid terminal control characters."""
    text = str(value)
    return "".join(character if character.isprintable() else " " for character in text)


def _format_event(event: dict) -> str:
    """Render trace data for display without accepting or executing an action."""
    kind = event.get("event")
    if kind == "repair_started":
        return f"START  Project: {_display_text(event.get('case', 'unknown'))}"
    if kind == "model_response":
        number = _display_text(event.get("decision", "?"))
        try:
            action = json.loads(event.get("response", ""))
        except (ValueError, TypeError, RecursionError):
            action = None
        if not isinstance(action, dict):
            return f"ACTION {number}: Unreadable model response (RepairAgent will validate)"
        tool = action.get("tool")
        label = _display_text(tool) if isinstance(tool, str) else "Unspecified tool"
        if isinstance(action.get("path"), str):
            label += f" | {_display_text(action['path'])}"
        if isinstance(action.get("summary"), str):
            label += f" | {_display_text(action['summary'])}"
        return f"ACTION {number}: {label}"
    if kind == "tool_result":
        heading = (f"RESULT {_display_text(event.get('tool', 'tool'))}: "
                   f"{_display_text(event.get('status', 'unknown')).upper()}")
        observation = event.get("observation", "")
        if event.get("tool") == "run_tests":
            try:
                test = json.loads(observation)
            except (ValueError, TypeError, RecursionError):
                test = None
            if isinstance(test, dict) and isinstance(test.get("passed"), bool):
                heading += f" | Tests {'PASSED' if test['passed'] else 'FAILED'}"
                heading += f" (exit {_display_text(test.get('returncode', '?'))})"
                observation = test.get("output", "")
        lines = str(observation).splitlines()
        body = "\n".join(_display_text(line) for line in lines)
        return heading + "\n" + indent(body or "(no output)", "    ")
    if kind == "repair_finished":
        outcome = "PASSED" if event.get("passed") else "FAILED"
        return f"FINISHED {outcome}: {_display_text(event.get('reason', ''))}"
    return _display_text(kind or "Trace event")


def _print_event(event: dict) -> None:
    """Print live events; display failures must not interrupt agent validation."""
    try:
        text = _format_event(event)
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="backslashreplace").decode(encoding), flush=True)
    except (ValueError, TypeError, RecursionError, OSError):
        # Presentation is optional; the original response still goes to RepairAgent.
        pass


def main(argv: list[str] | None = None) -> int:
    """Print live trace events and return a failing status for unsuccessful repairs."""
    parser = argparse.ArgumentParser(description="Repair an instructor evaluation case in Docker")
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser("repair", help="Repair a disposable copy of an eval project")
    repair.add_argument("project", help="Instructor project path, e.g. evals/arithmetic")
    repair.add_argument("--provider", choices=["scripted", "ollama"], default="scripted")
    repair.add_argument("--model", help="Ollama model (default: OLLAMA_MODEL or qwen2.5-coder:7b)")
    repair.add_argument("--temperature", type=float, default=0.0)
    commands.add_parser("ui", help="Start the local Gradio repair interface")
    args = parser.parse_args(argv)

    if args.command == "ui":
        from adapters.gradio_ui import create_demo

        create_demo().launch(server_name="127.0.0.1", share=False, inbrowser=False)
        return 0

    try:
        result = build_service(args.provider, _print_event,
                               model=args.model, temperature=args.temperature).repair(args.project)
    except (ValueError, OSError) as exc:
        print(f"Repair failed: {exc}", file=sys.stderr)
        return 1
    print("Workspace:", result.workspace)
    print("Changed files:")
    for relative in result.changed_files:
        print(f"    {_display_text(relative)}")
    if not result.changed_files:
        print("    (none)")
    test = result.last_test_result
    if test is None:
        print("Final sandboxed tests: NOT RUN")
    else:
        print(f"Final sandboxed tests: {'PASSED' if test.passed else 'FAILED'} (exit {test.returncode})")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
