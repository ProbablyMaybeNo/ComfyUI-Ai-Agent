"""ComfyUI AI Builder — Workflow Runner + Output Collector."""

import sys
import time
import shutil
from pathlib import Path

from . import config, api, store
from .utils import timestamp, save_json, append_jsonl, load_json


def run(workflow_name: str = "current") -> dict:
    """Run a workflow against ComfyUI.

    Args:
        workflow_name: Name of workflow to run ('current', template name, etc.)

    Returns:
        Run result dict with status, outputs, timing, etc.
    """
    ts = timestamp()
    workflow = store.load_workflow(workflow_name)
    if not workflow:
        return {"status": "error", "error": f"Workflow '{workflow_name}' not found"}

    # Check server
    server = api.check_server()
    if not server["online"]:
        return {
            "status": "error",
            "error": "ComfyUI server not reachable",
            "hint": f"Start ComfyUI and ensure it's running at {config.COMFYUI_URL}",
        }

    # Check if this is a batch workflow (lora_scenes meta)
    meta = _load_build_meta()
    if meta and meta.get("batch"):
        return _run_batch(workflow, meta, ts)

    return _run_single(workflow, workflow_name, ts)


def _run_single(workflow: dict, workflow_name: str, ts: str) -> dict:
    """Run a single workflow."""
    print(f"Submitting workflow '{workflow_name}'...", file=sys.stderr)

    try:
        resp = api.post_prompt(workflow)
    except Exception as e:
        return {"status": "error", "error": f"Failed to submit prompt: {e}"}

    if "error" in resp:
        return {"status": "error", "error": resp["error"],
                "node_errors": resp.get("node_errors", {})}

    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        return {"status": "error", "error": "No prompt_id in response", "response": resp}

    print(f"Queued: prompt_id={prompt_id}", file=sys.stderr)

    # Poll for completion
    result = _poll_completion(prompt_id)

    # Collect outputs
    outputs = []
    if result["status"] == "success":
        outputs = _collect_outputs(prompt_id, ts)

    # Build run log
    run_log = {
        "run_id": ts,
        "timestamp": ts,
        "workflow_name": workflow_name,
        "prompt_id": prompt_id,
        "status": result["status"],
        "duration_s": result.get("duration_s", 0),
        "outputs": outputs,
        "errors": result.get("errors", []),
    }

    # Save log
    log_path = store.save_run_log(run_log)
    run_log["log_path"] = str(log_path)

    # Append to metadata
    append_jsonl(config.METADATA_FILE, {
        "run_id": ts, "prompt_id": prompt_id,
        "status": result["status"], "outputs": [o["file"] for o in outputs],
    })

    return run_log


def _run_batch(workflow: dict, meta: dict, ts: str) -> dict:
    """Run a batch of workflows (e.g., lora_scenes)."""
    batch = meta["batch"]
    total = len(batch)
    all_outputs = []
    errors = []

    print(f"Running batch: {total} jobs", file=sys.stderr)

    for i, job in enumerate(batch):
        print(f"  [{i+1}/{total}] scene='{job.get('scene', '?')}' seed={job.get('seed', '?')}",
              file=sys.stderr)

        # Clone workflow and apply job-specific params
        import copy
        wf = copy.deepcopy(workflow)

        # Update prompt — find the positive CLIPTextEncode (not the negative)
        for node_id, node in wf.items():
            if node.get("class_type") == "CLIPTextEncode" and "text" in node.get("inputs", {}):
                text = node["inputs"]["text"]
                # Skip the negative prompt node (contains negative keywords)
                if any(neg in text.lower() for neg in ["blurry", "deformed", "ugly", "low quality"]):
                    continue
                node["inputs"]["text"] = job["prompt"]
                break

        # Update seed
        for node_id, node in wf.items():
            if node.get("class_type") == "KSampler" and "seed" in node.get("inputs", {}):
                node["inputs"]["seed"] = job["seed"]

        # Update filename prefix
        for node_id, node in wf.items():
            if node.get("class_type") == "SaveImage":
                node["inputs"]["filename_prefix"] = job.get("filename_prefix", f"comfy_builder/batch_{i}")

        # Submit
        try:
            resp = api.post_prompt(wf)
            prompt_id = resp.get("prompt_id")
            if not prompt_id:
                errors.append({"job": i, "error": "No prompt_id"})
                continue

            result = _poll_completion(prompt_id)
            if result["status"] == "success":
                job_outputs = _collect_outputs(prompt_id, f"{ts}_{i}")
                all_outputs.extend(job_outputs)
            else:
                errors.append({"job": i, "error": result.get("errors", "unknown")})

        except Exception as e:
            errors.append({"job": i, "error": str(e)})

    run_log = {
        "run_id": ts,
        "timestamp": ts,
        "batch_size": total,
        "status": "success" if not errors else ("partial" if all_outputs else "failed"),
        "outputs": all_outputs,
        "errors": errors,
    }

    log_path = store.save_run_log(run_log)
    run_log["log_path"] = str(log_path)
    return run_log


def _poll_completion(prompt_id: str, timeout: int = None) -> dict:
    """Poll ComfyUI history until prompt completes or times out."""
    timeout = timeout or config.RUN_TIMEOUT_S
    start = time.time()
    poll_interval = 1.0

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            return {"status": "timeout", "duration_s": elapsed,
                    "errors": [f"Timed out after {timeout}s"]}

        try:
            history = api.get_history(prompt_id)
        except Exception:
            time.sleep(poll_interval)
            continue

        entry = history.get(prompt_id)
        if not entry:
            time.sleep(poll_interval)
            continue

        status_info = entry.get("status", {})
        if status_info.get("completed", False) or status_info.get("status_str") == "success":
            return {
                "status": "success",
                "duration_s": round(elapsed, 2),
                "history": entry,
            }

        if status_info.get("status_str") == "error":
            msgs = entry.get("status", {}).get("messages", [])
            return {
                "status": "failed",
                "duration_s": round(elapsed, 2),
                "errors": msgs,
                "history": entry,
            }

        time.sleep(poll_interval)


def _collect_outputs(prompt_id: str, run_id: str) -> list[dict]:
    """Download output images/videos from ComfyUI to local out/ directory."""
    outputs = []

    try:
        history = api.get_history(prompt_id)
    except Exception:
        return outputs

    entry = history.get(prompt_id, {})
    output_data = entry.get("outputs", {})

    for node_id, node_output in output_data.items():
        # Images
        for img in node_output.get("images", []):
            filename = img.get("filename", "")
            subfolder = img.get("subfolder", "")
            img_type = img.get("type", "output")

            try:
                data = api.get_image(filename, subfolder, img_type)
                local_name = f"{run_id}_{filename}"
                local_path = config.IMAGES_DIR / local_name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(data)

                outputs.append({
                    "file": str(local_path),
                    "type": "image",
                    "node_id": node_id,
                    "original_filename": filename,
                })
                print(f"  Saved: {local_path}", file=sys.stderr)
            except Exception as e:
                print(f"  Warning: failed to download {filename}: {e}", file=sys.stderr)

        # Videos (GIFs, MP4s from VHS nodes)
        for vid in node_output.get("gifs", []):
            filename = vid.get("filename", "")
            subfolder = vid.get("subfolder", "")

            try:
                data = api.get_image(filename, subfolder, "output")
                local_name = f"{run_id}_{filename}"
                local_path = config.VIDEO_DIR / local_name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(data)

                outputs.append({
                    "file": str(local_path),
                    "type": "video",
                    "node_id": node_id,
                    "original_filename": filename,
                })
                print(f"  Saved: {local_path}", file=sys.stderr)
            except Exception as e:
                print(f"  Warning: failed to download {filename}: {e}", file=sys.stderr)

    return outputs


def _load_build_meta() -> dict | None:
    """Load build metadata from the current workflow's build params.

    The planner saves batch info alongside the workflow.
    """
    meta_path = config.WORKFLOWS_DIR / "current_meta.json"
    if meta_path.exists():
        return load_json(meta_path)
    return None
