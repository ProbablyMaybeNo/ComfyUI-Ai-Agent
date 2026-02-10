# ComfyUI Agent

CLI and chat interface to build, run, and manage [ComfyUI](https://github.com/comfyanonymous/ComfyUI) workflows from the command line or via natural language (Ollama-backed chat).

## Features

- **Build** workflows from templates: text2img, lora_scenes (same subject, multiple scenes), img2vid (AnimateDiff or keyframes).
- **Run** workflows against a local ComfyUI server; batch runs for lora_scenes.
- **Refine** the current workflow with natural-language instructions (e.g. “set steps to 30”, “change prompt to …”).
- **Chat UI** — optional web panel that talks to Ollama and invokes the builder (build/run/refine) via tools.
- **Install** custom node packs and check for missing nodes/models.

## Quick start

```powershell
cd "D:\AI-Workstation\Antigravity\apps\ComfyUI Agent"
# Or your clone path

# 1. Check ComfyUI is running
python -m comfy_builder status

# 2. Build and run a single image
python -m comfy_builder build text2img --prompt "a dragon in a library" --steps 20
python -m comfy_builder run current

# 3. View results
python -m comfy_builder logs last
```

Copy `.env.example` to `.env` and set `COMFYUI_URL` and `COMFYUI_PATH` if needed.

## Tests

- **Unit + CLI errors:** `.\run_tests.ps1` (no ComfyUI required).
- **Live tests:** `.\run_manual_tests.ps1` or `pytest -m live -v` (ComfyUI must be running).

See **CLAUDE.md** for full command reference and **TEST_PLAN.md** for the test plan.

## License

See repository license file if present.
