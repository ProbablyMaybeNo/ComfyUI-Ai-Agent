"""Tool definitions and executor for the chat LLM.

Maps Ollama tool calls to comfy_builder functions.
"""

import json
import traceback

SYSTEM_PROMPT = """\
You are a ComfyUI workflow assistant. You build workflows, add nodes, install missing node packs, \
and run image/video generation so the user's request is completed. Use your tools as needed.

## What you can do
- **status**: Check ComfyUI and list available models.
- **build_workflow**: Build a workflow from a template (text2img, img2img, ref_poses, lora_scenes, img2vid).
- **run_workflow**: Execute the current workflow and get output images/videos.
- **install_check**: If a workflow fails with missing nodes, call this to see what's missing and which pack to install.
- **install_nodes**: Install a node pack (e.g. ComfyUI-AnimateDiff-Evolved, or a GitHub URL with force_allow). After install, tell the user to restart ComfyUI.
- **refine_workflow**: Change steps, cfg, prompt, seed on the current workflow.
- **show_workflow** / **list_workflows** / **schema_search** / **logs_last**: Inspect workflows and results.

When the user asks to generate something: build the right workflow, run it, and report the outputs. \
If run fails due to missing nodes, use install_check then install_nodes, then ask the user to restart ComfyUI and try again.

## Reference images — subject in different poses
When the user attaches a reference image and wants "this person in different poses" or "same subject, different poses":
- Use template **ref_poses** with ref set to the attached filename and **poses** = pipe-separated pose descriptions, e.g. "standing|sitting|waving|running".
- Then run_workflow. You will get one image per pose.
For a single image from a reference, use **img2img** with ref and prompt.

## Available models (checkpoints / LoRA)
- Checkpoints: realvisxlV50_v50LightningBakedvae.safetensors (default), sd_xl_turbo_1.0_fp16.safetensors (fast), sd_xl_base_1.0.safetensors, robmix_zenithV30.safetensors
- LoRA: pixar_style_sdxl, ghibli_style_sdxl, crayon_style_sdxl, watercolor_style_sdxl

## Tips
- Default 1024x1024, steps 20, cfg 7.0. For fast previews: sd_xl_turbo, steps=4, cfg=1.0.
- Always describe what you did. If ComfyUI is not running, tell the user to start it.
"""

# Ollama tool definitions (function-calling format)
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "status",
            "description": "Check if ComfyUI server is running and list available models.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_workflow",
            "description": "Build a ComfyUI workflow from a template. Templates: text2img, img2img (one ref image), ref_poses (one ref + multiple poses), lora_scenes, img2vid.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "description": "Template name: text2img, img2img (requires ref), ref_poses (ref + poses), lora_scenes, img2vid",
                        "enum": ["text2img", "img2img", "ref_poses", "lora_scenes", "img2vid"],
                    },
                    "prompt": {"type": "string", "description": "Positive prompt describing the image"},
                    "negative": {"type": "string", "description": "Negative prompt (things to avoid)"},
                    "checkpoint": {"type": "string", "description": "Checkpoint model filename"},
                    "lora": {"type": "string", "description": "LoRA model filename (required for lora_scenes)"},
                    "lora_strength": {"type": "number", "description": "LoRA strength (0.0-1.0)"},
                    "scenes": {"type": "string", "description": "Pipe-separated scenes for lora_scenes, e.g. 'kitchen|forest|space'"},
                    "count": {"type": "integer", "description": "Images per scene for lora_scenes"},
                    "steps": {"type": "integer", "description": "Sampling steps (default 20)"},
                    "cfg": {"type": "number", "description": "CFG scale (default 7.0)"},
                    "width": {"type": "integer", "description": "Image width (default 1024)"},
                    "height": {"type": "integer", "description": "Image height (default 1024)"},
                    "seed": {"type": "integer", "description": "Random seed (-1 for random)"},
                    "seconds": {"type": "number", "description": "Video duration in seconds (for img2vid)"},
                    "fps": {"type": "integer", "description": "Frames per second (for img2vid)"},
                    "ref": {"type": "string", "description": "Reference image filename in ComfyUI input folder (e.g. comfy_builder_ref_xxx.png). Required for img2img and ref_poses; optional for lora_scenes or img2vid."},
                    "poses": {"type": "string", "description": "Pipe-separated pose descriptions for ref_poses, e.g. 'standing|sitting|waving|running'. Same reference subject, different poses."},
                    "denoise": {"type": "number", "description": "Denoise strength for img2img/ref_poses (0.0-1.0; lower keeps more of the ref image, default 0.75)"},
                },
                "required": ["template", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_workflow",
            "description": "Execute the current (or named) workflow on ComfyUI. Returns output file paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Workflow name (default: 'current')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_workflow",
            "description": "Show a summary of the current workflow (nodes and connections).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Workflow name (default: 'current')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refine_workflow",
            "description": "Modify the current workflow. Examples: 'set steps to 30', 'change cfg to 8.5', 'set seed to 12345', 'change prompt to ...'",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string", "description": "Refinement instruction"},
                },
                "required": ["instruction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workflows",
            "description": "List all available workflows, templates, and drafts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schema_search",
            "description": "Search available ComfyUI nodes by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "logs_last",
            "description": "Get the last run log with output paths, timing, and status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_check",
            "description": "Check if the current workflow uses any nodes that are not installed (missing from ComfyUI). Returns missing node names and suggested node packs to install. Call this if a workflow fails with missing nodes, then use install_nodes to install the suggested pack.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_nodes",
            "description": "Install a custom node pack into ComfyUI (clones repo, runs pip install if needed). source: pack name from allowlist (e.g. ComfyUI-AnimateDiff-Evolved, ComfyUI-VideoHelperSuite) or a GitHub URL. After installing, tell the user to restart ComfyUI and run schema refresh.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Pack name (from install_check suggestions) or https://github.com/... URL"},
                    "force_allow": {"type": "boolean", "description": "If true, allow installing from a URL not in the allowlist (use for GitHub URLs)"},
                },
                "required": ["source"],
            },
        },
    },
]


def execute(tool_name: str, arguments: dict) -> dict:
    """Execute a tool call and return the result as a dict."""
    try:
        handler = _HANDLERS.get(tool_name)
        if not handler:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}
        return handler(arguments)
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


def _tool_status(_args: dict) -> dict:
    from ..api import check_server, list_models
    from .. import config

    result = check_server()
    if result["online"]:
        result["models"] = {
            "checkpoints": list_models("checkpoints"),
            "loras": list_models("loras"),
        }
        result["comfyui_url"] = config.COMFYUI_URL
    return result


def _tool_build(args: dict) -> dict:
    from .. import planner

    template = args.get("template", "text2img")
    params = {k: v for k, v in args.items() if k != "template" and v is not None}
    return planner.build(template, params)


def _tool_run(args: dict) -> dict:
    from .. import runner

    name = args.get("name", "current")
    return runner.run(name)


def _tool_show(args: dict) -> dict:
    from .. import store

    name = args.get("name", "current")
    wf = store.load_workflow(name)
    if not wf:
        return {"status": "error", "error": f"No workflow '{name}' found"}

    nodes = []
    for node_id, node in sorted(wf.items(), key=lambda x: str(x[0])):
        nodes.append({
            "id": node_id,
            "class_type": node.get("class_type", "?"),
            "inputs": list(node.get("inputs", {}).keys()),
        })
    return {"workflow": name, "node_count": len(wf), "nodes": nodes}


def _tool_refine(args: dict) -> dict:
    from .. import planner

    instruction = args.get("instruction", "")
    if not instruction:
        return {"status": "error", "error": "No instruction provided"}
    return planner.refine(instruction)


def _tool_list(_args: dict) -> dict:
    from .. import store
    return store.list_all()


def _tool_schema_search(args: dict) -> dict:
    from .. import schema

    query = args.get("query", "")
    if not query:
        return {"status": "error", "error": "No query provided"}
    results = schema.search(query, limit=20)
    return {"query": query, "count": len(results), "nodes": results}


def _tool_logs_last(_args: dict) -> dict:
    from .. import store

    log = store.last_run_log()
    if log:
        return log
    return {"status": "error", "error": "No run logs found"}


def _tool_install_check(_args: dict) -> dict:
    from .. import installer

    return installer.check_missing()


def _tool_install_nodes(args: dict) -> dict:
    from .. import installer

    source = args.get("source", "").strip()
    if not source:
        return {"status": "error", "error": "No source (pack name or URL) provided"}
    force_allow = bool(args.get("force_allow", False))
    return installer.install_pack(source, force_allow=force_allow)


_HANDLERS = {
    "status": _tool_status,
    "build_workflow": _tool_build,
    "run_workflow": _tool_run,
    "show_workflow": _tool_show,
    "refine_workflow": _tool_refine,
    "list_workflows": _tool_list,
    "schema_search": _tool_schema_search,
    "logs_last": _tool_logs_last,
    "install_check": _tool_install_check,
    "install_nodes": _tool_install_nodes,
}
