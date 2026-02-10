"""ComfyUI AI Builder — Graph Operations Engine.

Applies structured operations to ComfyUI workflow dicts.
A workflow is a dict of {node_id: {class_type, inputs}}.
"""

from . import schema as schema_mod


def apply_ops(workflow: dict, ops: list[dict]) -> dict:
    """Apply a list of graph operations to a workflow dict.

    Args:
        workflow: ComfyUI API-format workflow (mutable, modified in-place).
        ops: List of operation dicts.

    Returns:
        The modified workflow dict.

    Raises:
        ValueError: If an operation is invalid.
    """
    for op in ops:
        op_type = op.get("op")
        if op_type == "add_node":
            _op_add_node(workflow, op)
        elif op_type == "connect":
            _op_connect(workflow, op)
        elif op_type == "set_input":
            _op_set_input(workflow, op)
        elif op_type == "delete_node":
            _op_delete_node(workflow, op)
        elif op_type == "replace_node":
            _op_replace_node(workflow, op)
        else:
            raise ValueError(f"Unknown op type: {op_type}")

    return workflow


def _op_add_node(workflow: dict, op: dict):
    node_id = str(op["id"])
    if node_id in workflow:
        raise ValueError(f"Node '{node_id}' already exists")

    workflow[node_id] = {
        "class_type": op["class_type"],
        "inputs": dict(op.get("inputs", {})),
    }


def _op_connect(workflow: dict, op: dict):
    from_id = str(op["from_id"])
    to_id = str(op["to_id"])

    if from_id not in workflow:
        raise ValueError(f"Source node '{from_id}' not found")
    if to_id not in workflow:
        raise ValueError(f"Target node '{to_id}' not found")

    from_output = op["from_output"]  # integer index
    to_input = op["to_input"]        # string key name

    workflow[to_id]["inputs"][to_input] = [from_id, from_output]


def _op_set_input(workflow: dict, op: dict):
    node_id = str(op["id"])
    if node_id not in workflow:
        raise ValueError(f"Node '{node_id}' not found")

    key = op["key"]
    value = op["value"]
    workflow[node_id]["inputs"][key] = value


def _op_delete_node(workflow: dict, op: dict):
    node_id = str(op["id"])
    if node_id not in workflow:
        raise ValueError(f"Node '{node_id}' not found for deletion")

    del workflow[node_id]

    # Clean up any connections pointing to this node
    for nid, node in workflow.items():
        inputs = node.get("inputs", {})
        dead_keys = [
            k for k, v in inputs.items()
            if isinstance(v, list) and len(v) == 2 and str(v[0]) == node_id
        ]
        for k in dead_keys:
            del inputs[k]


def _op_replace_node(workflow: dict, op: dict):
    node_id = str(op["id"])
    if node_id not in workflow:
        raise ValueError(f"Node '{node_id}' not found for replacement")

    # Preserve existing connections to this node from other nodes
    workflow[node_id] = {
        "class_type": op["class_type"],
        "inputs": dict(op.get("inputs", {})),
    }


def validate_workflow(workflow: dict, strict: bool = True) -> list[str]:
    """Validate a workflow against the cached node schema.

    Args:
        workflow: ComfyUI API-format workflow.
        strict: If True, validate input keys against schema.

    Returns:
        List of error strings (empty = valid).
    """
    errors = []

    for node_id, node in workflow.items():
        ct = node.get("class_type")
        if not ct:
            errors.append(f"Node '{node_id}' missing class_type")
            continue

        if not schema_mod.validate_class_type(ct):
            errors.append(f"Node '{node_id}': unknown class_type '{ct}'")
            continue

        if strict:
            input_errors = schema_mod.validate_inputs(ct, node.get("inputs", {}))
            for e in input_errors:
                errors.append(f"Node '{node_id}': {e}")

        # Validate connections point to existing nodes
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) == 2:
                ref_id = str(val[0])
                if ref_id not in workflow:
                    errors.append(
                        f"Node '{node_id}' input '{key}' references missing node '{ref_id}'"
                    )

    return errors


def workflow_summary(workflow: dict) -> dict:
    """Generate a human-readable summary of a workflow."""
    nodes = []
    connections = []

    for node_id, node in sorted(workflow.items(), key=lambda x: str(x[0])):
        ct = node.get("class_type", "?")
        inputs = node.get("inputs", {})

        # Separate value inputs from connection inputs
        values = {}
        for k, v in inputs.items():
            if isinstance(v, list) and len(v) == 2:
                connections.append({
                    "from": str(v[0]),
                    "from_output": v[1],
                    "to": node_id,
                    "to_input": k,
                })
            else:
                values[k] = v

        nodes.append({
            "id": node_id,
            "class_type": ct,
            "value_inputs": values,
        })

    return {
        "node_count": len(workflow),
        "nodes": nodes,
        "connections": connections,
    }
