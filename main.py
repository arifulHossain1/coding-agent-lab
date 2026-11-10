"""Terminal entry point for scripted sandboxed repairs."""

import argparse
from dataclasses import asdict
import json
import sys

from bootstrap import build_service


def main(argv: list[str] | None = None) -> int:
    """Print live trace events and return a failing status for unsuccessful repairs."""
    parser = argparse.ArgumentParser(description="Repair an instructor evaluation case in Docker")
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser("repair", help="Repair a disposable copy of an eval project")
    repair.add_argument("project", help="Instructor project path, e.g. evals/arithmetic")
    repair.add_argument("--provider", choices=["scripted"], default="scripted")
    commands.add_parser("ui", help="Start the local Gradio repair interface")
    args = parser.parse_args(argv)

    if args.command == "ui":
        from adapters.gradio_ui import create_demo

        create_demo().launch(server_name="127.0.0.1", share=False, inbrowser=False)
        return 0

    def print_event(event: dict) -> None:
        print(json.dumps(event), flush=True)

    try:
        result = build_service(args.provider, print_event).repair(args.project)
    except (ValueError, OSError) as exc:
        print(f"Repair failed: {exc}", file=sys.stderr)
        return 1
    print("Workspace:", result.workspace)
    print("Changed files:", json.dumps(result.changed_files))
    print("Final sandboxed test result:", json.dumps(
        asdict(result.last_test_result) if result.last_test_result else None
    ))
    print("Repair passed:", result.passed)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
