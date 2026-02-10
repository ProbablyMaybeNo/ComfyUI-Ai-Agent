"""ComfyUI AI Builder — Workflow Planner.

Turns high-level build requests into Graph Ops sequences,
then applies them to create workflow JSON.
"""

import random
import sys

from . import config, schema as schema_mod, graph_ops, store


def build(template: str, params: dict) -> dict:
    """Build a workflow from a template name and parameters.

    Returns:
        Result dict with status, workflow path, and summary.
    """
    builders = {
        "text2img": _build_text2img,
        "img2img": _build_img2img,
        "ref_poses": _build_ref_poses,
        "lora_scenes": _build_lora_scenes,
        "img2vid": _build_img2vid,
    }

    builder = builders.get(template)
    if not builder:
        return {"status": "error", "error": f"Unknown template '{template}'. Available: {list(builders.keys())}"}

    # Ensure schema is loaded (best-effort; build proceeds even without)
    s = schema_mod.load()
    if not s:
        try:
            print("Schema not cached. Fetching...", file=sys.stderr)
            schema_mod.refresh()
        except Exception:
            print("Warning: could not fetch schema. Building without validation.", file=sys.stderr)

    try:
        ops, meta = builder(params)
    except Exception as e:
        return {"status": "error", "error": str(e)}

    # Apply ops to empty workflow
    workflow = {}
    graph_ops.apply_ops(workflow, ops)

    # Save as current (always save, even with validation warnings)
    store.save_current(workflow)

    # Save build metadata (batch info etc.) for runner
    from .utils import save_json
    meta_path = config.WORKFLOWS_DIR / "current_meta.json"
    save_json(meta_path, meta)

    # Validate (warnings only — workflow is still saved)
    warnings = graph_ops.validate_workflow(workflow, strict=False)

    result = {
        "status": "success",
        "template": template,
        "workflow_path": str(config.CURRENT_WORKFLOW),
        "node_count": len(workflow),
        "parameters": meta,
    }
    if warnings:
        result["status"] = "warning"
        result["warnings"] = warnings

    return result


def _resolve(params: dict, key: str, default):
    """Get param value with fallback to config defaults."""
    return params.get(key, default)


def _build_text2img(params: dict) -> tuple[list[dict], dict]:
    """Build a minimal text2img SDXL workflow."""
    ckpt = _resolve(params, "checkpoint", config.DEFAULT_CHECKPOINT)
    prompt = _resolve(params, "prompt", "a beautiful landscape, 8k, photorealistic")
    negative = _resolve(params, "negative", config.DEFAULT_NEGATIVE)
    steps = _resolve(params, "steps", config.DEFAULT_STEPS)
    cfg = _resolve(params, "cfg", config.DEFAULT_CFG)
    width = _resolve(params, "width", config.DEFAULT_WIDTH)
    height = _resolve(params, "height", config.DEFAULT_HEIGHT)
    seed = _resolve(params, "seed", random.randint(1, 2**32 - 1))
    sampler = _resolve(params, "sampler", config.DEFAULT_SAMPLER)
    scheduler = _resolve(params, "scheduler", config.DEFAULT_SCHEDULER)

    ops = [
        {"op": "add_node", "id": "1", "class_type": "CheckpointLoaderSimple",
         "inputs": {"ckpt_name": ckpt}},
        {"op": "add_node", "id": "2", "class_type": "CLIPTextEncode",
         "inputs": {"text": prompt}},
        {"op": "add_node", "id": "3", "class_type": "CLIPTextEncode",
         "inputs": {"text": negative}},
        {"op": "add_node", "id": "4", "class_type": "EmptyLatentImage",
         "inputs": {"width": width, "height": height, "batch_size": 1}},
        {"op": "add_node", "id": "5", "class_type": "KSampler",
         "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                    "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0}},
        {"op": "add_node", "id": "6", "class_type": "VAEDecode", "inputs": {}},
        {"op": "add_node", "id": "7", "class_type": "SaveImage",
         "inputs": {"filename_prefix": "comfy_builder/text2img"}},
        # Connections
        {"op": "connect", "from_id": "1", "from_output": 0, "to_id": "5", "to_input": "model"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "2", "to_input": "clip"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "3", "to_input": "clip"},
        {"op": "connect", "from_id": "2", "from_output": 0, "to_id": "5", "to_input": "positive"},
        {"op": "connect", "from_id": "3", "from_output": 0, "to_id": "5", "to_input": "negative"},
        {"op": "connect", "from_id": "4", "from_output": 0, "to_id": "5", "to_input": "latent_image"},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "6", "to_input": "vae"},
        {"op": "connect", "from_id": "5", "from_output": 0, "to_id": "6", "to_input": "samples"},
        {"op": "connect", "from_id": "6", "from_output": 0, "to_id": "7", "to_input": "images"},
    ]

    meta = {
        "checkpoint": ckpt, "prompt": prompt, "negative": negative,
        "steps": steps, "cfg": cfg, "width": width, "height": height,
        "seed": seed, "sampler": sampler, "scheduler": scheduler,
    }
    return ops, meta


def _build_img2img(params: dict) -> tuple[list[dict], dict]:
    """Build image-to-image workflow using a reference image (e.g. uploaded in chat).

    Requires ref=filename in ComfyUI input folder. LoadImage → VAEEncode → KSampler(denoise) → VAEDecode → SaveImage.
    """
    ref = params.get("ref")
    if not ref:
        raise ValueError("img2img requires a reference image (ref=filename). Use the attached image in chat.")
    ckpt = _resolve(params, "checkpoint", config.DEFAULT_CHECKPOINT)
    prompt = _resolve(params, "prompt", "enhance details, high quality")
    negative = _resolve(params, "negative", config.DEFAULT_NEGATIVE)
    steps = _resolve(params, "steps", config.DEFAULT_STEPS)
    cfg = _resolve(params, "cfg", config.DEFAULT_CFG)
    denoise = _resolve(params, "denoise", 0.75)
    seed = _resolve(params, "seed", random.randint(1, 2**32 - 1))
    sampler = _resolve(params, "sampler", config.DEFAULT_SAMPLER)
    scheduler = _resolve(params, "scheduler", config.DEFAULT_SCHEDULER)

    ops = [
        {"op": "add_node", "id": "1", "class_type": "CheckpointLoaderSimple",
         "inputs": {"ckpt_name": ckpt}},
        {"op": "add_node", "id": "2", "class_type": "LoadImage",
         "inputs": {"image": ref}},
        {"op": "add_node", "id": "3", "class_type": "VAEEncode", "inputs": {}},
        {"op": "add_node", "id": "4", "class_type": "CLIPTextEncode",
         "inputs": {"text": prompt}},
        {"op": "add_node", "id": "5", "class_type": "CLIPTextEncode",
         "inputs": {"text": negative}},
        {"op": "add_node", "id": "6", "class_type": "KSampler",
         "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                    "sampler_name": sampler, "scheduler": scheduler, "denoise": denoise}},
        {"op": "add_node", "id": "7", "class_type": "VAEDecode", "inputs": {}},
        {"op": "add_node", "id": "8", "class_type": "SaveImage",
         "inputs": {"filename_prefix": "comfy_builder/img2img"}},
        {"op": "connect", "from_id": "1", "from_output": 0, "to_id": "6", "to_input": "model"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "4", "to_input": "clip"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "5", "to_input": "clip"},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "3", "to_input": "vae"},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "7", "to_input": "vae"},
        {"op": "connect", "from_id": "2", "from_output": 0, "to_id": "3", "to_input": "pixels"},
        {"op": "connect", "from_id": "3", "from_output": 0, "to_id": "6", "to_input": "latent_image"},
        {"op": "connect", "from_id": "4", "from_output": 0, "to_id": "6", "to_input": "positive"},
        {"op": "connect", "from_id": "5", "from_output": 0, "to_id": "6", "to_input": "negative"},
        {"op": "connect", "from_id": "6", "from_output": 0, "to_id": "7", "to_input": "samples"},
        {"op": "connect", "from_id": "7", "from_output": 0, "to_id": "8", "to_input": "images"},
    ]
    meta = {
        "checkpoint": ckpt, "prompt": prompt, "negative": negative,
        "steps": steps, "cfg": cfg, "denoise": denoise, "seed": seed,
        "ref": ref, "sampler": sampler, "scheduler": scheduler,
    }
    return ops, meta


def _build_ref_poses(params: dict) -> tuple[list[dict], dict]:
    """Build image-to-image workflow for one reference image, multiple pose prompts.

    Same graph as img2img. Runner will run once per pose (batch), replacing the prompt each time.
    Use case: 'put this person in different poses' — ref = subject, poses = pipe-separated descriptions.
    """
    ref = params.get("ref")
    if not ref:
        raise ValueError("ref_poses requires a reference image (ref=filename). Use the attached image in chat.")
    poses_str = params.get("poses", "").strip() or params.get("scenes", "").strip()
    if not poses_str:
        raise ValueError("ref_poses requires poses (pipe-separated), e.g. 'standing|sitting|waving'.")
    poses = [p.strip() for p in poses_str.split("|") if p.strip()]
    if not poses:
        raise ValueError("ref_poses requires at least one pose description.")

    ckpt = _resolve(params, "checkpoint", config.DEFAULT_CHECKPOINT)
    negative = _resolve(params, "negative", config.DEFAULT_NEGATIVE)
    steps = _resolve(params, "steps", config.DEFAULT_STEPS)
    cfg = _resolve(params, "cfg", config.DEFAULT_CFG)
    denoise = _resolve(params, "denoise", 0.75)
    base_seed = _resolve(params, "seed", random.randint(1, 2**32 - 1))
    sampler = _resolve(params, "sampler", config.DEFAULT_SAMPLER)
    scheduler = _resolve(params, "scheduler", config.DEFAULT_SCHEDULER)

    # One workflow; first prompt is first pose (runner will replace per batch item)
    ops = [
        {"op": "add_node", "id": "1", "class_type": "CheckpointLoaderSimple",
         "inputs": {"ckpt_name": ckpt}},
        {"op": "add_node", "id": "2", "class_type": "LoadImage",
         "inputs": {"image": ref}},
        {"op": "add_node", "id": "3", "class_type": "VAEEncode", "inputs": {}},
        {"op": "add_node", "id": "4", "class_type": "CLIPTextEncode",
         "inputs": {"text": poses[0]}},
        {"op": "add_node", "id": "5", "class_type": "CLIPTextEncode",
         "inputs": {"text": negative}},
        {"op": "add_node", "id": "6", "class_type": "KSampler",
         "inputs": {"seed": base_seed, "steps": steps, "cfg": cfg,
                    "sampler_name": sampler, "scheduler": scheduler, "denoise": denoise}},
        {"op": "add_node", "id": "7", "class_type": "VAEDecode", "inputs": {}},
        {"op": "add_node", "id": "8", "class_type": "SaveImage",
         "inputs": {"filename_prefix": "comfy_builder/pose_0"}},
        {"op": "connect", "from_id": "1", "from_output": 0, "to_id": "6", "to_input": "model"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "4", "to_input": "clip"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "5", "to_input": "clip"},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "3", "to_input": "vae"},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "7", "to_input": "vae"},
        {"op": "connect", "from_id": "2", "from_output": 0, "to_id": "3", "to_input": "pixels"},
        {"op": "connect", "from_id": "3", "from_output": 0, "to_id": "6", "to_input": "latent_image"},
        {"op": "connect", "from_id": "4", "from_output": 0, "to_id": "6", "to_input": "positive"},
        {"op": "connect", "from_id": "5", "from_output": 0, "to_id": "6", "to_input": "negative"},
        {"op": "connect", "from_id": "6", "from_output": 0, "to_id": "7", "to_input": "samples"},
        {"op": "connect", "from_id": "7", "from_output": 0, "to_id": "8", "to_input": "images"},
    ]
    seed = base_seed
    batch = []
    for i, pose_prompt in enumerate(poses):
        batch.append({
            "prompt": pose_prompt,
            "scene": pose_prompt,
            "seed": seed,
            "filename_prefix": f"comfy_builder/pose_{i}",
        })
        seed += 1

    meta = {
        "checkpoint": ckpt, "negative": negative,
        "steps": steps, "cfg": cfg, "denoise": denoise,
        "ref": ref, "poses": poses, "batch": batch,
        "sampler": sampler, "scheduler": scheduler,
    }
    return ops, meta


def _build_lora_scenes(params: dict) -> tuple[list[dict], dict]:
    """Build a LoRA scenes batch workflow.

    Generates one workflow per scene (saved as current; runner handles batch).
    Returns ops for the first scene; batch params stored in meta.
    """
    ckpt = _resolve(params, "checkpoint", config.DEFAULT_CHECKPOINT)
    lora = params.get("lora")
    if not lora:
        raise ValueError("--lora is required for lora_scenes template")

    lora_strength = _resolve(params, "lora_strength", 0.85)
    prompt_template = _resolve(params, "prompt", "photo of subject, {scene}, professional photography, 8k")
    negative = _resolve(params, "negative", config.DEFAULT_NEGATIVE)
    scenes_str = params.get("scenes", "default scene")
    scenes = [s.strip() for s in scenes_str.split("|")]
    count = _resolve(params, "count", 1)
    steps = _resolve(params, "steps", 25)
    cfg = _resolve(params, "cfg", config.DEFAULT_CFG)
    width = _resolve(params, "width", config.DEFAULT_WIDTH)
    height = _resolve(params, "height", config.DEFAULT_HEIGHT)
    sampler = _resolve(params, "sampler", config.DEFAULT_SAMPLER)
    scheduler = _resolve(params, "scheduler", config.DEFAULT_SCHEDULER)
    base_seed = _resolve(params, "seed", random.randint(1, 2**30))

    # Validate batch size
    total_images = len(scenes) * count
    if total_images > config.MAX_BATCH_SIZE:
        raise ValueError(
            f"Batch size {total_images} ({len(scenes)} scenes x {count} each) "
            f"exceeds limit of {config.MAX_BATCH_SIZE}"
        )

    # Check for ref image → IPAdapter path
    ref = params.get("ref")
    use_ipadapter = ref is not None

    # Build base ops (LoRA spine)
    first_scene = scenes[0] if scenes else "default scene"
    first_prompt = prompt_template.replace("{scene}", first_scene)

    ops = [
        {"op": "add_node", "id": "1", "class_type": "CheckpointLoaderSimple",
         "inputs": {"ckpt_name": ckpt}},
        {"op": "add_node", "id": "2", "class_type": "LoraLoader",
         "inputs": {"lora_name": lora, "strength_model": lora_strength,
                    "strength_clip": lora_strength}},
        {"op": "connect", "from_id": "1", "from_output": 0, "to_id": "2", "to_input": "model"},
        {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "2", "to_input": "clip"},
        {"op": "add_node", "id": "3", "class_type": "CLIPTextEncode",
         "inputs": {"text": first_prompt}},
        {"op": "add_node", "id": "4", "class_type": "CLIPTextEncode",
         "inputs": {"text": negative}},
        {"op": "connect", "from_id": "2", "from_output": 1, "to_id": "3", "to_input": "clip"},
        {"op": "connect", "from_id": "2", "from_output": 1, "to_id": "4", "to_input": "clip"},
        {"op": "add_node", "id": "5", "class_type": "EmptyLatentImage",
         "inputs": {"width": width, "height": height, "batch_size": 1}},
        {"op": "add_node", "id": "6", "class_type": "KSampler",
         "inputs": {"seed": base_seed, "steps": steps, "cfg": cfg,
                    "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0}},
        {"op": "connect", "from_id": "2", "from_output": 0, "to_id": "6", "to_input": "model"},
        {"op": "connect", "from_id": "3", "from_output": 0, "to_id": "6", "to_input": "positive"},
        {"op": "connect", "from_id": "4", "from_output": 0, "to_id": "6", "to_input": "negative"},
        {"op": "connect", "from_id": "5", "from_output": 0, "to_id": "6", "to_input": "latent_image"},
        {"op": "add_node", "id": "7", "class_type": "VAEDecode", "inputs": {}},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "7", "to_input": "vae"},
        {"op": "connect", "from_id": "6", "from_output": 0, "to_id": "7", "to_input": "samples"},
        {"op": "add_node", "id": "8", "class_type": "SaveImage",
         "inputs": {"filename_prefix": f"comfy_builder/lora_{first_scene.replace(' ', '_')}"}},
        {"op": "connect", "from_id": "7", "from_output": 0, "to_id": "8", "to_input": "images"},
    ]

    # Generate batch plan (all scenes x count)
    batch = []
    seed = base_seed
    for scene in scenes:
        for i in range(count):
            batch.append({
                "scene": scene,
                "index": i,
                "seed": seed,
                "prompt": prompt_template.replace("{scene}", scene),
                "filename_prefix": f"comfy_builder/lora_{scene.replace(' ', '_')}_{i}",
            })
            seed += 1

    meta = {
        "checkpoint": ckpt, "lora": lora, "lora_strength": lora_strength,
        "prompt_template": prompt_template, "negative": negative,
        "scenes": scenes, "count_per_scene": count, "total_images": len(batch),
        "steps": steps, "cfg": cfg, "width": width, "height": height,
        "sampler": sampler, "scheduler": scheduler,
        "use_ipadapter": use_ipadapter, "ref": ref,
        "batch": batch,
    }
    return ops, meta


def _build_img2vid(params: dict) -> tuple[list[dict], dict]:
    """Build an image-to-video workflow.

    Strategy 2A: AnimateDiff (if nodes available).
    Strategy 2B: Keyframes fallback.
    """
    ckpt = _resolve(params, "checkpoint", config.DEFAULT_CHECKPOINT)
    ref = params.get("ref")
    prompt = _resolve(params, "prompt", "a person in motion, cinematic, smooth")
    negative = _resolve(params, "negative", config.DEFAULT_NEGATIVE + ", static, morphing face")
    seconds = _resolve(params, "seconds", 2)
    fps = _resolve(params, "fps", 12)
    lora = params.get("lora")
    lora_strength = _resolve(params, "lora_strength", 0.8)
    style = params.get("style", "")
    steps = _resolve(params, "steps", 20)
    cfg = _resolve(params, "cfg", config.DEFAULT_CFG)
    seed = _resolve(params, "seed", random.randint(1, 2**32 - 1))
    denoise = _resolve(params, "denoise", 0.8)

    if style:
        prompt = f"{prompt}, {style}"

    total_frames = int(seconds * fps)

    # Check if AnimateDiff nodes are available
    has_animatediff = schema_mod.node_exists("ADE_AnimateDiffLoaderWithContext")
    # Detect video output: prefer core CreateVideo/SaveVideo, fallback to VHS_VideoCombine
    has_core_video = schema_mod.node_exists("CreateVideo") and schema_mod.node_exists("SaveVideo")
    has_vhs_video = schema_mod.node_exists("VHS_VideoCombine")
    has_video_output = has_core_video or has_vhs_video
    video_backend = "core" if has_core_video else ("vhs" if has_vhs_video else None)

    if has_animatediff and has_video_output:
        strategy = "2A_animatediff"
        ops = _img2vid_animatediff(
            ckpt, prompt, negative, seed, steps, cfg, denoise,
            total_frames, fps, lora, lora_strength, ref, video_backend,
        )
    else:
        strategy = "2B_keyframes"
        ops = _img2vid_keyframes(
            ckpt, prompt, negative, seed, steps, cfg,
            fps, lora, lora_strength, ref,
        )

    meta = {
        "strategy": strategy,
        "checkpoint": ckpt, "prompt": prompt, "negative": negative,
        "seconds": seconds, "fps": fps, "total_frames": total_frames,
        "lora": lora, "ref": ref, "style": style,
        "steps": steps, "cfg": cfg, "seed": seed, "denoise": denoise,
        "has_animatediff": has_animatediff, "has_video_output": has_video_output,
        "video_backend": video_backend,
    }
    return ops, meta


def _img2vid_animatediff(ckpt, prompt, negative, seed, steps, cfg, denoise,
                          total_frames, fps, lora, lora_strength, ref,
                          video_backend="core") -> list[dict]:
    """Build AnimateDiff workflow ops.

    Args:
        video_backend: "core" for CreateVideo/SaveVideo, "vhs" for VHS_VideoCombine.
    """
    ops = [
        {"op": "add_node", "id": "1", "class_type": "CheckpointLoaderSimple",
         "inputs": {"ckpt_name": ckpt}},
    ]

    model_source = "1"  # tracks which node outputs the model

    # Optional LoRA
    if lora:
        ops.extend([
            {"op": "add_node", "id": "2", "class_type": "LoraLoader",
             "inputs": {"lora_name": lora, "strength_model": lora_strength,
                        "strength_clip": lora_strength}},
            {"op": "connect", "from_id": "1", "from_output": 0, "to_id": "2", "to_input": "model"},
            {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "2", "to_input": "clip"},
        ])
        model_source = "2"
        clip_source = "2"
    else:
        clip_source = "1"

    # AnimateDiff loader (Legacy Gen1 — feeds model in, gets model out)
    ops.extend([
        {"op": "add_node", "id": "10", "class_type": "ADE_AnimateDiffLoaderWithContext",
         "inputs": {"model_name": "mm_sdxl_v10_beta.ckpt",
                    "beta_schedule": "linear (AnimateDiff-SDXL)"}},
        {"op": "connect", "from_id": model_source, "from_output": 0,
         "to_id": "10", "to_input": "model"},
    ])
    model_source = "10"

    # CLIP encode
    ops.extend([
        {"op": "add_node", "id": "20", "class_type": "CLIPTextEncode",
         "inputs": {"text": prompt}},
        {"op": "add_node", "id": "21", "class_type": "CLIPTextEncode",
         "inputs": {"text": negative}},
        {"op": "connect", "from_id": clip_source, "from_output": 1,
         "to_id": "20", "to_input": "clip"},
        {"op": "connect", "from_id": clip_source, "from_output": 1,
         "to_id": "21", "to_input": "clip"},
    ])

    # Latent
    ops.append(
        {"op": "add_node", "id": "30", "class_type": "EmptyLatentImage",
         "inputs": {"width": 512, "height": 512, "batch_size": total_frames}},
    )

    # Sampler
    ops.extend([
        {"op": "add_node", "id": "40", "class_type": "KSampler",
         "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                    "sampler_name": "euler", "scheduler": "normal", "denoise": denoise}},
        {"op": "connect", "from_id": model_source, "from_output": 0,
         "to_id": "40", "to_input": "model"},
        {"op": "connect", "from_id": "20", "from_output": 0,
         "to_id": "40", "to_input": "positive"},
        {"op": "connect", "from_id": "21", "from_output": 0,
         "to_id": "40", "to_input": "negative"},
        {"op": "connect", "from_id": "30", "from_output": 0,
         "to_id": "40", "to_input": "latent_image"},
    ])

    # VAE Decode
    ops.extend([
        {"op": "add_node", "id": "50", "class_type": "VAEDecode", "inputs": {}},
        {"op": "connect", "from_id": "1", "from_output": 2,
         "to_id": "50", "to_input": "vae"},
        {"op": "connect", "from_id": "40", "from_output": 0,
         "to_id": "50", "to_input": "samples"},
    ])

    # Create video from frames, then save
    if video_backend == "vhs":
        # VHS_VideoCombine: takes images directly, outputs video file
        ops.extend([
            {"op": "add_node", "id": "60", "class_type": "VHS_VideoCombine",
             "inputs": {"frame_rate": fps, "format": "video/h264-mp4",
                        "filename_prefix": "comfy_builder/vid",
                        "pingpong": False, "save_output": True}},
            {"op": "connect", "from_id": "50", "from_output": 0,
             "to_id": "60", "to_input": "images"},
        ])
    else:
        # Core ComfyUI: CreateVideo → SaveVideo pipeline
        ops.extend([
            {"op": "add_node", "id": "60", "class_type": "CreateVideo",
             "inputs": {"fps": fps}},
            {"op": "connect", "from_id": "50", "from_output": 0,
             "to_id": "60", "to_input": "images"},
            {"op": "add_node", "id": "61", "class_type": "SaveVideo",
             "inputs": {"filename_prefix": "comfy_builder/vid",
                        "format": "mp4", "codec": "h264"}},
            {"op": "connect", "from_id": "60", "from_output": 0,
             "to_id": "61", "to_input": "video"},
        ])

    return ops


def _img2vid_keyframes(ckpt, prompt, negative, seed, steps, cfg,
                        fps, lora, lora_strength, ref) -> list[dict]:
    """Build keyframes fallback workflow ops (generates 4 keyframe images)."""
    # For the fallback, we generate individual keyframe images
    # that will be interpolated externally via ffmpeg
    ops = [
        {"op": "add_node", "id": "1", "class_type": "CheckpointLoaderSimple",
         "inputs": {"ckpt_name": ckpt}},
    ]

    model_source = "1"
    clip_source = "1"

    if lora:
        ops.extend([
            {"op": "add_node", "id": "2", "class_type": "LoraLoader",
             "inputs": {"lora_name": lora, "strength_model": lora_strength,
                        "strength_clip": lora_strength}},
            {"op": "connect", "from_id": "1", "from_output": 0, "to_id": "2", "to_input": "model"},
            {"op": "connect", "from_id": "1", "from_output": 1, "to_id": "2", "to_input": "clip"},
        ])
        model_source = "2"
        clip_source = "2"

    ops.extend([
        {"op": "add_node", "id": "3", "class_type": "CLIPTextEncode",
         "inputs": {"text": prompt}},
        {"op": "add_node", "id": "4", "class_type": "CLIPTextEncode",
         "inputs": {"text": negative}},
        {"op": "connect", "from_id": clip_source, "from_output": 1, "to_id": "3", "to_input": "clip"},
        {"op": "connect", "from_id": clip_source, "from_output": 1, "to_id": "4", "to_input": "clip"},
        {"op": "add_node", "id": "5", "class_type": "EmptyLatentImage",
         "inputs": {"width": 1024, "height": 1024, "batch_size": 4}},
        {"op": "add_node", "id": "6", "class_type": "KSampler",
         "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                    "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        {"op": "connect", "from_id": model_source, "from_output": 0, "to_id": "6", "to_input": "model"},
        {"op": "connect", "from_id": "3", "from_output": 0, "to_id": "6", "to_input": "positive"},
        {"op": "connect", "from_id": "4", "from_output": 0, "to_id": "6", "to_input": "negative"},
        {"op": "connect", "from_id": "5", "from_output": 0, "to_id": "6", "to_input": "latent_image"},
        {"op": "add_node", "id": "7", "class_type": "VAEDecode", "inputs": {}},
        {"op": "connect", "from_id": "1", "from_output": 2, "to_id": "7", "to_input": "vae"},
        {"op": "connect", "from_id": "6", "from_output": 0, "to_id": "7", "to_input": "samples"},
        {"op": "add_node", "id": "8", "class_type": "SaveImage",
         "inputs": {"filename_prefix": "comfy_builder/keyframe"}},
        {"op": "connect", "from_id": "7", "from_output": 0, "to_id": "8", "to_input": "images"},
    ])

    return ops


def refine(instruction: str) -> dict:
    """Apply a refinement instruction to the current workflow.

    Parses simple instructions and maps to Graph Ops.
    """
    workflow = store.load_current()
    if not workflow:
        return {"status": "error", "error": "No current workflow to refine"}

    ops = _parse_refinement(instruction, workflow)
    if not ops:
        return {"status": "error", "error": f"Could not parse refinement: '{instruction}'"}

    graph_ops.apply_ops(workflow, ops)
    store.save_current(workflow)

    return {
        "status": "success",
        "ops_applied": len(ops),
        "ops": ops,
        "workflow_path": str(config.CURRENT_WORKFLOW),
    }


def _parse_refinement(instruction: str, workflow: dict) -> list[dict]:
    """Parse a refinement instruction into Graph Ops.

    Handles simple patterns:
    - "set steps to 30" / "increase steps to 30"
    - "change cfg to 8.5"
    - "set seed to 12345"
    - "change prompt to ..."
    """
    ops = []
    instruction_lower = instruction.lower()

    # Pattern: "set/change <key> to <value>"
    import re
    patterns = [
        (r"(?:set|change|increase|decrease)\s+steps\s+to\s+(\d+)", "steps", int),
        (r"(?:set|change)\s+cfg\s+to\s+([\d.]+)", "cfg", float),
        (r"(?:set|change)\s+seed\s+to\s+(\d+)", "seed", int),
        (r"(?:set|change)\s+denoise\s+to\s+([\d.]+)", "denoise", float),
        (r"(?:set|change)\s+width\s+to\s+(\d+)", "width", int),
        (r"(?:set|change)\s+height\s+to\s+(\d+)", "height", int),
        (r"(?:set|change)\s+sampler\s+to\s+(\w+)", "sampler_name", str),
        (r"(?:set|change)\s+scheduler\s+to\s+(\w+)", "scheduler", str),
    ]

    for pattern, key, cast in patterns:
        match = re.search(pattern, instruction_lower)
        if match:
            value = cast(match.group(1))
            # Find nodes that have this input key
            for node_id, node in workflow.items():
                if key in node.get("inputs", {}):
                    ops.append({"op": "set_input", "id": node_id, "key": key, "value": value})

    # Pattern: "change prompt to ..."
    prompt_match = re.search(r"(?:set|change)\s+prompt\s+to\s+(.+)", instruction, re.IGNORECASE)
    if prompt_match:
        new_prompt = prompt_match.group(1).strip().strip('"\'')
        for node_id, node in workflow.items():
            if node.get("class_type") == "CLIPTextEncode" and "text" in node.get("inputs", {}):
                # Only change the positive prompt (first CLIPTextEncode typically)
                ops.append({"op": "set_input", "id": node_id, "key": "text", "value": new_prompt})
                break  # only first one

    return ops
