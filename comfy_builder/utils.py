"""ComfyUI AI Builder — Shared utilities."""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def timestamp() -> str:
    """Return a sortable timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def file_hash(path: Path) -> str:
    """Return SHA256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def json_hash(data: dict) -> str:
    """Return SHA256 hex digest of a JSON-serializable dict."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> dict:
    """Load and return JSON from a file, or empty dict if missing."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: Path, data, indent: int = 2):
    """Save data as JSON to a file, creating parents if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)


def append_jsonl(path: Path, record: dict):
    """Append a single JSON record to a .jsonl file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
