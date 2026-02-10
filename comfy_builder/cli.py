"""ComfyUI AI Builder — CLI Command Router."""

import argparse
import json
import sys

from . import config


def cmd_status(args):
    """Check ComfyUI server status."""
    from .api import check_server, list_models

    result = check_server()
    if not result["online"]:
        result["comfyui_url"] = config.COMFYUI_URL
        result["hint"] = "Start ComfyUI server and try again."
        print(json.dumps(result, indent=2))
        return 1

    models = {
        "checkpoints": list_models("checkpoints"),
        "loras": list_models("loras"),
        "vae": list_models("vae"),
    }
    result["models"] = models
    result["comfyui_url"] = config.COMFYUI_URL
    result["comfyui_path"] = str(config.COMFYUI_PATH)
    print(json.dumps(result, indent=2))
    return 0


def cmd_schema_refresh(args):
    """Refresh node schema from ComfyUI."""
    from . import schema
    result = schema.refresh()
    print(json.dumps(result, indent=2))
    return 0


def cmd_schema_search(args):
    """Search node schema by keyword."""
    from . import schema
    results = schema.search(args.query, limit=args.limit)
    print(json.dumps({"query": args.query, "count": len(results), "nodes": results}, indent=2))
    return 0


def cmd_build(args):
    """Build a workflow from a template."""
    from . import planner

    template = args.template
    params = _parse_build_params(args)

    try:
        result = planner.build(template, params)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") != "error" else 1
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        return 1


def cmd_run(args):
    """Run a workflow against ComfyUI."""
    from . import runner

    workflow_name = args.workflow or "current"
    try:
        result = runner.run(workflow_name)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") == "success" else 1
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1


def cmd_show(args):
    """Show current workflow summary."""
    from . import store

    workflow_name = args.workflow or "current"
    wf = store.load_workflow(workflow_name)
    if not wf:
        print(json.dumps({"status": "error", "error": f"No workflow '{workflow_name}' found"}))
        return 1

    summary = {
        "workflow": workflow_name,
        "node_count": len(wf),
        "nodes": [],
    }
    for node_id, node in sorted(wf.items(), key=lambda x: str(x[0])):
        summary["nodes"].append({
            "id": node_id,
            "class_type": node.get("class_type", "?"),
            "inputs": list(node.get("inputs", {}).keys()),
        })
    print(json.dumps(summary, indent=2))
    return 0


def cmd_list_workflows(args):
    """List available workflows and templates."""
    from . import store
    result = store.list_all()
    print(json.dumps(result, indent=2))
    return 0


def cmd_export(args):
    """Export current workflow + outputs to a named export."""
    from . import store

    workflow_name = args.workflow or "current"
    name = args.name
    result = store.export_workflow(workflow_name, name)
    print(json.dumps(result, indent=2))
    return 0


def cmd_install_nodes(args):
    """Install a custom node pack."""
    from . import installer

    result = installer.install_pack(args.source, force_allow=args.force_allow)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "success" else 1


def cmd_install_check(args):
    """Check for missing nodes in current workflow."""
    from . import installer

    result = installer.check_missing()
    print(json.dumps(result, indent=2))
    return 0


def cmd_run_scenes(args):
    """Run a workflow across all scenes in scenes.txt."""
    import copy
    import re
    from . import config, api, store
    from .utils import load_json, save_json, timestamp, append_jsonl

    workflow_name = args.workflow
    wf = store.load_workflow(workflow_name)
    if not wf:
        print(json.dumps({"status": "error", "error": f"Workflow '{workflow_name}' not found"}))
        return 1

    # Load scenes
    scenes_file = config.WORKFLOWS_DIR / "scenes.txt"
    if not scenes_file.exists():
        print(json.dumps({"status": "error", "error": "workflows/scenes.txt not found"}))
        return 1

    scenes = [line.strip() for line in scenes_file.read_text().splitlines() if line.strip()]
    if not scenes:
        print(json.dumps({"status": "error", "error": "scenes.txt is empty"}))
        return 1

    # Character description anchor (kept constant in every prompt)
    char_desc = args.character or "a cute fat round little creature with short stubby arms, big dark glossy eyes, smooth pale body"
    suffix = ", photorealistic, cinematic lighting, 8k, detailed"

    server = api.check_server()
    if not server["online"]:
        print(json.dumps({"status": "error", "error": "ComfyUI server not reachable"}))
        return 1

    ts = timestamp()
    all_outputs = []
    errors = []

    print(f"Running {len(scenes)} scenes with workflow '{workflow_name}'...", file=sys.stderr)

    for i, scene in enumerate(scenes):
        scene_slug = re.sub(r'[^a-z0-9]+', '_', scene.lower())[:40].strip('_')
        full_prompt = f"{char_desc}, {scene}{suffix}"

        print(f"  [{i+1}/{len(scenes)}] {scene_slug}", file=sys.stderr)

        wf_copy = copy.deepcopy(wf)

        # Patch prompt node (find CLIPTextEncode that's positive prompt)
        for nid, node in wf_copy.items():
            if node.get("class_type") == "CLIPTextEncode":
                text = node.get("inputs", {}).get("text", "")
                if "blurry" not in text and "deformed" not in text:
                    node["inputs"]["text"] = full_prompt
                    break

        # Patch filename prefix
        for nid, node in wf_copy.items():
            if node.get("class_type") == "SaveImage":
                node["inputs"]["filename_prefix"] = f"huffle/{scene_slug}"

        # Patch seed if requested
        if args.seed is not None:
            for nid, node in wf_copy.items():
                if node.get("class_type") == "KSampler":
                    node["inputs"]["seed"] = args.seed + i

        try:
            resp = api.post_prompt(wf_copy)
            prompt_id = resp.get("prompt_id")
            if not prompt_id:
                errors.append({"scene": scene_slug, "error": "No prompt_id"})
                continue

            # Poll for completion
            import time
            start = time.time()
            while time.time() - start < config.RUN_TIMEOUT_S:
                try:
                    hist = api.get_history(prompt_id)
                    entry = hist.get(prompt_id, {})
                    status = entry.get("status", {})
                    if status.get("completed") or status.get("status_str") == "success":
                        # Collect outputs
                        for nid, out in entry.get("outputs", {}).items():
                            for img in out.get("images", []):
                                all_outputs.append({
                                    "scene": scene_slug,
                                    "file": f"ComfyUI/output/huffle/{scene_slug}_{img.get('filename', '')}",
                                    "filename": img.get("filename", ""),
                                })
                        break
                    if status.get("status_str") == "error":
                        errors.append({"scene": scene_slug, "error": str(status)})
                        break
                except Exception:
                    pass
                time.sleep(2)
            else:
                errors.append({"scene": scene_slug, "error": "timeout"})

        except Exception as e:
            errors.append({"scene": scene_slug, "error": str(e)})

    result = {
        "status": "success" if not errors else ("partial" if all_outputs else "failed"),
        "scenes_total": len(scenes),
        "scenes_completed": len(all_outputs),
        "outputs": all_outputs,
        "errors": errors,
    }

    # Save run log
    log_path = store.save_run_log(result)
    result["log_path"] = str(log_path)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "success" else 1


def cmd_refine(args):
    """Apply refinement to current workflow."""
    from . import planner

    result = planner.refine(args.instruction)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") != "error" else 1


def cmd_logs_last(args):
    """Show the last run log."""
    from . import store

    log = store.last_run_log()
    if log:
        print(json.dumps(log, indent=2, default=str))
        return 0
    print(json.dumps({"status": "error", "error": "No run logs found"}))
    return 1


def _parse_build_params(args) -> dict:
    """Extract build parameters from argparse namespace."""
    params = {}
    for key in [
        "prompt", "negative", "checkpoint", "lora", "lora_strength",
        "scenes", "count", "ref", "seconds", "fps", "style",
        "steps", "cfg", "width", "height", "seed", "sampler", "scheduler",
        "denoise", "batch_size",
    ]:
        val = getattr(args, key, None)
        if val is not None:
            params[key] = val
    return params


def main(argv=None):
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="comfy_builder",
        description="ComfyUI AI Builder — build, run, and manage ComfyUI workflows",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Check ComfyUI server status")

    # schema
    schema_p = sub.add_parser("schema", help="Manage node schema")
    schema_sub = schema_p.add_subparsers(dest="schema_cmd", required=True)
    schema_sub.add_parser("refresh", help="Refresh schema from ComfyUI")
    search_p = schema_sub.add_parser("search", help="Search nodes by keyword")
    search_p.add_argument("query", help="Search keyword")
    search_p.add_argument("--limit", type=int, default=20)

    # build
    build_p = sub.add_parser("build", help="Build a workflow from template")
    build_p.add_argument("template", help="Template name: text2img, lora_scenes, img2vid")
    build_p.add_argument("--prompt", "-p", help="Positive prompt")
    build_p.add_argument("--negative", "-n", help="Negative prompt")
    build_p.add_argument("--checkpoint", help="Checkpoint filename")
    build_p.add_argument("--lora", help="LoRA filename")
    build_p.add_argument("--lora-strength", type=float, dest="lora_strength")
    build_p.add_argument("--scenes", help="Pipe-separated scene list")
    build_p.add_argument("--count", type=int, help="Images per scene")
    build_p.add_argument("--ref", help="Reference image path")
    build_p.add_argument("--seconds", type=float, help="Video duration in seconds")
    build_p.add_argument("--fps", type=int, help="Frames per second")
    build_p.add_argument("--style", help="Style modifier")
    build_p.add_argument("--steps", type=int)
    build_p.add_argument("--cfg", type=float)
    build_p.add_argument("--width", type=int)
    build_p.add_argument("--height", type=int)
    build_p.add_argument("--seed", type=int)
    build_p.add_argument("--sampler", help="Sampler name")
    build_p.add_argument("--scheduler", help="Scheduler name")
    build_p.add_argument("--denoise", type=float)
    build_p.add_argument("--batch-size", type=int, dest="batch_size")

    # run
    run_p = sub.add_parser("run", help="Run a workflow")
    run_p.add_argument("workflow", nargs="?", default="current", help="Workflow name or path")

    # show
    show_p = sub.add_parser("show", help="Show workflow summary")
    show_p.add_argument("workflow", nargs="?", default="current")

    # list
    sub.add_parser("list", help="List workflows and templates")

    # export
    export_p = sub.add_parser("export", help="Export workflow + outputs")
    export_p.add_argument("workflow", nargs="?", default="current")
    export_p.add_argument("--name", required=True, help="Export name")

    # install
    install_p = sub.add_parser("install", help="Install nodes or check deps")
    install_sub = install_p.add_subparsers(dest="install_cmd", required=True)
    nodes_p = install_sub.add_parser("nodes", help="Install a custom node pack")
    nodes_p.add_argument("source", help="Pack name (from allowlist) or repo URL")
    nodes_p.add_argument("--force-allow", action="store_true", dest="force_allow",
                         help="Allow URL not in allowlist")
    install_sub.add_parser("check", help="Check for missing nodes")

    # run-scenes
    rs_p = sub.add_parser("run-scenes", help="Run workflow across all scenes in scenes.txt")
    rs_p.add_argument("workflow", help="Workflow name to run per scene")
    rs_p.add_argument("--character", help="Character description to inject into prompts")
    rs_p.add_argument("--seed", type=int, help="Base seed (incremented per scene)")

    # refine
    refine_p = sub.add_parser("refine", help="Refine current workflow")
    refine_p.add_argument("instruction", help="Refinement instruction")

    # logs
    logs_p = sub.add_parser("logs", help="View run logs")
    logs_sub = logs_p.add_subparsers(dest="logs_cmd", required=True)
    logs_sub.add_parser("last", help="Show last run log")

    # chat
    sub.add_parser("chat", help="Launch the chat UI panel")

    # focus-ui (desktop: bring ComfyUI window to front and move mouse)
    sub.add_parser("focus-ui", help="Bring ComfyUI desktop window to front and move mouse (desktop automation)")

    args = parser.parse_args(argv)

    # Route commands
    routes = {
        "status": cmd_status,
        "schema": lambda a: {"refresh": cmd_schema_refresh, "search": cmd_schema_search}[a.schema_cmd](a),
        "build": cmd_build,
        "run": cmd_run,
        "run-scenes": cmd_run_scenes,
        "show": cmd_show,
        "list": cmd_list_workflows,
        "export": cmd_export,
        "install": lambda a: {"nodes": cmd_install_nodes, "check": cmd_install_check}[a.install_cmd](a),
        "refine": cmd_refine,
        "logs": lambda a: {"last": cmd_logs_last}[a.logs_cmd](a),
    }

    if args.command == "chat":
        from .chat.server import main as chat_main
        chat_main()
        return 0

    if args.command == "focus-ui":
        from .desktop_ui import focus_comfyui_and_click
        ok = focus_comfyui_and_click(click_inside=True)
        print(json.dumps({"status": "success" if ok else "error", "window_focused": ok}))
        return 0 if ok else 1

    handler = routes.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1
