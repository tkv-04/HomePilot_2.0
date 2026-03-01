# ============================================================
# HomePilot Windows Setup Script
# ============================================================
# This script:
# 1. Creates a Python virtual environment
# 2. Installs Python packages
# 3. Downloads the Vosk STT model
# 4. Creates required directories
#
# Usage (run in PowerShell as Administrator):
#   .\deploy\install.ps1
# ============================================================

$ErrorActionPreference = "Stop"

$InstallDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $InstallDir) { $InstallDir = (Get-Location).Path }
$VenvDir = Join-Path $InstallDir "venv"
$ModelDir = Join-Path $InstallDir "models"
$DataDir = Join-Path $InstallDir "data"
$LogDir = Join-Path $InstallDir "logs"
$AssetDir = Join-Path $InstallDir "assets\sounds"
$PluginDir = Join-Path $InstallDir "plugins"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  HomePilot v2.0 - Windows Installation Script" -ForegroundColor Cyan
Write-Host "  Privacy-First Edge AI Voice Assistant" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# -- Step 1: Check Python --
Write-Host "[1/5] Checking Python installation..." -ForegroundColor Green
$pythonVersion = & python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Python 3.11+ is required. Install from https://python.org" -ForegroundColor Red
    exit 1
}
Write-Host "  Found: $pythonVersion" -ForegroundColor Gray

# -- Step 2: Create Virtual Environment --
Write-Host "[2/5] Creating Python virtual environment..." -ForegroundColor Green
if (-not (Test-Path $VenvDir)) {
    & python -m venv $VenvDir
}
$pipPath = Join-Path $VenvDir "Scripts\pip.exe"
$pythonPath = Join-Path $VenvDir "Scripts\python.exe"
& $pipPath install --upgrade pip setuptools wheel -q
Write-Host "  Virtual environment ready." -ForegroundColor Gray

# -- Step 3: Install Python Packages --
Write-Host "[3/5] Installing Python packages..." -ForegroundColor Green
$reqFile = Join-Path $InstallDir "requirements.txt"
& $pipPath install -r $reqFile -q
Write-Host "  Python packages installed." -ForegroundColor Gray

# -- Step 4: Download Vosk STT Model --
Write-Host "[4/5] Downloading AI models..." -ForegroundColor Green
if (-not (Test-Path $ModelDir)) { New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null }

$VoskModel = "vosk-model-small-en-us-0.15"
$VoskModelPath = Join-Path $ModelDir $VoskModel
if (-not (Test-Path $VoskModelPath)) {
    Write-Host "  Downloading Vosk STT model (~40MB)..." -ForegroundColor Yellow
    $zipUrl = "https://alphacephei.com/vosk/models/$VoskModel.zip"
    $zipPath = Join-Path $env:TEMP "$VoskModel.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $ModelDir -Force
    Remove-Item $zipPath -Force
    Write-Host "  Vosk model downloaded." -ForegroundColor Gray
} else {
    Write-Host "  Vosk model already present." -ForegroundColor Gray
}

Write-Host "  NOTE: Download a Piper TTS model manually:" -ForegroundColor Yellow
Write-Host "    https://github.com/rhasspy/piper/blob/master/VOICES.md" -ForegroundColor Yellow
Write-Host "    Recommended: en_US-lessac-medium" -ForegroundColor Yellow
Write-Host "    Place .onnx and .onnx.json files in $ModelDir\" -ForegroundColor Yellow

# -- Step 5: Create Directories --
Write-Host "[5/5] Creating directories..." -ForegroundColor Green
@($DataDir, $LogDir, $AssetDir, $PluginDir) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}
Write-Host "  Directories created." -ForegroundColor Gray

# -- Done --
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  HomePilot installation complete!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Edit config\default_config.yaml" -ForegroundColor White
Write-Host "     - Set your Picovoice access key" -ForegroundColor Gray
Write-Host "     - Configure Home Assistant (optional)" -ForegroundColor Gray
Write-Host "  2. Download a Piper TTS voice model" -ForegroundColor White
Write-Host "  3. Run the assistant:" -ForegroundColor White
Write-Host "     .\venv\Scripts\activate" -ForegroundColor Gray
Write-Host "     python run.py" -ForegroundColor Gray
Write-Host ""
