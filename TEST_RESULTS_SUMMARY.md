# Test run summary

**Date:** 2026-02-08

## Unit tests
- **99 passed** (pytest, `-m "not live"`)
- 5 live tests deselected in this run

## CLI error-handling (from TEST_PLAN)
| ID | Scenario | Result |
|----|----------|--------|
| TC-ERR-2 | Unknown template | PASS — error + list of available templates |
| TC-SCENE-4 | Missing --lora for lora_scenes | PASS — clear error |
| TC-REF-7 | Refine with no current workflow | PASS — "No current workflow to refine" |
| TC-ERR-3 | Run nonexistent workflow | PASS — workflow not found |

## Server & live
| ID | Result |
|----|--------|
| TC-SRV-1 | status with ComfyUI running — PASS (online, models listed) |
| Live connectivity (pytest -m live) | 4 passed (status, object_info, queue, schema refresh) |

## Happy-path flows
| Flow | Result |
|------|--------|
| build text2img → show → run current → logs last | PASS — 1 image generated |
| build lora_scenes (2 scenes, same subject) → run current | PASS — 2 images (kitchen, forest) |
| refine "change prompt to a dog in a hat" | PASS — 1 op applied |

## How to re-run
- **Unit + CLI errors:** `.\run_tests.ps1`
- **Live (ComfyUI must be running):** `.\run_manual_tests.ps1` or `pytest -m live -v`
