# ComfyUI Agent — run test suite (unit + CLI error cases).
# For live tests (requires ComfyUI): .\run_manual_tests.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== 1. Unit tests (no server) ===" -ForegroundColor Cyan
python -m pytest comfy_builder/tests/ -v -m "not live" --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n=== 2. CLI error-handling tests ===" -ForegroundColor Cyan
$errOk = 0
# Unknown template
$r = python -m comfy_builder build fake_template --prompt "x" 2>&1 | Out-String
if ($r -match '"status":\s*"error"' -and $r -match "Unknown template") { Write-Host "  TC-ERR-2 unknown template: PASS"; $errOk++ } else { Write-Host "  TC-ERR-2: FAIL"; exit 1 }
# Missing lora
$r = python -m comfy_builder build lora_scenes --scenes "a|b" 2>&1 | Out-String
if ($r -match '"status":\s*"error"' -and $r -match "lora") { Write-Host "  TC-SCENE-4 missing lora: PASS"; $errOk++ } else { Write-Host "  TC-SCENE-4: FAIL"; exit 1 }
# Run nonexistent
$r = python -m comfy_builder run nonexistent_workflow 2>&1 | Out-String
if ($r -match "not found") { Write-Host "  TC-ERR-3 run nonexistent: PASS"; $errOk++ } else { Write-Host "  TC-ERR-3: FAIL"; exit 1 }
# TC-REF-7 (refine with no workflow) covered by unit test test_refine_no_workflow; CLI exit code verified manually.

Write-Host "`nAll tests passed." -ForegroundColor Green
exit 0
