# Run manual/live tests against the live ComfyUI server and window.
# Requires: ComfyUI application running (server + window) at COMFYUI_URL (default http://127.0.0.1:8000).
# Jobs submitted by tests will appear in the ComfyUI queue/window.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$url = if ($env:COMFYUI_URL) { $env:COMFYUI_URL } else { "http://127.0.0.1:8000" }

Write-Host ""
Write-Host "=== Manual / Live Test Run ===" -ForegroundColor Cyan
Write-Host "  ComfyUI server + window must be running at $url" -ForegroundColor Yellow
Write-Host "  Live tests will submit real workflows; you can watch the queue in ComfyUI." -ForegroundColor Yellow
Write-Host ""

# Load .env from project root if present
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim().Trim('"'), "Process")
        }
    }
    $url = if ($env:COMFYUI_URL) { $env:COMFYUI_URL } else { "http://127.0.0.1:8000" }
}

$venvPath = ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating venv at $venvPath..."
    python -m venv $venvPath
}
& "$venvPath\Scripts\Activate.ps1"

# Install deps if needed
$pipList = pip list 2>$null
if ($pipList -notmatch "pytest") {
    Write-Host "Installing dev dependencies..."
    pip install -r requirements-dev.txt -q
}

# 1. Quick connectivity check before pytest
Write-Host "Checking ComfyUI server at $url..." -ForegroundColor Cyan
$statusJson = python -m comfy_builder status 2>&1 | Out-String
if ($statusJson -notmatch '"online":\s*true') {
    Write-Host "ERROR: ComfyUI server not reachable. Start ComfyUI (server + window) and run this script again." -ForegroundColor Red
    exit 1
}
Write-Host "Server OK. Running all live pytest tests (including E2E text2img on live server)..." -ForegroundColor Green
Write-Host ""

# 2. Run ALL live tests (no -k filter): connectivity, object_info, queue, text2img E2E, schema refresh
python -m pytest comfy_builder/tests/test_live.py -m live -v --tb=short
$pytestExit = $LASTEXITCODE

if ($pytestExit -eq 0) {
    Write-Host ""
    Write-Host "All live tests passed. Optional: run .\run_manual_cli_flow.ps1 to run a manual CLI flow while watching the ComfyUI window." -ForegroundColor Green
}
exit $pytestExit
