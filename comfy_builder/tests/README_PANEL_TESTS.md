# ComfyUI Agent Panel — Manual and Live Tests

The **ComfyUI Agent Panel** is the chat UI at `comfy_builder/chat/`. It lets you converse with an LLM (Ollama); the LLM uses your prompts to call builder tools and generate workflows/nodes in ComfyUI.

## Path to the builder UI

- **Project root:** `D:\AI-Workstation\Antigravity\apps\ComfyUI Agent`
- **Builder package:** `D:\AI-Workstation\Antigravity\apps\ComfyUI Agent\comfy_builder`
- **Panel (chat):** `comfy_builder/chat/` — server, Ollama client, tools, static UI.

## Recommended LLM models (Ollama)

For this automation/chat system you want a model that **reliably uses tools** (function calling) and follows **structured instructions** (template names, parameters, optional ref image).

| Model | Notes |
|-------|--------|
| **qwen2.5:7b** | Strong tool use and structured output; good balance of speed and quality. You can use **qwen2.5:14b** for more reliable tool choice and parameters. |
| **llama3.1** (8B or 70B) | Native tool calling in Ollama; 8B is fast, 70B is best quality if you have VRAM. |
| **mistral** (7B) | Good instruction following and tool use; fast. |
| **command-r** / **command-r-plus** | Built for tool use and agent workflows; often more consistent on multi-step requests. |

**Practical choice:** Use **qwen2.5:7b** (or **qwen2.5:14b** if you have the RAM) for daily use; switch to **llama3.1:8b** or **command-r** if you prefer. Set via `OLLAMA_MODEL`, e.g. `$env:OLLAMA_MODEL = "qwen2.5:7b"` before starting the panel.

## Prerequisites

1. **Ollama** running (default `http://localhost:11434`) with a model that supports tool calls (see table above).
2. **ComfyUI** running (optional for status/build-only; required for run).
3. **Panel server** — start with:
   ```powershell
   cd "D:\AI-Workstation\Antigravity\apps\ComfyUI Agent"
   python -m comfy_builder chat
   ```
   Panel URL: **http://localhost:8085** (or `CHAT_PORT` from env).

## Running tests

### Unit tests (no server, no LLM)

```powershell
python -m pytest comfy_builder/tests/test_chat_panel.py -v -m "not live" --tb=short
```

Covers: each tool (status, build_workflow, run_workflow, show_workflow, refine_workflow, list_workflows, schema_search, logs_last) with mocked planner/runner/store/api/schema.

### Live panel tests (server + LLM)

1. Start the panel: `python -m comfy_builder chat` (in a separate terminal or background).
2. Run:
   ```powershell
   python -m pytest comfy_builder/tests/test_chat_panel.py -m live -v --tb=short
   ```
   Or use the script: `.\run_manual_panel_tests.ps1`

Live tests:
- **TestPanelEndpoints:** GET `/api/status`, GET `/` (index).
- **TestPanelChatWithLLM:** POST `/api/chat` with prompts that should trigger the LLM to call tools (e.g. "What is ComfyUI status?", "Build text2img with prompt 'a red apple' and run it"). Requires Ollama (and optionally ComfyUI for run).

## Manual verification (converse in the UI)

1. Start **Ollama** and pull a model: `ollama pull llama3.1`
2. Start **ComfyUI** (desktop or server).
3. Start the panel: `python -m comfy_builder chat`
4. Open **http://localhost:8085** in a browser.
5. In the chat input, try for example:
   - "What is the ComfyUI status?"
   - "Build a text2img workflow with prompt 'a red apple on a table' and run it."
   - "Show me the current workflow."
   - "Set steps to 25 and run again."

Confirm that the LLM responds and that tool results (status, build_workflow, run_workflow, etc.) appear and that workflows are generated/run in ComfyUI.

## Reference image upload
You can attach a **reference image** in the chat panel (button “Attach reference image”). The image is uploaded to ComfyUI’s input folder and its filename is sent with your message. Use it for **lora_scenes** (same character in different scenes) or **img2vid** (animate this image). The LLM is instructed to use the `ref` parameter when you attach an image and ask for those workflow types.

## Manual test results (panel + live ComfyUI)

Manual API tests were run against the panel and live ComfyUI:

- **GET /api/status** — 200; returns `ollama` (online, models list), `comfyui` (online), `model`.
- **POST /api/chat** — "What is the ComfyUI server status?" → 200; LLM called `status` tool and returned a natural-language summary (ComfyUI version, RAM, GPU, checkpoints, LoRAs).
- **POST /api/chat** — "Build a text2img workflow with prompt 'a red apple on a wooden table', then run it" → server logged `build_workflow(...)` and `run_workflow({"name": "current"})`, and ComfyUI queue showed `Queued: prompt_id=...`. The HTTP client can timeout (e.g. 180s) because the panel is single-threaded and waits for ComfyUI execution to finish before replying.

**Ollama model:** Set `OLLAMA_MODEL` to a model you have (e.g. `qwen2.5:7b`). Default `llama3.1` will 404 if not installed. Example: `$env:OLLAMA_MODEL = "qwen2.5:7b"; python -m comfy_builder chat`.

**Ollama timeout:** If you see "Error contacting Ollama: timed out", the first request (or a busy model) can exceed the default. Set `OLLAMA_TIMEOUT` (seconds); default is 300. Example: `$env:OLLAMA_TIMEOUT = "600"; python -m comfy_builder chat`.
