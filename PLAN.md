# ComfyUI AI Builder — Planning & Specification Document

**Date:** 2026-02-08
**Status:** IMPLEMENTED — All milestones (M0-M4) complete + unit tests (99 passing) + template workflows
**ComfyUI Location:** `C:\Users\Admin\Documents\ComfyUI`
**Builder Location:** `D:\AI-Workstation\Antigravity\apps\ComfyUI Agent\comfy_builder\`
**Project Root:** `D:\AI-Workstation\Antigravity\apps\ComfyUI Agent\`

## Defaults Assumed (no questions needed)

| Parameter | Default |
|---|---|
| Base model family | **SDXL** (sd_xl_base_1.0, realvisxlV50, sd_xl_turbo available) |
| LoRA files | User will provide .safetensors → placed in `ComfyUI/models/loras/` |
| Image-to-video strategy | **AnimateDiff first** (model dir exists + IPAdapter installed); keyframes+ffmpeg fallback |
| ComfyUI server | `http://127.0.0.1:8000` |
| Primary interface | **CLI** (`python -m comfy_builder <cmd>`) for Cursor agent compatibility |
| Python env | System Python 3.13 (or ComfyUI's embedded env for pip installs into custom_nodes) |

---

## SECTION 1 — Architecture Overview

### Components

```
┌─────────────────────────────────────────────────────────┐
│                   Cursor Agent / User Chat               │
│  (parses /comfy commands, calls CLI, shows results)      │
└──────────────────────────┬──────────────────────────────┘
                           │
                  CLI: python -m comfy_builder <cmd>
                           │
         ┌─────────────────┼──────────────────────┐
         ▼                 ▼                      ▼
┌──────────────┐  ┌────────────────┐  ┌───────────────────┐
│  Command     │  │  Workflow      │  │  Installer /      │
│  Router      │  │  Planner       │  │  Dependency Mgr   │
│  (cli.py)    │  │  (planner.py)  │  │  (installer.py)   │
└──────┬───────┘  └───────┬────────┘  └─────────┬─────────┘
       │                  │                     │
       ▼                  ▼                     ▼
┌──────────────┐  ┌────────────────┐  ┌───────────────────┐
│  ComfyUI     │  │  Graph Ops     │  │  Schema Cache     │
│  API Client  │  │  Engine        │  │  (node_schema.json)│
│  (api.py)    │  │  (graph_ops.py)│  │  (schema.py)      │
└──────┬───────┘  └───────┬────────┘  └───────────────────┘
       │                  │
       ▼                  ▼
┌──────────────┐  ┌────────────────┐
│  Runner +    │  │  Workflow      │
│  Output      │  │  Store         │
│  Collector   │  │  (JSON files)  │
│  (runner.py) │  │                │
└──────┬───────┘  └────────────────┘
       │
       ▼
┌──────────────┐
│  Error       │
│  Interpreter │
│  + Self-Heal │
│  (healer.py) │
└──────────────┘
```

### Dataflow

```
User Chat
  → Cursor Agent (parse /comfy command)
    → CLI Router (dispatch to subcommand)
      → Schema Cache (ensure node_schema.json is current)
        → Workflow Planner (turn request into Graph Ops sequence)
          → Graph Ops Engine (apply ops to workflow JSON, validate)
            → Workflow Store (save current.json)
              → Runner (POST /prompt to ComfyUI)
                → Output Collector (poll history, save images/video)
                  → Error Interpreter (if failure: parse, propose fix)
                    → [loop back to Graph Ops if auto-fixable]
                      → Report (log run, present to user)
```

### Component Responsibilities

| Component | File | Responsibility |
|---|---|---|
| **API Client** | `api.py` | HTTP calls to ComfyUI: GET /object_info, POST /prompt, GET /history, WebSocket progress |
| **Schema Cache** | `schema.py` | Fetch, store, version, and query node_schema.json; provide node lookup by class_type |
| **Workflow Store** | `store.py` | Read/write workflow JSON files; manage current/drafts/templates |
| **Graph Ops Engine** | `graph_ops.py` | Apply structured ops (add/connect/set/delete) to workflow dict; validate against schema |
| **Workflow Planner** | `planner.py` | Map high-level requests to concrete Graph Ops sequences using schema-aware templates |
| **Installer** | `installer.py` | Git clone custom_nodes, pip install deps, place models, verify via schema re-fetch |
| **Runner** | `runner.py` | Queue workflow, track progress via WS, collect outputs, write to out/ |
| **Error Interpreter** | `healer.py` | Parse ComfyUI error responses, map to fix strategies, emit corrective Graph Ops |
| **CLI Router** | `cli.py` | argparse-based CLI entry point; dispatch to above components |

---

## SECTION 2 — Interfaces / Contracts

### A) Chat Commands

```
/comfy status                     — Check ComfyUI server status + loaded models
/comfy schema refresh             — Re-fetch /object_info, update node_schema.json
/comfy schema search <query>      — Search available nodes by keyword

/comfy install nodes <repo_url>   — Git clone a custom node pack into custom_nodes/
/comfy install check              — List node packs required for current workflow that are missing

/comfy build text2img --prompt "a cat on mars" --checkpoint "realvisxlV50_v50LightningBakedvae.safetensors"
/comfy build lora_scenes --lora "MySubject.safetensors" --prompt "photo of {subject}" --scenes "beach|arcade|subway" --count 12
/comfy build img2vid_persistence --ref "path/image.png" --seconds 2 --fps 12 --style "cinematic"

/comfy run current                — Submit current.json to ComfyUI, collect outputs
/comfy run <workflow_name>        — Submit named workflow

/comfy refine "make lighting moodier; keep face consistent"   — Apply refinement ops to current workflow
/comfy export current --name "my_project_v1"                  — Copy current workflow + outputs to named export

/comfy list workflows             — Show available templates and drafts
/comfy show current               — Print current workflow summary (nodes, connections)
/comfy logs last                  — Show last run log
```

### B) Graph Ops Format

Every workflow mutation is expressed as a list of ops. Machine-readable JSON.

```json
{
  "ops": [
    {
      "op": "add_node",
      "id": "3",
      "class_type": "KSampler",
      "inputs": {
        "seed": 42,
        "steps": 20,
        "cfg": 7.0,
        "sampler_name": "euler",
        "scheduler": "normal",
        "denoise": 1.0
      }
    },
    {
      "op": "connect",
      "from_id": "1",
      "from_output": 0,
      "to_id": "3",
      "to_input": "model"
    },
    {
      "op": "set_input",
      "id": "3",
      "key": "steps",
      "value": 30
    },
    {
      "op": "delete_node",
      "id": "99"
    },
    {
      "op": "replace_node",
      "id": "5",
      "class_type": "VAEDecodeTiled",
      "inputs": {
        "tile_size": 512
      }
    }
  ]
}
```

**Validation rules (enforced by graph_ops.py):**
- `class_type` must exist in node_schema.json.
- `inputs` keys must match the node's `input.required` or `input.optional` schema.
- `connect` must reference valid output index and valid input name.
- `from_id` and `to_id` must exist in the workflow after prior ops are applied.
- Ops are applied sequentially (order matters).

### C) File Layout

```
comfy_builder/
├── __main__.py              # Entry: python -m comfy_builder
├── cli.py                   # Argparse command router
├── api.py                   # ComfyUI HTTP/WS client
├── schema.py                # Schema cache + query
├── store.py                 # Workflow file management
├── graph_ops.py             # Graph operations engine
├── planner.py               # High-level request → Graph Ops
├── installer.py             # Custom node / model installer
├── runner.py                # Workflow execution + output collection
├── healer.py                # Error interpretation + auto-fix
├── config.py                # Configuration (paths, URLs, defaults)
├── utils.py                 # Shared utilities
├── requirements.txt         # Python deps for the builder itself
│
├── workflows/
│   ├── current.json         # Active workflow being edited
│   ├── drafts/              # Named drafts
│   └── templates/           # Reusable workflow skeletons
│       ├── text2img_sdxl.json
│       ├── lora_scenes_sdxl.json
│       └── img2vid_animatediff.json
│
├── schema/
│   ├── node_schema.json     # Cached /object_info response
│   └── schema_meta.json     # Version hash, timestamp
│
├── installs/
│   ├── allowlist.json       # Approved repos/packs
│   ├── node_packs.json      # Record of what's installed + source
│   └── install.log          # Timestamped install actions
│
├── logs/
│   └── runs/                # Per-run JSON reports
│       └── 20260207_143022.json
│
├── out/
│   ├── images/              # Generated images
│   ├── video/               # Generated videos
│   └── metadata.jsonl       # Append-only run metadata
│
└── tests/
    ├── test_graph_ops.py
    ├── test_schema.py
    ├── test_planner.py
    └── golden_workflows/    # Reference workflow JSONs for regression
```

### D) CLI Commands (Primary Interface)

```bash
# Core
python -m comfy_builder status
python -m comfy_builder schema refresh
python -m comfy_builder schema search "sampler"

# Install
python -m comfy_builder install nodes https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
python -m comfy_builder install check

# Build
python -m comfy_builder build text2img --prompt "a cat on mars" --steps 20
python -m comfy_builder build lora_scenes --lora MySubject.safetensors --scenes "beach|arcade|subway" --count 12
python -m comfy_builder build img2vid --ref ./ref.png --seconds 2 --fps 12

# Run
python -m comfy_builder run current
python -m comfy_builder run --workflow drafts/my_draft.json

# Refine
python -m comfy_builder refine --instruction "increase steps to 30, add hires fix"

# Export
python -m comfy_builder export current --name project_v1

# Inspect
python -m comfy_builder show current
python -m comfy_builder logs last
python -m comfy_builder list workflows
```

All commands print JSON to stdout (machine-parseable by Cursor agent) and human-readable summaries to stderr.

---

## SECTION 3 — Installer / Setup Plan

### 3.1 Missing Node Discovery

When the planner builds a workflow, it references `class_type` values. Before emitting final Graph Ops:

1. Load `schema/node_schema.json`.
2. For each `class_type` in the planned ops, check if it exists in the schema.
3. Missing nodes → collect into a `missing_nodes` list.
4. Look up `installs/allowlist.json` for known pack → class_type mappings.
5. If found in allowlist: propose install. If not: report unknown node, ask user for repo URL.

### 3.2 Allowlist

`installs/allowlist.json`:
```json
{
  "packs": {
    "ComfyUI-AnimateDiff-Evolved": {
      "repo": "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved",
      "provides": ["ADE_AnimateDiffLoaderWithContext", "ADE_AnimateDiffSamplingSettings", "ADE_UseEvolvedSampling"],
      "requires_models": ["animatediff_models/v3_sd15_mm.ckpt"]
    },
    "ComfyUI-VideoHelperSuite": {
      "repo": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite",
      "provides": ["VHS_VideoCombine", "VHS_LoadVideo", "VHS_LoadImages"]
    },
    "ComfyUI_IPAdapter_plus": {
      "repo": "https://github.com/cubiq/ComfyUI_IPAdapter_plus",
      "provides": ["IPAdapterModelLoader", "IPAdapterApply", "IPAdapterAdvanced"],
      "note": "Already installed"
    },
    "ComfyUI-Manager": {
      "repo": "https://github.com/ltdrdata/ComfyUI-Manager",
      "provides": ["ManagerMetaNode"],
      "note": "Already installed"
    }
  }
}
```

Users can add entries. The builder never installs from URLs not in allowlist without explicit `--force-allow` flag + user confirmation.

### 3.3 Installation Steps

```
install_node_pack(pack_name_or_url):
  1. Resolve pack to repo URL (from allowlist or direct URL with --force-allow).
  2. Validate URL is a GitHub/GitLab HTTPS URL (no arbitrary URLs).
  3. Log intent to installs/install.log.
  4. git clone <repo_url> into COMFYUI_PATH/custom_nodes/<pack_name>/
  5. If custom_nodes/<pack_name>/requirements.txt exists:
     - Detect ComfyUI's Python environment:
       a. Check for COMFYUI_PATH/python_embeded/python.exe (portable install)
       b. Fall back to system Python with the correct venv if applicable
     - Run: <python> -m pip install -r requirements.txt
  6. Log result to install.log.
  7. Prompt user: "Restart ComfyUI server for new nodes to load" OR
     call ComfyUI-Manager's restart endpoint if available.
  8. After restart: run `schema refresh` to re-fetch /object_info.
  9. Verify: check that expected class_types from allowlist now appear in schema.
  10. Update installs/node_packs.json with pack name, repo, date, classes added.
```

### 3.4 Model Placement

Model directories under `C:\Users\Admin\Documents\ComfyUI\models\`:

| Type | Directory | Example Files |
|---|---|---|
| Checkpoints | `checkpoints/` | `sd_xl_base_1.0.safetensors` |
| LoRAs | `loras/` | `MySubject.safetensors` |
| VAE | `vae/` | `sdxl_vae.safetensors` |
| ControlNet | `controlnet/` | `control_v11p_sd15_openpose.pth` |
| IPAdapter | `ipadapter/` | `ip-adapter-plus_sdxl_vit-h.safetensors` |
| CLIP Vision | `clip_vision/` | `CLIP-ViT-H-14.safetensors` |
| AnimateDiff | `animatediff_models/` | `v3_sd15_mm.ckpt` |

**When a model is missing:**
1. Builder detects missing file by checking the expected path.
2. If model is freely downloadable (e.g., from HuggingFace with open license): offer auto-download with `wget`/`curl` + progress bar.
3. If model requires manual download (license-gated):
   ```
   ⚠ MANUAL DOWNLOAD REQUIRED
   Model: ip-adapter-plus_sdxl_vit-h.safetensors
   Source: https://huggingface.co/h94/IP-Adapter
   Place at: C:\Users\Admin\Documents\ComfyUI\models\ipadapter\ip-adapter-plus_sdxl_vit-h.safetensors

   Run `/comfy status` after placing the file to continue.
   ```
4. Builder polls for file existence before proceeding with workflow.

---

## SECTION 4 — Workflow Strategies

### Goal 1: LoRA Scenes (Subject Persistence)

#### Strategy 1A: LoRA + Prompt Scenes (SDXL)

**Node spine:**
```
CheckpointLoaderSimple (ckpt: sd_xl_base_1.0.safetensors)
  → LoraLoader (lora: MySubject.safetensors, strength_model: 0.8, strength_clip: 0.8)
    → CLIPTextEncode (positive: "photo of <subject> at a beach, golden hour, cinematic")
    → CLIPTextEncode (negative: "blurry, deformed, low quality, watermark")
      → KSampler (seed: variable, steps: 25, cfg: 7.0, sampler: euler, scheduler: normal)
        → VAEDecode
          → SaveImage (filename_prefix: "lora_scene_{scene}_{seed}")
```

**Parameterization for batch:**
- `scenes` list → each generates a separate positive prompt with scene injected.
- `count` per scene → different seeds.
- Optionally vary aspect ratio per scene (landscape for "beach", portrait for "mirror selfie").
- Negative prompt: fixed default, user-overridable.

**Implementation:**
1. Planner generates a base Graph Ops sequence for the spine.
2. For batch: planner emits N workflow copies (or uses ComfyUI batch if supported), each with a different `set_input` for seed and prompt.
3. Runner queues all, collects outputs, names them `{scene}_{index}_{seed}.png`.

#### Strategy 1B: LoRA + IPAdapter for Stronger Identity Lock

When LoRA alone isn't enough (or user provides a reference image instead of LoRA):

**Additional nodes inserted:**
```
LoraLoader output
  → IPAdapterModelLoader (ipadapter: "ip-adapter-plus_sdxl_vit-h.safetensors")
  → CLIPVisionLoader (clip_vision: "CLIP-ViT-H-14.safetensors")
  → IPAdapterApply (weight: 0.6, image: <reference_image>)
    → feeds into KSampler (model input)
```

**Required models (may need manual download):**
- `ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors`
- `clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`

**Strategy selection logic:**
- If user provides `--ref <image>` → use Strategy 1B.
- If user provides only `--lora <file>` → use Strategy 1A.
- If user provides both → combine (LoRA + IPAdapter together).

### Goal 2: Image-to-Video with Character Persistence

#### Strategy 2A (Preferred): AnimateDiff

**Required installs:**
- `ComfyUI-AnimateDiff-Evolved` (check allowlist)
- `ComfyUI-VideoHelperSuite` (for VHS_VideoCombine)
- Model: `animatediff_models/` needs a motion module (e.g., `v3_sd15_mm.ckpt` for SD1.5 or `mm_sdxl_v10_beta.ckpt` for SDXL)

**Node spine:**
```
CheckpointLoaderSimple (ckpt: sdxl or sd15 depending on motion module)
  → LoraLoader (optional: subject LoRA)
    → CLIPTextEncode (positive: "video of <subject> eating a burger, cinematic, smooth motion")
    → CLIPTextEncode (negative: "static, blurry, morphing face")
      → ADE_AnimateDiffLoaderWithContext (model: motion module, context: 16 frames)
        → KSampler (steps: 20, cfg: 7, denoise: 0.8)
          → VAEDecode
            → VHS_VideoCombine (fps: 12, format: "video/h264-mp4")
              → output: out/video/

+ IPAdapter branch (for character persistence from ref image):
  LoadImage (ref image)
    → IPAdapterApply → feeds model into KSampler
```

**Parameters:**
- `--seconds N` → frames = N * fps
- `--fps 12` → passed to VHS_VideoCombine
- `--ref image.png` → fed to IPAdapter for identity lock
- `--style "cinematic"` → appended to positive prompt

#### Strategy 2B (Fallback): Keyframes + Interpolation

If AnimateDiff nodes are unavailable or fail to install:

1. **Generate N keyframes** (e.g., 4–8) using img2img with progressive prompt changes:
   - Frame 1: "subject holding burger, about to bite"
   - Frame 2: "subject biting burger"
   - Frame 3: "subject chewing burger, satisfied"
   - Frame 4: "subject smiling after eating burger"
   Each uses same seed + LoRA/IPAdapter for consistency, with slight denoise variation.

2. **Frame interpolation:**
   - Check if FILM/RIFE interpolation node is available (e.g., `ComfyUI-Frame-Interpolation`).
   - If available: use as a ComfyUI node to interpolate between keyframes.
   - If not: use ffmpeg externally:
     ```bash
     ffmpeg -framerate 2 -i keyframe_%d.png -vf "minterpolate=fps=12:mi_mode=mci" -c:v libx264 output.mp4
     ```

3. **Assembly:**
   - Combine interpolated frames into MP4/GIF.
   - Save to `out/video/`.

**Persistence controls (both strategies):**
- Fixed seed across keyframes.
- Same LoRA applied to all frames.
- IPAdapter with same reference image for all frames.
- Consistent negative prompt.

**Logging for both goals:**
- Each run logs: workflow JSON used, parameters, node versions, output paths, timing, errors.
- Saved to `logs/runs/<timestamp>.json`.

---

## SECTION 5 — MVP Milestones

### Milestone 0: Connectivity + Schema Cache
**Build:** `api.py`, `schema.py`, `config.py`, `cli.py` (status + schema commands)
**Acceptance criteria:**
- [x] `python -m comfy_builder status` returns server status, system stats, loaded checkpoints.
- [x] `python -m comfy_builder schema refresh` fetches /object_info, saves to `schema/node_schema.json`.
- [x] `schema/schema_meta.json` contains hash + timestamp.
- [x] `python -m comfy_builder schema search "KSampler"` returns matching node info.

### Milestone 1: "Hello World" Build + Run
**Build:** `graph_ops.py`, `store.py`, `runner.py`, `planner.py` (text2img template)
**Acceptance criteria:**
- [x] `python -m comfy_builder build text2img --prompt "a cat on mars"` creates `workflows/current.json`.
- [x] `python -m comfy_builder run current` submits to ComfyUI, waits for completion.
- [x] Output image saved to `out/images/` with meaningful filename.
- [x] Run log saved to `logs/runs/<timestamp>.json` with prompt_id, duration, output paths.

### Milestone 2: LoRA Scenes Builder
**Build:** `planner.py` (lora_scenes template), batch execution in `runner.py`
**Acceptance criteria:**
- [x] `python -m comfy_builder build lora_scenes --lora X --scenes "beach|arcade" --count 4` generates 8 images.
- [x] Each image uses the LoRA and the correct scene prompt.
- [x] Filenames follow `{scene}_{index}_{seed}.png` pattern.
- [x] Subject consistency verified visually (manual check).

### Milestone 3: Image-to-Video Persistence
**Build:** `planner.py` (img2vid template), video output in `runner.py`
**Acceptance criteria:**
- [x] `python -m comfy_builder build img2vid --ref ./face.png --seconds 2` produces MP4.
- [x] Strategy 2A (AnimateDiff) attempted first; falls back to 2B if nodes missing.
- [x] Output video saved to `out/video/`.
- [x] Character in video matches reference image.

### Milestone 4: Install Automation
**Build:** `installer.py`, allowlist management
**Acceptance criteria:**
- [x] `python -m comfy_builder install check` reports missing nodes for current workflow.
- [x] `python -m comfy_builder install nodes <repo>` clones, installs deps, logs actions.
- [x] After restart + schema refresh, new nodes appear in schema.
- [x] `installs/node_packs.json` updated with install record.

---

## SECTION 6 — Error Handling + Self-Healing

### Error → Fix Playbook

| Error Pattern | Detection | Auto-Fix |
|---|---|---|
| `"class_type" not found: XYZ` | ComfyUI validation error JSON | Look up XYZ in allowlist → propose install; or suggest alternative node from schema |
| `"file not found: models/loras/X.safetensors"` | ComfyUI error or pre-run check | Report expected path, ask user to place file |
| `"Invalid input key 'foo' for node 'Bar'"` | Validation error | Re-query schema for Bar's inputs; emit corrective `set_input` op |
| `"Output type mismatch: expected MODEL got CLIP"` | Connection error | Re-check schema output types; emit corrective `connect` op |
| `CUDA out of memory` | stderr / error response | Reduce resolution (set width/height to 75%); reduce batch to 1; enable tiled VAE decode; retry |
| `"Prompt execution interrupted"` | History shows failed status | Check which node failed; if OOM → apply OOM fix; if node error → re-check inputs |
| `Connection refused (server down)` | HTTP connection error | Report "ComfyUI server not running"; provide start command |
| `Timeout waiting for result` | WS/polling timeout | Report current queue position; offer to continue waiting or cancel |

### Self-Heal Loop

```
MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    result = runner.run(workflow)
    if result.success:
        return result

    fix = healer.diagnose(result.error)
    if fix.type == "graph_op":
        graph_ops.apply(workflow, fix.ops)
    elif fix.type == "install_required":
        report_to_user(fix.install_instructions)
        return BLOCKED  # stop, wait for user
    elif fix.type == "model_missing":
        report_to_user(fix.download_instructions)
        return BLOCKED
    elif fix.type == "reduce_resources":
        graph_ops.apply(workflow, fix.ops)  # lower resolution etc.
    else:
        report_to_user(f"Unknown error after {attempt+1} attempts: {result.error}")
        return FAILED

report_to_user(f"Failed after {MAX_RETRIES} attempts. Last error: ...")
return FAILED
```

**Stop conditions:**
- 3 consecutive failures on the same workflow.
- Missing asset that requires user action (model file, LoRA, reference image).
- Server unreachable after 3 connection attempts.

---

## SECTION 7 — Testing Plan

### Unit Tests (`tests/`)

| Test File | What It Tests |
|---|---|
| `test_graph_ops.py` | add_node, connect, set_input, delete_node ops; validation rejects bad class_type; validation rejects bad input keys; ops apply in order |
| `test_schema.py` | Schema loading; node lookup; search; hash comparison for drift detection |
| `test_planner.py` | text2img plan produces valid ops; lora_scenes plan produces N batched ops; img2vid plan selects correct strategy |
| `test_store.py` | Save/load workflow; draft management; template listing |
| `test_healer.py` | Each error pattern maps to correct fix type |

### Integration Tests

| Test | Requires |
|---|---|
| `test_connectivity` | ComfyUI running; fetches /object_info successfully |
| `test_text2img_e2e` | Runs minimal text2img; verifies image output exists |
| `test_schema_drift` | Install a node pack; verify schema changes detected |

### Golden Workflows

Store reference workflow JSONs in `tests/golden_workflows/`:
- `text2img_sdxl_minimal.json`
- `lora_scenes_sdxl.json`
- `img2vid_animatediff.json`

Used for regression: run planner, compare output ops against golden result.

---

## SECTION 8 — Cursor Agent Orchestration

### Operating Procedure

**Step 1: Parse Chat Command**
When user types `/comfy <subcommand> [args]`, the Cursor agent:
1. Strips the `/comfy` prefix.
2. Constructs the CLI invocation: `python -m comfy_builder <subcommand> [args]`.
3. Executes via terminal.

**Step 2: Execute Builder CLI**
```bash
cd D:\AI-Workstation\Projects\campaign-console-live
python -m comfy_builder <subcommand> [args] 2>comfy_builder/logs/stderr.log
```
- stdout: JSON result (machine-readable).
- stderr: Human-readable progress/status messages.

**Step 3: Present Results**
Parse JSON stdout:
```json
{
  "status": "success",
  "action": "run",
  "outputs": ["out/images/cat_mars_42.png"],
  "duration_s": 12.3,
  "log": "logs/runs/20260207_143022.json"
}
```
Present to user:
```
✓ Generated 1 image in 12.3s
  → out/images/cat_mars_42.png
  Run log: logs/runs/20260207_143022.json
```

**Step 4: Handle Installs**
When builder returns `"status": "blocked", "reason": "missing_nodes"`:
1. Show user the missing nodes and proposed install sources.
2. Ask for confirmation: "Install ComfyUI-AnimateDiff-Evolved from github.com/Kosinkadink/...? (y/n)"
3. On confirm: run `python -m comfy_builder install nodes <url>`.
4. After install: remind user to restart ComfyUI.
5. Run `python -m comfy_builder schema refresh` to verify.

**Step 5: Handle Model Requests**
When builder returns `"status": "blocked", "reason": "missing_model"`:
1. Show user exact download instructions.
2. Provide target path.
3. Wait for user confirmation that file is placed.
4. Re-run the original command.

**Step 6: Iterate on Errors**
When builder returns `"status": "failed"`:
1. Show error summary.
2. If auto-fix was attempted, show what was tried.
3. Offer: "Would you like me to try a different approach?" or present specific options.

### Command Routing Table

| User Says | Cursor Agent Does |
|---|---|
| `/comfy status` | `python -m comfy_builder status` |
| `/comfy build text2img --prompt "X"` | `python -m comfy_builder build text2img --prompt "X"` → then auto-run if `--auto-run` |
| `/comfy run current` | `python -m comfy_builder run current` → show outputs |
| `/comfy refine "more contrast"` | `python -m comfy_builder refine --instruction "more contrast"` → show diff → auto-run |
| "make me a video of X eating a burger" | Cursor agent translates to: `python -m comfy_builder build img2vid --prompt "X eating a burger" --ref <ask for ref> --seconds 2` |

---

## SECTION 9 — Security + Safety

### Path Sanitization
- All file operations restricted to:
  - `comfy_builder/` (builder's own directory)
  - `COMFYUI_PATH/custom_nodes/` (for installs)
  - `COMFYUI_PATH/models/` (for model placement)
- Path traversal (`..`) blocked in all user-provided paths.
- Resolved paths validated to be under allowed roots before any I/O.

### Command Execution
- Only predefined subcommands are callable.
- `installer.py` only runs: `git clone`, `pip install -r requirements.txt`.
- No arbitrary shell execution from user input.
- All subprocess calls use explicit argument lists (no `shell=True`).

### Rate Limits
- Max 5 concurrent prompt submissions (ComfyUI queue depth check).
- Max 100 images per batch run (prevent runaway generation).
- Timeout: 300s per workflow execution (configurable).

### Logging
- Every CLI invocation logged with timestamp, command, args, result status.
- Install actions logged with full command, source URL, outcome.
- Run results logged with prompt_id, workflow hash, outputs, errors.
- Logs stored in `comfy_builder/logs/` with rotation (keep last 100 run logs).

### Secrets
- No API keys stored (ComfyUI is local).
- If extended to remote ComfyUI, use environment variables only.
- `.gitignore` excludes `out/`, `schema/node_schema.json` (large), `logs/`.

---

## SECTION 10 — Concrete Examples

### Example 1: Graph Ops JSON — Minimal Text2Img Workflow

```json
{
  "ops": [
    {
      "op": "add_node",
      "id": "1",
      "class_type": "CheckpointLoaderSimple",
      "inputs": {
        "ckpt_name": "realvisxlV50_v50LightningBakedvae.safetensors"
      }
    },
    {
      "op": "add_node",
      "id": "2",
      "class_type": "CLIPTextEncode",
      "inputs": {
        "text": "a cat sitting on the surface of Mars, photorealistic, 8k"
      }
    },
    {
      "op": "add_node",
      "id": "3",
      "class_type": "CLIPTextEncode",
      "inputs": {
        "text": "blurry, deformed, ugly, watermark, text"
      }
    },
    {
      "op": "add_node",
      "id": "4",
      "class_type": "EmptyLatentImage",
      "inputs": {
        "width": 1024,
        "height": 1024,
        "batch_size": 1
      }
    },
    {
      "op": "add_node",
      "id": "5",
      "class_type": "KSampler",
      "inputs": {
        "seed": 42,
        "steps": 20,
        "cfg": 7.0,
        "sampler_name": "euler",
        "scheduler": "normal",
        "denoise": 1.0
      }
    },
    {
      "op": "add_node",
      "id": "6",
      "class_type": "VAEDecode",
      "inputs": {}
    },
    {
      "op": "add_node",
      "id": "7",
      "class_type": "SaveImage",
      "inputs": {
        "filename_prefix": "comfy_builder/cat_mars"
      }
    },
    {
      "op": "connect",
      "from_id": "1", "from_output": 0,
      "to_id": "5", "to_input": "model"
    },
    {
      "op": "connect",
      "from_id": "1", "from_output": 1,
      "to_id": "2", "to_input": "clip"
    },
    {
      "op": "connect",
      "from_id": "1", "from_output": 1,
      "to_id": "3", "to_input": "clip"
    },
    {
      "op": "connect",
      "from_id": "2", "from_output": 0,
      "to_id": "5", "to_input": "positive"
    },
    {
      "op": "connect",
      "from_id": "3", "from_output": 0,
      "to_id": "5", "to_input": "negative"
    },
    {
      "op": "connect",
      "from_id": "4", "from_output": 0,
      "to_id": "5", "to_input": "latent_image"
    },
    {
      "op": "connect",
      "from_id": "1", "from_output": 2,
      "to_id": "6", "to_input": "vae"
    },
    {
      "op": "connect",
      "from_id": "5", "from_output": 0,
      "to_id": "6", "to_input": "samples"
    },
    {
      "op": "connect",
      "from_id": "6", "from_output": 0,
      "to_id": "7", "to_input": "images"
    }
  ]
}
```

### Example 2: LoRA Scenes Command + Parameters

**Command:**
```bash
python -m comfy_builder build lora_scenes \
  --lora "BurgerGuy_v1.safetensors" \
  --prompt "photo of BurgerGuy, {scene}, professional photography, 8k" \
  --negative "blurry, deformed, cartoon, watermark" \
  --scenes "eating at a beach restaurant|cooking in a modern kitchen|at a food truck in NYC" \
  --count 4 \
  --checkpoint "realvisxlV50_v50LightningBakedvae.safetensors" \
  --lora-strength 0.85 \
  --steps 25 \
  --cfg 7.0 \
  --size 1024x1024
```

**Internal parameters produced:**
```json
{
  "template": "lora_scenes_sdxl",
  "checkpoint": "realvisxlV50_v50LightningBakedvae.safetensors",
  "lora": "BurgerGuy_v1.safetensors",
  "lora_strength_model": 0.85,
  "lora_strength_clip": 0.85,
  "base_prompt": "photo of BurgerGuy, {scene}, professional photography, 8k",
  "negative_prompt": "blurry, deformed, cartoon, watermark",
  "scenes": [
    "eating at a beach restaurant",
    "cooking in a modern kitchen",
    "at a food truck in NYC"
  ],
  "count_per_scene": 4,
  "total_images": 12,
  "width": 1024,
  "height": 1024,
  "steps": 25,
  "cfg": 7.0,
  "sampler": "euler",
  "scheduler": "normal",
  "seeds": [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200],
  "output_pattern": "out/images/lora_scenes/{scene}_{index}_{seed}.png"
}
```

### Example 3: Img2Vid Persistence Command + Parameters

**Command:**
```bash
python -m comfy_builder build img2vid \
  --ref "D:\photos\burgerguy_face.png" \
  --prompt "BurgerGuy eating a giant burger, cinematic lighting, smooth motion" \
  --seconds 2 \
  --fps 12 \
  --style "cinematic" \
  --lora "BurgerGuy_v1.safetensors"
```

**Internal parameters produced:**
```json
{
  "template": "img2vid_animatediff",
  "strategy": "2A_animatediff",
  "fallback": "2B_keyframes",
  "checkpoint": "realvisxlV50_v50LightningBakedvae.safetensors",
  "lora": "BurgerGuy_v1.safetensors",
  "lora_strength": 0.8,
  "ref_image": "D:\\photos\\burgerguy_face.png",
  "positive_prompt": "BurgerGuy eating a giant burger, cinematic lighting, smooth motion, cinematic",
  "negative_prompt": "static, blurry, morphing face, deformed, low quality",
  "seconds": 2,
  "fps": 12,
  "total_frames": 24,
  "motion_module": "auto_detect",
  "ipadapter_weight": 0.6,
  "denoise": 0.8,
  "steps": 20,
  "cfg": 7.0,
  "output_path": "out/video/img2vid_{timestamp}.mp4",
  "required_nodes": ["ADE_AnimateDiffLoaderWithContext", "VHS_VideoCombine", "IPAdapterApply"],
  "required_models": ["animatediff_models/*", "ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors"]
}
```

### Example 4: Run Report Format

`logs/runs/20260207_143022.json`:
```json
{
  "run_id": "20260207_143022",
  "timestamp": "2026-02-07T14:30:22Z",
  "command": "build lora_scenes --lora BurgerGuy_v1.safetensors --scenes beach|kitchen --count 2",
  "workflow_hash": "a3f9b2c1...",
  "workflow_file": "workflows/current.json",
  "comfyui_prompt_id": "abc-123-def",
  "status": "success",
  "duration_s": 45.2,
  "attempts": 1,
  "parameters": {
    "checkpoint": "realvisxlV50_v50LightningBakedvae.safetensors",
    "lora": "BurgerGuy_v1.safetensors",
    "scenes": ["beach", "kitchen"],
    "count_per_scene": 2,
    "steps": 25
  },
  "outputs": [
    {
      "file": "out/images/lora_scenes/beach_0_100.png",
      "type": "image",
      "scene": "beach",
      "seed": 100
    },
    {
      "file": "out/images/lora_scenes/beach_1_200.png",
      "type": "image",
      "scene": "beach",
      "seed": 200
    },
    {
      "file": "out/images/lora_scenes/kitchen_0_300.png",
      "type": "image",
      "scene": "kitchen",
      "seed": 300
    },
    {
      "file": "out/images/lora_scenes/kitchen_1_400.png",
      "type": "image",
      "scene": "kitchen",
      "seed": 400
    }
  ],
  "errors": [],
  "self_heal_actions": [],
  "node_versions": {
    "CheckpointLoaderSimple": "core",
    "LoraLoader": "core",
    "KSampler": "core"
  }
}
```

---

## Next 10 Actions Cursor Agent Should Take

1. **Create the file structure:** Create all directories under `comfy_builder/` as specified in Section 2C (workflows/, schema/, installs/, logs/runs/, out/images/, out/video/, tests/golden_workflows/).

2. **Create `config.py`:** Define `COMFYUI_URL = "http://127.0.0.1:8188"`, `COMFYUI_PATH = r"C:\Users\Admin\Documents\ComfyUI"`, and all path constants. Make them overridable via environment variables.

3. **Create `api.py`:** Implement `get_object_info()`, `post_prompt(workflow)`, `get_history(prompt_id)`, and `ws_connect()` against the ComfyUI API. Use `requests` + `websocket-client`.

4. **Create `schema.py`:** Implement `refresh_schema()` (calls api, saves to `schema/node_schema.json` + `schema_meta.json`), `load_schema()`, `get_node(class_type)`, `search_nodes(query)`.

5. **Create `cli.py` + `__main__.py`:** Wire up argparse with subcommands: `status`, `schema refresh`, `schema search`. Test `python -m comfy_builder status` against running ComfyUI. **This is Milestone 0.**

6. **Create `graph_ops.py`:** Implement `apply_ops(workflow_dict, ops_list)` and `validate_workflow(workflow_dict, schema)`. Unit test with `test_graph_ops.py`.

7. **Create `store.py`:** Implement `save_current(workflow)`, `load_current()`, `list_templates()`, `save_draft(name, workflow)`.

8. **Create `planner.py` (text2img template):** Implement `plan_text2img(params) → ops_list` that generates the Graph Ops from Example 1. Wire to `build text2img` CLI command.

9. **Create `runner.py`:** Implement `run_workflow(workflow_path) → RunResult` that POSTs to ComfyUI, polls/WS for completion, downloads output images, writes run log. Wire to `run current` CLI command. **This completes Milestone 1.**

10. **Create `installs/allowlist.json`:** Populate with the known packs (AnimateDiff-Evolved, VideoHelperSuite, IPAdapter_plus, ComfyUI-Manager). Create `installer.py` with `check_missing(workflow, schema)` and `install_pack(pack_name)`. **This prepares Milestone 4 and unblocks Milestones 2–3.**
