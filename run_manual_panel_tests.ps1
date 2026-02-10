# Run manual/live tests for the ComfyUI Agent Panel (chat UI).
# Requires: Panel server running at http://127.0.0.1:8085 (start with: python -m comfy_builder chat)
# Optional: Ollama running for /api/chat tests; ComfyUI for full workflow run.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$panelUrl = "http://127.0.0.1:8085"
Write-Host ""
Write-Host "=== ComfyUI Agent Panel — Manual / Live Tests ===" -ForegroundColor Cyan
Write-Host "  Panel must be running at $panelUrl" -ForegroundColor Yellow
Write-Host "  Start it with: python -m comfy_builder chat" -ForegroundColor Yellow
Write-Host "  Ollama (and optionally ComfyUI) needed for chat-with-LLM tests." -ForegroundColor Yellow
Write-Host ""

# Check panel is reachable
try {
    $resp = Invoke-WebRequest -Uri "$panelUrl/api/status" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "Panel OK. Running unit tests (no live) first..." -ForegroundColor Green
} catch {
    Write-Host "Panel not reachable at $panelUrl. Start it with: python -m comfy_builder chat" -ForegroundColor Red
    exit 1
}

# 1. Unit tests (no live)
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m pytest comfy_builder/tests/test_chat_panel.py -v -m "not live" --tb=short 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Running live panel tests (GET /api/status, GET /, POST /api/chat)..." -ForegroundColor Cyan
& $py -m pytest comfy_builder/tests/test_chat_panel.py -m live -v --tb=short 2>&1 | Out-Host
$liveExit = $LASTEXITCODE

if ($liveExit -eq 0) {
    Write-Host ""
    Write-Host "All panel tests passed. Open $panelUrl in a browser to converse with the LLM and verify workflow generation." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Some live tests failed or were skipped (e.g. Ollama not running). Start Ollama and ComfyUI, then re-run." -ForegroundColor Yellow
}
exit $liveExit
