"""ComfyUI AI Builder — Error Interpreter + Self-Healing."""

import re
import sys

from . import config, schema as schema_mod, installer


class Fix:
    """Represents a proposed fix for a ComfyUI error."""

    def __init__(self, fix_type: str, description: str,
                 ops: list[dict] = None, install_instructions: dict = None,
                 download_instructions: dict = None):
        self.type = fix_type  # "graph_op", "install_required", "model_missing", "reduce_resources", "unfixable"
        self.description = description
        self.ops = ops or []
        self.install_instructions = install_instructions
        self.download_instructions = download_instructions

    def to_dict(self) -> dict:
        d = {"type": self.type, "description": self.description}
        if self.ops:
            d["ops"] = self.ops
        if self.install_instructions:
            d["install"] = self.install_instructions
        if self.download_instructions:
            d["download"] = self.download_instructions
        return d


def diagnose(error_data) -> Fix:
    """Diagnose a ComfyUI error and propose a fix.

    Args:
        error_data: Error info from runner (dict or string).

    Returns:
        Fix object with proposed solution.
    """
    if isinstance(error_data, str):
        error_str = error_data
    elif isinstance(error_data, dict):
        error_str = str(error_data)
    elif isinstance(error_data, list):
        error_str = " ".join(str(e) for e in error_data)
    else:
        error_str = str(error_data)

    # Check each pattern
    for checker in [
        _check_node_not_found,
        _check_model_missing,
        _check_input_mismatch,
        _check_oom,
        _check_connection_refused,
    ]:
        fix = checker(error_str)
        if fix:
            return fix

    return Fix("unfixable", f"Unrecognized error: {error_str[:200]}")


def _check_node_not_found(error: str) -> Fix | None:
    """Detect missing node class errors."""
    patterns = [
        r"class_type.*?not found.*?['\"](\w+)['\"]",
        r"['\"](\w+)['\"].*?not found",
        r"Cannot find.*?node.*?['\"](\w+)['\"]",
    ]
    for pat in patterns:
        match = re.search(pat, error, re.IGNORECASE)
        if match:
            node_class = match.group(1)
            # Look up in allowlist
            check = installer.check_missing()
            suggestions = check.get("suggestions", {})
            if node_class in suggestions:
                return Fix(
                    "install_required",
                    f"Node '{node_class}' not found. Install required.",
                    install_instructions=suggestions[node_class],
                )
            return Fix(
                "install_required",
                f"Node '{node_class}' not found. No known pack provides it.",
                install_instructions={"class_type": node_class, "pack": "unknown"},
            )
    return None


def _check_model_missing(error: str) -> Fix | None:
    """Detect missing model file errors."""
    patterns = [
        r"(?:file not found|FileNotFoundError).*?models[/\\](\w+)[/\\]([^\s'\"]+)",
        r"Could not.*?load.*?['\"]([^\s'\"]+\.safetensors)['\"]",
        r"['\"]([^\s'\"]+\.(?:safetensors|ckpt|pt|pth|bin))['\"].*?(?:not found|missing)",
    ]
    for pat in patterns:
        match = re.search(pat, error, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                model_type, filename = groups
            else:
                filename = groups[0]
                model_type = "unknown"

            return Fix(
                "model_missing",
                f"Model file missing: {filename}",
                download_instructions={
                    "model_type": model_type,
                    "filename": filename,
                    "hint": f"Place the file in ComfyUI/models/{model_type}/{filename}",
                },
            )
    return None


def _check_input_mismatch(error: str) -> Fix | None:
    """Detect input key or type mismatch errors."""
    match = re.search(
        r"(?:Invalid|Unknown).*?input.*?['\"](\w+)['\"].*?node.*?['\"](\w+)['\"]",
        error, re.IGNORECASE,
    )
    if match:
        input_key, node_class = match.group(1), match.group(2)
        # Query schema for correct inputs
        node_info = schema_mod.get_node_inputs(node_class)
        valid_keys = set(node_info.get("required", {})) | set(node_info.get("optional", {}))

        return Fix(
            "graph_op",
            f"Invalid input '{input_key}' for '{node_class}'. Valid: {sorted(valid_keys)}",
            ops=[],  # Caller should re-map the input
        )
    return None


def _check_oom(error: str) -> Fix | None:
    """Detect CUDA OOM errors."""
    if any(phrase in error.lower() for phrase in [
        "cuda out of memory", "out of memory", "oom", "torch.cuda.outofmemoryerror",
    ]):
        return Fix(
            "reduce_resources",
            "CUDA out of memory. Reducing resolution and enabling optimizations.",
            ops=[
                # Reduce resolution to 75%
                {"op": "set_input", "id": "find_latent", "key": "width", "value": 768},
                {"op": "set_input", "id": "find_latent", "key": "height", "value": 768},
            ],
        )
    return None


def _check_connection_refused(error: str) -> Fix | None:
    """Detect server connection errors."""
    if any(phrase in error.lower() for phrase in [
        "connection refused", "urlopen error", "cannot connect",
    ]):
        return Fix(
            "unfixable",
            f"ComfyUI server not reachable at {config.COMFYUI_URL}. Start the server and try again.",
        )
    return None


def auto_heal(workflow: dict, error_data, attempt: int) -> tuple[dict, Fix] | None:
    """Attempt to auto-heal a workflow based on error.

    Args:
        workflow: Current workflow dict.
        error_data: Error from runner.
        attempt: Current retry attempt (1-indexed).

    Returns:
        (modified_workflow, fix) tuple if healable, None if not.
    """
    if attempt > config.MAX_RETRIES:
        return None

    fix = diagnose(error_data)
    print(f"  Heal attempt {attempt}: {fix.description}", file=sys.stderr)

    if fix.type == "graph_op" and fix.ops:
        from . import graph_ops
        # Apply fix ops (may need to resolve "find_latent" placeholders)
        resolved_ops = _resolve_placeholders(workflow, fix.ops)
        graph_ops.apply_ops(workflow, resolved_ops)
        return workflow, fix

    if fix.type == "reduce_resources":
        from . import graph_ops
        resolved_ops = _resolve_placeholders(workflow, fix.ops)
        graph_ops.apply_ops(workflow, resolved_ops)
        return workflow, fix

    # Can't auto-fix install_required or model_missing — needs user action
    return None


def _resolve_placeholders(workflow: dict, ops: list[dict]) -> list[dict]:
    """Resolve placeholder node IDs like 'find_latent' to actual node IDs."""
    resolved = []
    for op in ops:
        op = dict(op)
        node_id = op.get("id", "")

        if node_id.startswith("find_"):
            target_type = node_id.replace("find_", "")
            type_map = {
                "latent": "EmptyLatentImage",
                "sampler": "KSampler",
                "vae": "VAEDecode",
            }
            class_type = type_map.get(target_type)
            if class_type:
                for wf_id, wf_node in workflow.items():
                    if wf_node.get("class_type") == class_type:
                        op["id"] = wf_id
                        break

        resolved.append(op)
    return resolved
