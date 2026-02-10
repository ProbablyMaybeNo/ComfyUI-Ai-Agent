# ComfyUI Agent — Test Report

**Date:** 2026-02-08  
**Scope:** Full test suite including ComfyUI Builder CLI, chat feature, installer, runner, and live tests.

---

## 1. Test Summary

| Category | Count | Result |
|----------|--------|--------|
| Unit tests (pytest, `-m "not live"`) | 159 | **All passed** |
| Live tests (connectivity + schema) | 4 | **All passed** |
| CLI error-handling (run_tests.ps1) | 3 | **All passed** |
| **Total** | **166** | **Pass** |

### Test areas covered

- **CLI:** Argument parsing, command routing, build-param extraction, `run-scenes`, exit codes
- **Planner:** text2img, lora_scenes, img2vid (AnimateDiff + keyframes), refine, unknown template
- **Graph ops:** add/connect/set_input/delete/replace, validation, workflow summary
- **Schema:** load, search, node exists, validate
- **Store:** save/load current, load workflow, drafts/templates, export, run logs
- **Runner:** missing workflow, server down, single run, batch, poll, collect outputs
- **Healer:** diagnose patterns, fix serialization, resolve placeholders, auto-heal
- **Installer:** allowlist, install pack (known/URL/force), check missing nodes, check model
- **Live:** server status, object_info, queue, schema refresh

---

## 2. Necessary Fixes Applied

**None required.** All tests passed. The following were already addressed in earlier work:

- **CLI exit codes:** `cmd_build` and `cmd_refine` return exit code 1 when result status is error (TC-ERR-2, TC-REF-7).
- **Error messages:** Unknown template, missing lora, workflow not found, and no current workflow to refine all return clear JSON errors.

---

## 3. Optional Optimizations

| Item | Recommendation |
|------|-----------------|
| **TC-REF-7 in run_tests.ps1** | Omitted: automating it requires renaming `workflows/current.json`, which can hit Windows path/device issues in PowerShell. TC-REF-7 is covered by unit test `test_refine_no_workflow` and by manual CLI check (refine returns exit 1). |
| **NUL file** | Remove or ignore `comfy_builder/NUL` and project root `nul` (Windows reserved name). Added to `.gitignore`; delete manually if present: `del \\.\d:\...\comfy_builder\NUL` if needed. |
| **Chat module tests** | `comfy_builder/chat` (Ollama + HTTP server + tools) has no pytest yet. Optional: add `test_chat.py` for tools/CLI wiring or smoke test server. |
| **run_tests.ps1 live note** | Script already states “For live tests: run_manual_tests.ps1”. No change needed. |

---

## 4. Changes Made This Run

1. **.gitignore** — Created for standalone repo: `.env`, `out/`, `logs/`, `.venv`, `__pycache__`, `.pytest_cache`, `*.pyc`, `nul`, `NUL`, optional schema cache.
2. **TEST_REPORT.md** — This file.
3. **GITHUB_PUSH.md** — Steps to create a new GitHub repo and push ComfyUI Agent.
4. **README.md** — Project overview and quick start for the repo.

---

## 5. How to Re-run

```powershell
# Unit + CLI error tests (no ComfyUI required)
.\run_tests.ps1

# Live tests (ComfyUI must be running at COMFYUI_URL)
.\run_manual_tests.ps1
# or: pytest -m live -v
```

---

## 6. References

- **TEST_PLAN.md** — Full test plan (chat→workflow, same-subject scenes, img2vid, refine, errors).
- **comfy_builder/tests/README_LIVE_TESTS.md** — How to run and interpret live tests.
