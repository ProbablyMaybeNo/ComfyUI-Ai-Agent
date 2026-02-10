# Manual CLI flow — run builder commands live while watching the ComfyUI window.
# Requires: ComfyUI server + window running (same as run_manual_tests.ps1).
# Use this to verify the full path: build -> queue -> run -> logs, with the job visible in ComfyUI.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim().Trim('"'), "Process")
        }
    }
}

$url = if ($env:COMFYUI_URL) { $env:COMFYUI_URL } else { "http://127.0.0.1:8000" }

Write-Host ""
Write-Host "=== Manual CLI flow (live ComfyUI server + window) ===" -ForegroundColor Cyan
Write-Host "  Ensure ComfyUI is open and you can see the queue. Commands will submit real work." -ForegroundColor Yellow
Write-Host ""

# 1. Status
Write-Host "[1/4] status" -ForegroundColor Cyan
python -m comfy_builder status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Server not reachable. Start ComfyUI and run again." -ForegroundColor Red
    exit 1
}
Write-Host ""

# 2. Build text2img (fast params)
Write-Host "[2/4] build text2img (fast: 4 steps)" -ForegroundColor Cyan
python -m comfy_builder build text2img --prompt "a coffee mug on a desk, manual test" --steps 4 --cfg 1.0 2>&1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ""

# 3. Run current (job will appear in ComfyUI window)
Write-Host "[3/4] run current (watch the ComfyUI window for the queued job)" -ForegroundColor Cyan
python -m comfy_builder run current 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Bring ComfyUI desktop window to front and move mouse / click so you see interaction
Write-Host "Bringing ComfyUI window to front and moving mouse..." -ForegroundColor Cyan
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m comfy_builder focus-ui 2>&1 | Out-Host
Write-Host ""

# 4. Logs
Write-Host "[4/4] logs last" -ForegroundColor Cyan
python -m comfy_builder logs last 2>&1

Write-Host ""
Write-Host "Manual CLI flow finished. Check ComfyUI output folder or comfy_builder/out/images/ for the image." -ForegroundColor Green
exit 0
