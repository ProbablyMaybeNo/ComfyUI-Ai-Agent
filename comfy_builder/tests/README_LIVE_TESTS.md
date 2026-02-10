# Manual / Live Tests

Tests that require the **live ComfyUI server and window** to be running. They hit the real API at `COMFYUI_URL` and submit real workflows; you can watch jobs run in the ComfyUI window.

## Prerequisites

1. **ComfyUI running** — Start the ComfyUI app so both the **server** and **window** are up at the URL in `.env` (default `http://127.0.0.1:8000`). Live tests submit real prompts; the queue and progress appear in the ComfyUI window.
2. **Environment**: create a venv and install dev deps:
   ```powershell
   cd "D:\AI-Workstation\Antigravity\apps\ComfyUI Agent"
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   ```
3. **`.env`** in project root (copy from `.env.example` if needed):
   - `COMFYUI_URL` — ComfyUI server URL
   - `COMFYUI_PATH` — ComfyUI install path (for model lists, schema)

## Run live tests

From project root:

```powershell
# All live tests (skipped if server is down)
pytest -m live -v

# Only live tests in test_live.py
pytest comfy_builder/tests/test_live.py -m live -v
```

Or use the helper script (checks server, then runs **all** live tests including E2E):

```powershell
.\run_manual_tests.ps1
```

**Manual CLI flow** (run commands one-by-one while watching the ComfyUI window):

```powershell
.\run_manual_cli_flow.ps1
```

This runs: `status` → `build text2img` → `run current` → `logs last`. The job appears in the ComfyUI queue/window.

## What runs

| Test | Description |
|------|-------------|
| `TestLiveConnectivity` | Server status, `/object_info`, `/queue` |
| `TestLiveText2ImgE2E` | Build text2img → run on server → assert image output exists |
| `TestLiveSchemaFromServer` | Fetch schema from server and cache to disk |

If the server is not reachable, `run_manual_tests.ps1` exits with an error; pytest `-m live` would skip the live tests. Unit tests (no server) are unchanged: run `.\run_tests.ps1` or `pytest` without `-m live` to run only unit tests.
