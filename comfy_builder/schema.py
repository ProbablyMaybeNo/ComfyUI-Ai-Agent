"""ComfyUI AI Builder — Schema Cache & Query."""

import sys
from datetime import datetime, timezone

from . import config
from .api import get_object_info
from .utils import save_json, load_json, json_hash

# Module-level cache to avoid re-reading 1.5MB JSON on every call
_schema_cache: dict | None = None


def _invalidate_cache():
    """Clear the in-memory schema cache (used after refresh or in tests)."""
    global _schema_cache
    _schema_cache = None


def refresh() -> dict:
    """Fetch /object_info from ComfyUI and cache to disk.

    Returns:
        Dict with 'node_count', 'hash', 'path'.
    """
    print("Fetching node schema from ComfyUI...", file=sys.stderr)
    schema = get_object_info()
    save_json(config.SCHEMA_FILE, schema)

    h = json_hash(schema)
    meta = {
        "hash": h,
        "node_count": len(schema),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json(config.SCHEMA_META, meta)
    _invalidate_cache()
    print(f"Cached {len(schema)} nodes → {config.SCHEMA_FILE}", file=sys.stderr)

    return {
        "node_count": len(schema),
        "hash": h,
        "path": str(config.SCHEMA_FILE),
    }


def load() -> dict:
    """Load cached schema from disk (with in-memory caching). Returns empty dict if not cached."""
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = load_json(config.SCHEMA_FILE)
    return _schema_cache


def meta() -> dict:
    """Load schema metadata (hash, timestamp)."""
    return load_json(config.SCHEMA_META)


def get_node(class_type: str) -> dict | None:
    """Look up a single node by class_type from cached schema."""
    schema = load()
    return schema.get(class_type)


def node_exists(class_type: str) -> bool:
    """Check if a node class_type exists in the cached schema."""
    schema = load()
    return class_type in schema


def search(query: str, limit: int = 20) -> list[dict]:
    """Search nodes by keyword in class_type or display_name.

    Returns list of {class_type, display_name, category, description}.
    """
    schema = load()
    query_lower = query.lower()
    results = []

    for class_type, info in schema.items():
        display = info.get("display_name", class_type)
        category = info.get("category", "")
        desc = info.get("description", "")
        searchable = f"{class_type} {display} {category} {desc}".lower()

        if query_lower in searchable:
            results.append({
                "class_type": class_type,
                "display_name": display,
                "category": category,
                "description": desc,
            })
        if len(results) >= limit:
            break

    return results


def get_node_inputs(class_type: str) -> dict:
    """Get input spec for a node: {required: {...}, optional: {...}}.

    Returns empty dict if node not found.
    """
    node = get_node(class_type)
    if not node:
        return {}
    return node.get("input", {})


def get_node_outputs(class_type: str) -> list:
    """Get output type list for a node.

    Returns list of output type strings, e.g. ['MODEL', 'CLIP', 'VAE'].
    """
    node = get_node(class_type)
    if not node:
        return []
    return node.get("output", [])


def validate_class_type(class_type: str) -> bool:
    """Validate that a class_type exists in schema."""
    return node_exists(class_type)


def validate_inputs(class_type: str, inputs: dict) -> list[str]:
    """Validate input keys against schema. Returns list of error strings."""
    spec = get_node_inputs(class_type)
    if not spec:
        return [f"Node '{class_type}' not found in schema"]

    required = spec.get("required", {})
    optional = spec.get("optional", {})
    hidden = spec.get("hidden", {})
    all_keys = set(required) | set(optional) | set(hidden)

    errors = []
    for key in inputs:
        # Skip link-type inputs (lists like [node_id, output_index])
        if isinstance(inputs[key], list) and len(inputs[key]) == 2:
            continue
        if key not in all_keys:
            errors.append(f"Unknown input '{key}' for node '{class_type}'. Valid: {sorted(all_keys)}")

    return errors
