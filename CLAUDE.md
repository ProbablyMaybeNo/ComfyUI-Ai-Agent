# ComfyUI AI Builder — Agent Instructions

## What This Is
A CLI tool that builds, runs, and manages ComfyUI workflows programmatically. All commands output JSON to stdout (machine-readable) and status messages to stderr (human-readable).

## How To Use
All commands run from this project root:
```bash
cd "D:\AI-Workstation\Antigravity\apps\ComfyUI Agent"
python -m comfy_builder <command> [args]
```

## Quick Start
```bash
# 1. Check server is running
python -m comfy_builder status

# 2. Build a workflow
python -m comfy_builder build text2img --prompt "a dragon in a library" --steps 20

# 3. Run it
python -m comfy_builder run current

# 4. View results (outputs JSON with file paths)
python -m comfy_builder logs last
```

## Commands Reference

### Server & Schema
```bash
python -m comfy_builder status                    # Server status, models, VRAM
python -m comfy_builder schema refresh             # Re-cache node schema from ComfyUI
python -m comfy_builder schema search "keyword"    # Find available nodes
```

### Build Workflows
```bash
# Text-to-image
python -m comfy_builder build text2img \
  --prompt "your prompt" \
  --negative "things to avoid" \
  --checkpoint "realvisxlV50_v50LightningBakedvae.safetensors" \
  --steps 20 --cfg 7.0 --width 1024 --height 1024 --seed 42

# LoRA style scenes (batch generation)
python -m comfy_builder build lora_scenes \
  --lora "pixar_style_sdxl.safetensors" \
  --prompt "a cat in {scene}, pixar style" \
  --scenes "a cozy kitchen|a magical forest|outer space" \
  --count 2 \
  --steps 25

# AnimateDiff video
python -m comfy_builder build img2vid \
  --prompt "a cat walking, cinematic" \
  --seconds 1 --fps 8 --seed 42
```

### Run & Inspect
```bash
python -m comfy_builder run current               # Execute current workflow
python -m comfy_builder run <name>                 # Execute named workflow
python -m comfy_builder show current               # Show workflow node summary
python -m comfy_builder list                       # List all workflows/templates/drafts
python -m comfy_builder logs last                  # Last run results
```

### Modify
```bash
python -m comfy_builder refine "set steps to 30"
python -m comfy_builder refine "change cfg to 8.5"
python -m comfy_builder refine "set seed to 12345"
```

### Install & Export
```bash
python -m comfy_builder install check              # Check for missing nodes
python -m comfy_builder install nodes <pack_or_url> # Install custom node pack
python -m comfy_builder export current --name "my_project"
```

## Available Models

### Checkpoints (SDXL)
- `realvisxlV50_v50LightningBakedvae.safetensors` — photorealistic (default)
- `sd_xl_turbo_1.0_fp16.safetensors` — fast generation (fewer steps needed)
- `sd_xl_base_1.0.safetensors` — standard SDXL base
- `robmix_zenithV30.safetensors` — mixed style
- `sd_xl_refiner_1.0.safetensors` — refiner (second-pass detail)

### LoRA Styles
- `pixar_style_sdxl.safetensors` — Pixar 3D look
- `ghibli_style_sdxl.safetensors` — Studio Ghibli anime
- `crayon_style_sdxl.safetensors` — crayon drawing
- `watercolor_style_sdxl.safetensors` — watercolor painting

### Other Models
- IPAdapter SDXL + SD1.5 (face/style transfer from reference images)
- CLIP Vision (required for IPAdapter)
- ControlNet SDXL: canny (edges), depth
- RealESRGAN 4x upscaler (photo + anime variants)
- AnimateDiff SDXL motion module

## Output Locations
- Images: `comfy_builder/out/images/`
- Video: `comfy_builder/out/video/`
- Run logs: `comfy_builder/logs/runs/`
- Current workflow: `comfy_builder/workflows/current.json`

## JSON Output Format
All commands return JSON to stdout. Key fields:
```json
{
  "status": "success|warning|error|blocked",
  "outputs": [{"file": "path/to/image.png", "type": "image"}],
  "error": "description if failed",
  "hint": "what to do next"
}
```

## Important Notes
- ComfyUI server must be running at `http://127.0.0.1:8000`
- ComfyUI path: `C:\Users\Admin\Documents\ComfyUI`
- Video generation (AnimateDiff SDXL) takes ~8 min on the RTX 4060 8GB
- Text2img takes ~20s at 1024x1024
- Use `sd_xl_turbo` with `--steps 4 --cfg 1.0` for fastest results
- After installing new custom nodes, restart ComfyUI and run `schema refresh`

## Workflow Pattern for Agents
1. `status` → verify server is up
2. `build <template> --params` → create workflow
3. `show current` → verify workflow looks right (optional)
4. `run current` → execute and get outputs
5. `logs last` → get output file paths and timing
6. If error: `install check` → see what's missing, then `install nodes <pack>`

## Manual / Live Tests
Tests run against the **live ComfyUI server and window**. Start ComfyUI first, then from project root: `.\run_manual_tests.ps1` (runs all live pytest tests; jobs appear in the ComfyUI queue). For a step-by-step manual flow while watching the ComfyUI window: `.\run_manual_cli_flow.ps1` (status → build text2img → run current → logs last). Live tests are in `comfy_builder/tests/test_live.py` (`pytest -m live -v`). See `comfy_builder/tests/README_LIVE_TESTS.md` for details.

## ComfyUI Agent Panel (Chat UI)
The **builder UI** (chat panel) lives under `comfy_builder` and is run with `python -m comfy_builder chat`. It serves the UI at **http://localhost:8085** and uses **Ollama** so you can converse with an LLM; the LLM uses your prompts to call builder tools and generate workflows/nodes in ComfyUI. **Tests:** unit tests in `comfy_builder/tests/test_chat_panel.py` (tool execution with mocks); live tests hit the panel server and POST `/api/chat` to verify LLM-driven workflow generation. Run panel unit tests: `pytest comfy_builder/tests/test_chat_panel.py -m "not live"`. Run manual/live panel tests: start the panel (`python -m comfy_builder chat`), then `.\run_manual_panel_tests.ps1` or `pytest comfy_builder/tests/test_chat_panel.py -m live -v`. See **comfy_builder/tests/README_PANEL_TESTS.md** for details.

## Test Plan
A full test plan for chat-to-workflow flows, same-subject scenes, and image-to-animation is in **TEST_PLAN.md**. It covers unit/integration/live layers, intent→CLI mapping, lora_scenes and run-scenes, img2vid and “same subject in different situations,” refine, and error handling.
