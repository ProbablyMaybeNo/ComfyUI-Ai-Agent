# ComfyUI Agent — Test Plan

This document defines a thorough test plan for the ComfyUI Agent project, with emphasis on:

1. **Chat-to-workflow flow** — User conversations (or agent-interpreted commands) that create and run ComfyUI workflows.
2. **Same subject, variety of scenes** — Workflows that keep one subject/character/style across multiple scenes.
3. **Image-to-animation with same subject** — Turning images into animations with the same subject in different situations.

---

## 1. Test Scope and Layers

| Layer | Scope | ComfyUI server | Chat/agent |
|-------|--------|-----------------|------------|
| **Unit** | Planner, graph ops, schema, store, healer | No (mocked) | No |
| **Integration (CLI)** | Full build → run → logs via CLI | Optional (live tests) | No |
| **Chat / agent** | User utterance → CLI invocation → result | Yes | Yes (Cursor/agent) |
| **E2E (manual)** | Same-subject scenes, img2vid, refine | Yes | Optional |

---

## 2. Chat Conversation → Workflow Mapping

The agent (e.g. Cursor) interprets user chat and runs `python -m comfy_builder <command> [args]`. Tests in this section validate that **intent** maps correctly to **CLI calls** and **workflow outcomes**.

### 2.1 Intent → Command Matrix

| User intent (example) | Expected CLI sequence | Template / flow |
|------------------------|------------------------|-----------------|
| "Generate a dragon in a library" | `build text2img --prompt "a dragon in a library"` → `run current` | text2img |
| "Make 3 images of a cat in different places" | `build lora_scenes --lora <style> --scenes "kitchen\|forest\|space" --count 1` → `run current` | lora_scenes |
| "Same character in 5 scenes" (with LoRA) | `build lora_scenes --lora <lora> --prompt "photo of subject, {scene}, 8k" --scenes "A\|B\|C\|D\|E"` → `run current` | lora_scenes batch |
| "Turn my character into a short video" | `build img2vid --prompt "character in motion" --ref <path> --seconds 2` → `run current` | img2vid |
| "Animate this image in 3 different situations" | Build img2vid 3× with different prompts (or future multi-situation API) | img2vid (multi-run or batch) |
| "Use more steps" | `refine "set steps to 30"` → optional `run current` | refine |
| "Change the prompt to X" | `refine "change prompt to X"` | refine |
| "Is ComfyUI running?" | `status` | status |
| "What did I just generate?" | `logs last` | logs |

**Test cases (manual or automated where possible):**

- **TC-CHAT-1** For each row above, document the exact user phrase and the exact CLI command(s) the agent should run. Run the command and assert JSON `status` is success (or expected error).
- **TC-CHAT-2** Ambiguous intent: user says "make me a video" without subject/ref — agent should ask for clarification or use defaults; no crash.
- **TC-CHAT-3** Refine without current workflow: user says "set steps to 30" before any build — expect clear error from `refine` (no current workflow).

---

## 3. Same Subject, Variety of Scenes

### 3.1 LoRA Scenes (built-in template)

**Flow:** One LoRA (style/character), prompt template with `{scene}`, pipe-separated scene list. Runner batches N jobs (scene × count).

**Test cases:**

| ID | Scenario | Steps | Pass criteria |
|----|----------|--------|----------------|
| **TC-SCENE-1** | Minimal: 1 LoRA, 2 scenes, 1 image each | `build lora_scenes --lora pixar_style_sdxl.safetensors --scenes "kitchen\|forest" --count 1` → `run current` | status success; 2 outputs; each image reflects scene in prompt. |
| **TC-SCENE-2** | Same subject phrase in prompt | Use `--prompt "a red fox, {scene}, pixar style"` with 3 scenes | All 3 images share "red fox" and "pixar style"; only scene changes. |
| **TC-SCENE-3** | Batch size limit | `--scenes "a\|b\|c\|..."` so total (scenes × count) > MAX_BATCH_SIZE (100) | Build fails with clear error. |
| **TC-SCENE-4** | Missing --lora | `build lora_scenes --scenes "a\|b"` | Build fails with "lora is required". |
| **TC-SCENE-5** | Golden workflow regression | Build lora_scenes with fixed params; compare output ops (or workflow JSON) to `tests/golden_workflows/lora_scenes_sdxl.json` (structure/key nodes). | No regression in node set and connections. |

### 3.2 Run-scenes (scenes.txt + existing workflow)

**Flow:** `run-scenes <workflow_name>` reads `workflows/scenes.txt`, uses a fixed character/subject description, and runs the workflow once per scene (patch prompt + filename per line).

**Note:** `run_scenes` is implemented in code but may not be registered in the CLI parser; if so, add a subparser and route, then test.

**Test cases:**

| ID | Scenario | Steps | Pass criteria |
|----|----------|--------|----------------|
| **TC-RUNSCENES-1** | run-scenes with valid workflow and scenes.txt | Ensure `workflows/scenes.txt` has 2–3 lines; run `run-scenes huffle_scenes_main` (or equivalent) | status success or partial; one output per scene. |
| **TC-RUNSCENES-2** | run-scenes with missing workflow | `run-scenes nonexistent` | Clear error: workflow not found. |
| **TC-RUNSCENES-3** | run-scenes with empty scenes.txt | Empty or missing scenes.txt | Clear error: scenes.txt empty or not found. |
| **TC-RUNSCENES-4** | Same character across scenes | Use workflow with fixed character description; vary only scene text in scenes.txt | Outputs share same character; scenes differ. |

### 3.3 Chat-driven “same subject, many scenes”

**Test cases:**

| ID | Scenario | Steps | Pass criteria |
|----|----------|--------|----------------|
| **TC-CHAT-SCENE-1** | User: "I want my character in a cafe, on a train, and at the beach" | Agent maps to lora_scenes (or run-scenes) with those 3 scenes | 3 images generated; character consistent; scenes match. |
| **TC-CHAT-SCENE-2** | User: "Generate 10 variations of a robot in different environments" | Agent maps to lora_scenes with 10 scenes (or count × scenes = 10) | 10 images; theme "robot" + varying environment. |

---

## 4. Image-to-Animation (Same Subject, Different Situations)

### 4.1 img2vid template (single run)

**Flow:** `build img2vid` with optional `--ref`, `--prompt`, `--seconds`, `--fps`, `--style`, `--lora`. Strategy: AnimateDiff if nodes present, else keyframes fallback.

**Test cases:**

| ID | Scenario | Steps | Pass criteria |
|----|----------|--------|----------------|
| **TC-VID-1** | Basic img2vid (no ref) | `build img2vid --prompt "a cat walking" --seconds 1 --fps 8` → `run current` | Workflow builds; run completes; video or keyframe outputs. |
| **TC-VID-2** | img2vid with ref image | `build img2vid --prompt "same character waving" --ref <path>` | Build includes ref (when IPAdapter path implemented); or clear behavior when ref not wired. |
| **TC-VID-3** | img2vid with style | `build img2vid --prompt "person running" --style "cinematic, slow motion"` | Prompt in workflow includes style suffix. |
| **TC-VID-4** | AnimateDiff vs keyframes | With AnimateDiff nodes: strategy 2A; without: strategy 2B (keyframe images) | Correct strategy in meta; workflow has expected node types. |
| **TC-VID-5** | Same subject, different situation (multi-run) | Run 1: `img2vid --prompt "subject eating"`; Run 2: `img2vid --prompt "subject sleeping"` (same ref/seed if applicable) | Two separate videos; same subject implied by shared ref/params. |

### 4.2 Same subject in different situations (animations)

**Test cases:**

| ID | Scenario | Steps | Pass criteria |
|----|----------|--------|----------------|
| **TC-VID-SIT-1** | "Animate my character in 3 situations: waving, sitting, running" | Three builds/runs of img2vid with same ref, different prompts | 3 videos; subject consistent (to the degree ref/LoRA allows). |
| **TC-VID-SIT-2** | Chat: "Turn this image into a 2s video of them in a park, then in a kitchen" | Agent runs img2vid twice with different prompts (or future batch) | 2 videos; same source image/subject. |

---

## 5. Refine (Chat-Based Workflow Tweaks)

Refine parses natural-language instructions and applies graph ops (set_input) to the current workflow.

**Test cases:**

| ID | Instruction | Expected op(s) | Pass criteria |
|----|-------------|-----------------|----------------|
| **TC-REF-1** | "set steps to 30" | set_input KSampler steps = 30 | steps in workflow = 30. |
| **TC-REF-2** | "change cfg to 8.5" | set_input KSampler cfg = 8.5 | cfg = 8.5. |
| **TC-REF-3** | "set seed to 12345" | set_input KSampler seed = 12345 | seed = 12345. |
| **TC-REF-4** | "change prompt to a dog in a hat" | set_input first CLIPTextEncode text = "a dog in a hat" | Positive prompt updated. |
| **TC-REF-5** | "set width to 768" | set_input EmptyLatentImage width = 768 | width = 768. |
| **TC-REF-6** | Unparseable: "make it prettier" | No op or error | No crash; clear error or no-op. |
| **TC-REF-7** | Refine with no current workflow | Any refine | status error, "No current workflow to refine". |

(Unit tests for refine already exist in `test_planner.py`; these can be used as live/CLI checks: build → refine with instruction → show current → assert values.)

---

## 6. Server, Schema, and Install

### 6.1 Server and schema

| ID | Scenario | Pass criteria |
|----|----------|----------------|
| **TC-SRV-1** | `status` with ComfyUI running | online true; models listed. |
| **TC-SRV-2** | `status` with ComfyUI stopped | online false; hint to start server. |
| **TC-SRV-3** | `schema refresh` with server up | node_count ≥ 1; schema file written. |
| **TC-SRV-4** | `schema search "KSampler"` | KSampler in results. |

### 6.2 Install and missing nodes

| ID | Scenario | Pass criteria |
|----|----------|----------------|
| **TC-INST-1** | `install check` with current workflow using only core nodes | No missing nodes (or expected list). |
| **TC-INST-2** | Current workflow uses a custom node not installed | install check reports missing; status blocked or clear message. |

---

## 7. Error Handling and Boundaries

| ID | Scenario | Pass criteria |
|----|----------|----------------|
| **TC-ERR-1** | Run workflow when server is down | status error; hint to start ComfyUI. |
| **TC-ERR-2** | Build with unknown template | status error; message lists available templates. |
| **TC-ERR-3** | Run nonexistent workflow name | status error; workflow not found. |
| **TC-ERR-4** | Build lora_scenes without --lora | ValueError / status error. |
| **TC-ERR-5** | Refine with no current workflow | status error. |
| **TC-ERR-6** | Timeout on long run (e.g. AnimateDiff) | Run result status timeout or error after RUN_TIMEOUT_S. |

---

## 8. Test Data and Oracles

### 8.1 Scenes and prompts

- **Same-subject prompt template:** e.g. `"a red fox, {scene}, pixar style, 8k"`.
- **Scene lists:** Use small sets (2–3) for automation; 5–10 for manual “variety” checks.
- **scenes.txt:** Keep a test file with 3–5 lines (e.g. "kitchen", "forest", "space", "cafe", "beach") for run-scenes tests.

### 8.2 Reference images

- One reference image in ComfyUI `input/` (or path allowed by config) for img2vid/ref tests.
- Document path in .env or test config so agent/CLI can pass `--ref` consistently.

### 8.3 Golden workflows

- **text2img:** `tests/golden_workflows/text2img_sdxl.json`
- **lora_scenes:** `tests/golden_workflows/lora_scenes_sdxl.json`
- **img2vid:** `tests/golden_workflows/img2vid_animatediff.json`

Use for: structure regression (node types, connections), not pixel output.

---

## 9. Execution Summary

| Category | Test type | Where to run | ComfyUI required |
|----------|-----------|----------------|-------------------|
| Unit (planner, graph_ops, schema, store, healer) | pytest | `pytest -m "not live"` | No |
| Live (connectivity, text2img e2e, schema refresh) | pytest | `pytest -m live` | Yes |
| Chat → CLI mapping | Manual / script | Agent + CLI | Yes (for run) |
| Same subject / scenes (lora_scenes, run-scenes) | Manual + optional pytest | CLI or agent | Yes |
| Image-to-animation (img2vid, situations) | Manual + optional pytest | CLI or agent | Yes |
| Refine (NL instructions) | Unit + CLI | test_planner + `refine "..."` | No for unit |
| Errors and boundaries | Unit + CLI | pytest + manual | Partial |

### Recommended order for manual validation

1. **Status and schema:** status, schema refresh, schema search.
2. **Single image:** build text2img → run current → logs last.
3. **Same subject, multiple scenes:** build lora_scenes (2–3 scenes) → run current → verify outputs.
4. **Refine:** build text2img → refine "set steps to 30" → show current → run current.
5. **Image-to-video:** build img2vid (short duration) → run current → verify video/keyframes.
6. **Same subject, different situations (video):** run img2vid 2× with different prompts; compare subjects.
7. **run-scenes** (if CLI wired): run-scenes with scenes.txt and a workflow that uses a fixed subject.
8. **Error cases:** server down, unknown template, missing lora, refine with no workflow.

---

## 10. Chat Conversation Test Scripts (Suggested)

To automate “chat-like” flows without a real chat UI, use a script that runs CLI commands in sequence and asserts on JSON output:

```powershell
# Example: same subject, 3 scenes
python -m comfy_builder build lora_scenes --lora pixar_style_sdxl.safetensors `
  --prompt "a cute robot, {scene}, pixar style" `
  --scenes "in a kitchen|in a forest|on the moon" --count 1
# Parse JSON; assert status success
python -m comfy_builder run current
# Parse JSON; assert status success; assert outputs count >= 3
python -m comfy_builder logs last
# Assert output file paths exist
```

Similar scripts for: single text2img, refine then run, img2vid single run, img2vid two situations (two runs).

This test plan should be updated when new templates (e.g. IPAdapter-first “same subject” or batch img2vid) or new chat intents are added.
