"""ComfyUI AI Builder — Workflow Store."""

import shutil
from pathlib import Path

from . import config
from .utils import load_json, save_json, timestamp


def save_current(workflow: dict):
    """Save workflow as the current active workflow."""
    save_json(config.CURRENT_WORKFLOW, workflow)


def load_current() -> dict:
    """Load the current active workflow."""
    return load_json(config.CURRENT_WORKFLOW)


def load_workflow(name: str) -> dict:
    """Load a workflow by name ('current', template name, or draft name)."""
    if name == "current":
        return load_current()

    # Check templates
    template_path = config.TEMPLATES_DIR / f"{name}.json"
    if template_path.exists():
        return load_json(template_path)

    # Check drafts
    draft_path = config.DRAFTS_DIR / f"{name}.json"
    if draft_path.exists():
        return load_json(draft_path)

    # Check if it's a direct path
    direct = Path(name)
    if direct.exists():
        return load_json(direct)

    return {}


def save_draft(name: str, workflow: dict):
    """Save workflow as a named draft."""
    path = config.DRAFTS_DIR / f"{name}.json"
    save_json(path, workflow)


def save_template(name: str, workflow: dict):
    """Save workflow as a named template."""
    path = config.TEMPLATES_DIR / f"{name}.json"
    save_json(path, workflow)


def list_all() -> dict:
    """List all available workflows (current, templates, drafts)."""
    result = {
        "current": config.CURRENT_WORKFLOW.exists(),
        "templates": [],
        "drafts": [],
    }

    if config.TEMPLATES_DIR.exists():
        result["templates"] = sorted(
            f.stem for f in config.TEMPLATES_DIR.glob("*.json")
        )

    if config.DRAFTS_DIR.exists():
        result["drafts"] = sorted(
            f.stem for f in config.DRAFTS_DIR.glob("*.json")
        )

    return result


def export_workflow(workflow_name: str, export_name: str) -> dict:
    """Export a workflow + its outputs to a named directory."""
    wf = load_workflow(workflow_name)
    if not wf:
        return {"status": "error", "error": f"Workflow '{workflow_name}' not found"}

    export_dir = config.BUILDER_DIR / "exports" / export_name
    export_dir.mkdir(parents=True, exist_ok=True)

    save_json(export_dir / "workflow.json", wf)

    # Copy latest outputs if they exist
    for subdir in ["images", "video"]:
        src = config.OUT_DIR / subdir
        if src.exists() and any(src.iterdir()):
            dst = export_dir / subdir
            dst.mkdir(exist_ok=True)
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)

    return {
        "status": "success",
        "export_path": str(export_dir),
        "workflow": str(export_dir / "workflow.json"),
    }


def last_run_log() -> dict | None:
    """Load the most recent run log."""
    if not config.RUNS_DIR.exists():
        return None

    logs = sorted(config.RUNS_DIR.glob("*.json"), reverse=True)
    if not logs:
        return None

    return load_json(logs[0])


MAX_RUN_LOGS = 100


def save_run_log(log: dict):
    """Save a run log with timestamp-based filename. Rotates to keep last 100."""
    ts = timestamp()
    path = config.RUNS_DIR / f"{ts}.json"
    save_json(path, log)
    _rotate_run_logs()
    return path


def _rotate_run_logs():
    """Delete oldest run logs if count exceeds MAX_RUN_LOGS."""
    if not config.RUNS_DIR.exists():
        return
    logs = sorted(config.RUNS_DIR.glob("*.json"))
    excess = len(logs) - MAX_RUN_LOGS
    if excess > 0:
        for old_log in logs[:excess]:
            old_log.unlink()
