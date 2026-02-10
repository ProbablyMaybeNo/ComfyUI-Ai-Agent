# Huffle Scenes Workflow Guide

## Overview
Two workflows for generating the same Huffle character in different scenes:

| Workflow | Method | Identity Strength | Requires |
|---|---|---|---|
| `huffle_scenes_main.json` | **IPAdapter** (reference conditioning) | Strong | IPAdapter + CLIP Vision models |
| `huffle_scenes_fallback_img2img.json` | **img2img** (low denoise) | Moderate | Nothing extra (core nodes only) |

## Quick Start (Agent/CLI)

### Using the comfy_builder CLI:
```bash
cd "D:\AI-Workstation\Antigravity\apps\ComfyUI Agent"

# Check server
python -m comfy_builder status

# Run main workflow (IPAdapter)
python -m comfy_builder run huffle_scenes_main

# Or run fallback (img2img)
python -m comfy_builder run huffle_scenes_fallback_img2img
```

### Batch all scenes via CLI:
```bash
python -m comfy_builder run-scenes huffle_scenes_main
```

## Reference Image
- **Current**: `probablymaybenot_A_cute_fat_round_little_creature_with_short_ch_6e11801f-b39b-4ae0-8d0f-57bbaa91284c.png`
- **Location**: `C:\Users\Admin\Documents\ComfyUI\input\`
- To change: replace the `image` value in node `2` (LoadImage) with your image filename
- The image must be placed in ComfyUI's `input/` directory

## How To Change Scenes

### Nodes to edit per scene:

| Node | Field | What to Change |
|---|---|---|
| `10` (SCENE PROMPT) | `text` | Replace the scene description after the character description |
| `50` (SaveImage) | `filename_prefix` | Change to `huffle/<scene_slug>` for organized outputs |
| `30` (KSampler) | `seed` | Keep same seed for consistency, or change for variation |

### Character description anchor (keep this in every prompt):
```
a cute fat round little creature with short stubby arms, big dark glossy eyes, smooth pale body,
```

### Then add your scene:
```
sitting in a grocery store aisle at night, holding a tiny shopping basket, photorealistic, cinematic lighting, 8k, detailed
```

## Scene List
Edit `scenes.txt` (one scene per line). Each scene becomes the variable part of the prompt.

## Recommended Settings

### Main workflow (IPAdapter):
| Setting | Value | Notes |
|---|---|---|
| IPAdapter weight | 0.85 | Higher = more like reference (0.7-0.95 range) |
| Steps | 25 | Lower for speed, higher for quality |
| CFG | 7.0 | Standard guidance |
| Denoise | 1.0 | Full denoise (IPAdapter handles identity) |
| Resolution | 1024x1024 | Keep consistent across all scenes |
| Seed | 42 | Fixed per scene for repeatability |

### Fallback workflow (img2img):
| Setting | Value | Notes |
|---|---|---|
| Denoise | 0.45 | **Critical** — lower keeps more reference identity (0.35-0.55) |
| Steps | 25 | Standard |
| CFG | 7.0 | Standard |
| Resolution | Matches input image | Auto from reference |
| Seed | 42 | Fixed per scene |

## Batching Strategy
ComfyUI doesn't have a built-in "loop over text file" node. Two approaches:

### 1. Agent-driven (recommended):
The comfy_builder CLI handles batching automatically:
```bash
python -m comfy_builder run-scenes huffle_scenes_main
```
This reads `scenes.txt`, patches the prompt and filename per scene, and submits each.

### 2. Manual:
1. Open the workflow
2. Edit node `10` with the new scene prompt
3. Edit node `50` filename_prefix to match the scene
4. Queue the prompt
5. Repeat for each scene

## Output Location
All images save to: `C:\Users\Admin\Documents\ComfyUI\output\huffle\`
Organized by scene slug (e.g., `huffle/grocery_store_00001_.png`)

## Limitations
- No LoRA trained for this specific Huffle character yet
- IPAdapter provides visual similarity but may drift on unusual scenes
- For stronger identity lock: train a LoRA on the Huffle and add a LoraLoader node

## Install Plan (Optional Upgrades)
| Pack | What It Adds |
|---|---|
| Train a Huffle LoRA | Strongest identity preservation |
| ControlNet + depth map | Consistent pose control |
| ComfyUI-Frame-Interpolation | Smooth video from scene keyframes |
