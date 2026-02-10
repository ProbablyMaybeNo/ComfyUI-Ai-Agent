"""ComfyUI AI Builder — ComfyUI API Client."""

import json
import uuid
import urllib.request
import urllib.error
from pathlib import Path

from . import config


def _get(endpoint: str, timeout: int = 10) -> dict:
    """GET request to ComfyUI server. Returns parsed JSON."""
    url = f"{config.COMFYUI_URL}{endpoint}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _post(endpoint: str, data: dict, timeout: int = None) -> dict:
    """POST JSON to ComfyUI server. Returns parsed JSON."""
    url = f"{config.COMFYUI_URL}{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t = timeout or config.RUN_TIMEOUT_S
    with urllib.request.urlopen(req, timeout=t) as resp:
        return json.loads(resp.read().decode())


def get_status() -> dict:
    """GET /system_stats — server status and system info."""
    return _get("/system_stats")


def get_queue() -> dict:
    """GET /queue — current queue state."""
    return _get("/queue")


def get_object_info() -> dict:
    """GET /object_info — full node schema (all registered nodes)."""
    return _get("/object_info", timeout=30)


def get_object_info_node(class_type: str) -> dict:
    """GET /object_info/<class_type> — schema for a single node."""
    return _get(f"/object_info/{class_type}")


def post_prompt(workflow: dict, client_id: str = None) -> dict:
    """POST /prompt — queue a workflow for execution.

    Args:
        workflow: The workflow dict (ComfyUI API format).
        client_id: Optional client ID for WebSocket tracking.

    Returns:
        Response dict with 'prompt_id' on success.
    """
    payload = {"prompt": workflow}
    if client_id:
        payload["client_id"] = client_id
    return _post("/prompt", payload)


def get_history(prompt_id: str = None) -> dict:
    """GET /history or /history/<prompt_id>."""
    endpoint = f"/history/{prompt_id}" if prompt_id else "/history"
    return _get(endpoint, timeout=30)


def get_image(filename: str, subfolder: str = "", img_type: str = "output") -> bytes:
    """GET /view — download a generated image.

    Returns raw image bytes.
    """
    params = f"?filename={filename}&subfolder={subfolder}&type={img_type}"
    url = f"{config.COMFYUI_URL}/view{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def interrupt() -> dict:
    """POST /interrupt — cancel current execution."""
    return _post("/interrupt", {})


def check_server() -> dict:
    """Check if ComfyUI server is reachable. Returns status dict."""
    try:
        status = get_status()
        queue = get_queue()
        return {
            "online": True,
            "system_stats": status,
            "queue": queue,
        }
    except urllib.error.URLError as e:
        return {"online": False, "error": str(e)}
    except Exception as e:
        return {"online": False, "error": str(e)}


def list_models(model_type: str = "checkpoints") -> list[str]:
    """List model filenames in a given model subdirectory."""
    model_dir = config.MODELS_DIR / model_type
    if not model_dir.exists():
        return []
    suffixes = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}
    return sorted(
        f.name for f in model_dir.iterdir()
        if f.is_file() and f.suffix in suffixes
    )
