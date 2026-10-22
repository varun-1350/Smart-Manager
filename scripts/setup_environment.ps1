# Smart Manager Environment Verification & Setup Script
$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "         Smart Manager Environment Setup & Check         " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan

# 1. Check Python
Write-Host "`n[1/5] Checking Python 3.12..." -ForegroundColor Yellow
$PythonVersion = & python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Found: $PythonVersion" -ForegroundColor Green
} else {
    Write-Host "  Python 3.12 is required but not found in PATH." -ForegroundColor Red
}

# 2. Check Node & npm
Write-Host "`n[2/5] Checking Node.js & npm..." -ForegroundColor Yellow
$NodeVersion = & node --version 2>&1
$NpmVersion = & npm --version 2>&1
Write-Host "  Node: $NodeVersion | npm: $NpmVersion" -ForegroundColor Green

# 3. Check Ollama & Model
Write-Host "`n[3/5] Checking Ollama daemon and local model..." -ForegroundColor Yellow
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
    $models = $res.models | ForEach-Object { $_.name }
    Write-Host "  Ollama status: Online" -ForegroundColor Green
    Write-Host "  Installed models: $($models -join ', ')" -ForegroundColor Green

    if ($models -contains "gemma4:e2b") {
        Write-Host "  Configured model 'gemma4:e2b' is ready." -ForegroundColor Green
    } else {
        Write-Host "  Warning: 'gemma4:e2b' is not present in Ollama. Run: ollama pull gemma4:e2b" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Ollama daemon is offline. Start it with: ollama serve" -ForegroundColor Red
}

# 4. Check / Setup Python Virtual Environment
Write-Host "`n[4/5] Checking Python Virtual Environment..." -ForegroundColor Yellow
$VenvPython = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "  Creating virtual environment at .venv..." -ForegroundColor Yellow
    & python -m venv "$ProjectRoot\.venv"
}
Write-Host "  Installing backend dependencies..." -ForegroundColor Yellow
& "$VenvPython" -m pip install -q -r "$ProjectRoot\backend\requirements.txt"
& "$VenvPython" -m pip install -q pyinstaller pywebview
Write-Host "  Virtual environment ready." -ForegroundColor Green

# 5. Check Frontend Build
Write-Host "`n[5/5] Checking Frontend Dependencies..." -ForegroundColor Yellow
Push-Location "$ProjectRoot\frontend"
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "  Installing frontend dependencies..." -ForegroundColor Yellow
        npm install
    }
    Write-Host "  Building production frontend..." -ForegroundColor Yellow
    npm run build
    Write-Host "  Frontend build ready at frontend/dist." -ForegroundColor Green
} finally {
    Pop-Location
}

Write-Host "`n=========================================================" -ForegroundColor Green
Write-Host "Setup complete! Launch Smart Manager with Launch-SmartManager.bat" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
