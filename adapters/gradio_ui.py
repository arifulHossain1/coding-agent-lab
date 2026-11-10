"""Local presentation of the existing scripted repair service."""

import json
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

import gradio as gr

from bootstrap import build_service


PROJECTS = ["arithmetic", "balanced_brackets", "median", "multi_function", "unique_words"]


def _repair(case: str) -> tuple[str, str, str, str | None]:
    """Present a service result and archive its disposable workspace."""
    if case not in PROJECTS:
        raise gr.Error("Select one of the five supplied projects")
    try:
        result = build_service(provider="scripted").repair(f"evals/{case}")
        workspace = result.workspace.resolve()
        changed = []
        for relative in result.changed_files:
            path = (workspace / relative).resolve()
            if not path.is_relative_to(workspace):
                raise ValueError("Changed file escapes the disposable workspace")
            changed.append(f"{relative}\n{path.read_text(encoding='utf-8')}")
        test = result.last_test_result
        output = f"Repair passed: {result.passed}\n"
        if test is None:
            output += "No sandboxed test result was returned."
        else:
            output += f"Docker test passed: {test.passed}\nReturn code: {test.returncode}\n\n{test.output}"
        download_dir = Path(tempfile.mkdtemp(prefix="repair-download-"))
        archive = download_dir / f"{case}-workspace.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
            for path in sorted(workspace.rglob("*")):
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(workspace):
                    bundle.write(path, path.relative_to(workspace).as_posix())
        return (
            "\n".join(json.dumps(event, ensure_ascii=False) for event in result.trace),
            "\n\n".join(changed) or "No files changed.",
            output,
            str(archive),
        )
    except (OSError, ValueError) as exc:
        raise gr.Error(f"Unable to present the repair: {exc}") from exc


def create_demo() -> gr.Blocks:
    """Build project selection and read-only repair results without launching."""
    with gr.Blocks(analytics_enabled=False, title="Python Repair Agent") as demo:
        gr.Markdown("# Python Repair Agent\nSelect a supplied project to repair a disposable copy using the scripted provider.")
        project = gr.Dropdown(choices=PROJECTS, value="arithmetic", label="Project", allow_custom_value=False)
        start = gr.Button("Start repair", variant="primary")
        trace = gr.Textbox(label="Visible repair trace", lines=14, interactive=False)
        changed = gr.Textbox(label="Changed relative files and updated contents", lines=16, interactive=False)
        tests = gr.Textbox(label="Final Docker test result", lines=8, interactive=False)
        download = gr.File(label="Download workspace ZIP", interactive=False)
        start.click(_repair, inputs=project, outputs=[trace, changed, tests, download], concurrency_limit=1)
    return demo
