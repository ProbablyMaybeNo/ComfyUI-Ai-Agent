"""ComfyUI AI Builder — Installer / Dependency Manager."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, schema as schema_mod, store
from .utils import load_json, save_json


def load_allowlist() -> dict:
    """Load the allowlist of approved node packs."""
    return load_json(config.ALLOWLIST_FILE)


def load_installed() -> dict:
    """Load record of installed node packs."""
    return load_json(config.NODE_PACKS_FILE)


def _log_install(message: str):
    """Append a timestamped message to install.log."""
    config.INSTALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(config.INSTALL_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


def _find_python() -> str:
    """Find the Python executable for ComfyUI's environment."""
    # Check for embedded Python (portable ComfyUI installs)
    embedded = config.COMFYUI_PATH / "python_embeded" / "python.exe"
    if embedded.exists():
        return str(embedded)

    # Check for venv
    venv_python = config.COMFYUI_PATH / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)

    # Fall back to system Python
    return sys.executable


def install_pack(source: str, force_allow: bool = False) -> dict:
    """Install a custom node pack from a repo URL or allowlist name.

    Args:
        source: Pack name (looked up in allowlist) or full repo URL.
        force_allow: If True, allow URLs not in allowlist.

    Returns:
        Result dict with status and details.
    """
    allowlist = load_allowlist()
    packs = allowlist.get("packs", {})

    # Resolve source to repo URL
    if source in packs:
        pack_info = packs[source]
        repo_url = pack_info["repo"]
        pack_name = source
    elif source.startswith("https://"):
        if not force_allow:
            return {
                "status": "blocked",
                "error": f"URL not in allowlist: {source}",
                "hint": "Use --force-allow to override, or add to installs/allowlist.json",
            }
        repo_url = source
        pack_name = repo_url.rstrip("/").split("/")[-1]
    else:
        return {
            "status": "error",
            "error": f"Unknown pack '{source}'. Not in allowlist and not a URL.",
            "available": list(packs.keys()),
        }

    # Validate URL format
    if not repo_url.startswith("https://github.com/") and not repo_url.startswith("https://gitlab.com/"):
        return {"status": "error", "error": "Only GitHub and GitLab HTTPS URLs are allowed"}

    target_dir = config.CUSTOM_NODES_DIR / pack_name

    # Check if already installed
    if target_dir.exists():
        return {
            "status": "already_installed",
            "path": str(target_dir),
            "hint": "Use 'schema refresh' to check if nodes are loaded",
        }

    # Clone
    _log_install(f"INSTALL START: {pack_name} from {repo_url}")
    print(f"Cloning {repo_url} → {target_dir}...", file=sys.stderr)

    try:
        result = subprocess.run(
            ["git", "clone", repo_url, str(target_dir)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            _log_install(f"INSTALL FAILED (git clone): {result.stderr}")
            return {"status": "error", "error": f"git clone failed: {result.stderr}"}
    except subprocess.TimeoutExpired:
        _log_install(f"INSTALL FAILED (timeout): git clone {repo_url}")
        return {"status": "error", "error": "git clone timed out after 120s"}
    except FileNotFoundError:
        return {"status": "error", "error": "git not found. Install git and try again."}

    _log_install(f"CLONED: {pack_name} → {target_dir}")

    # Install Python requirements if present
    req_file = target_dir / "requirements.txt"
    if req_file.exists():
        python_exe = _find_python()
        print(f"Installing requirements with {python_exe}...", file=sys.stderr)
        _log_install(f"PIP INSTALL: {python_exe} -m pip install -r {req_file}")

        try:
            pip_result = subprocess.run(
                [python_exe, "-m", "pip", "install", "-r", str(req_file)],
                capture_output=True, text=True, timeout=300,
            )
            if pip_result.returncode != 0:
                _log_install(f"PIP INSTALL WARNING: {pip_result.stderr}")
                print(f"Warning: pip install had issues: {pip_result.stderr[:500]}", file=sys.stderr)
        except Exception as e:
            _log_install(f"PIP INSTALL ERROR: {e}")
            print(f"Warning: pip install failed: {e}", file=sys.stderr)

    # Update installed packs record
    installed = load_installed()
    installed[pack_name] = {
        "repo": repo_url,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "path": str(target_dir),
    }
    save_json(config.NODE_PACKS_FILE, installed)

    _log_install(f"INSTALL COMPLETE: {pack_name}")

    return {
        "status": "success",
        "pack": pack_name,
        "path": str(target_dir),
        "hint": "Restart ComfyUI server, then run 'schema refresh' to verify new nodes.",
    }


def check_missing() -> dict:
    """Check current workflow for nodes not present in schema.

    Returns:
        Dict with missing nodes and suggested packs to install.
    """
    workflow = store.load_current()
    if not workflow:
        return {"status": "error", "error": "No current workflow"}

    schema = schema_mod.load()
    if not schema:
        return {"status": "error", "error": "No schema cached. Run 'schema refresh' first."}

    missing = []
    for node_id, node in workflow.items():
        ct = node.get("class_type", "")
        if ct and ct not in schema:
            missing.append(ct)

    if not missing:
        return {"status": "ok", "message": "All nodes are available"}

    # Look up suggestions from allowlist
    allowlist = load_allowlist()
    packs = allowlist.get("packs", {})
    suggestions = {}

    for ct in missing:
        for pack_name, pack_info in packs.items():
            if ct in pack_info.get("provides", []):
                suggestions[ct] = {
                    "pack": pack_name,
                    "repo": pack_info["repo"],
                }
                break

    return {
        "status": "missing_nodes",
        "missing": missing,
        "suggestions": suggestions,
        "unsupported": [ct for ct in missing if ct not in suggestions],
    }


def check_model(model_type: str, filename: str) -> dict:
    """Check if a model file exists in the expected directory.

    Returns:
        Dict with exists bool and expected path.
    """
    type_dirs = {
        "checkpoint": config.CHECKPOINTS_DIR,
        "lora": config.LORAS_DIR,
        "vae": config.VAE_DIR,
        "controlnet": config.CONTROLNET_DIR,
        "ipadapter": config.IPADAPTER_DIR,
        "clip_vision": config.CLIP_VISION_DIR,
        "animatediff": config.ANIMATEDIFF_DIR,
    }

    model_dir = type_dirs.get(model_type)
    if not model_dir:
        return {"exists": False, "error": f"Unknown model type: {model_type}"}

    path = model_dir / filename
    return {
        "exists": path.exists(),
        "expected_path": str(path),
        "model_type": model_type,
        "filename": filename,
    }
