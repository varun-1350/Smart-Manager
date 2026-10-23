# Smart Manager Windows Packaging Script
param (
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "         Building Smart Manager Windows Distribution     " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan

# 1. Build frontend bundle
if (-not $SkipFrontendBuild) {
    Write-Host "[1/3] Building frontend production bundle..." -ForegroundColor Yellow
    Push-Location "$ProjectRoot\frontend"
    try {
        npm run build
    } finally {
        Pop-Location
    }
}

# 2. Package standalone executable via PyInstaller
Write-Host "[2/3] Bundling desktop application with PyInstaller..." -ForegroundColor Yellow
$PythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
$PyInstallerExe = "$ProjectRoot\.venv\Scripts\pyinstaller.exe"
$AppIcon = "$ProjectRoot\frontend\src\assets\logo.png"

if (-not (Test-Path $PyInstallerExe)) {
    throw "PyInstaller is not installed in .venv. Run: pip install pyinstaller"
}

if (-not (Test-Path $AppIcon)) {
    throw "Application icon was not found at: $AppIcon"
}

Push-Location $ProjectRoot
try {
    & $PyInstallerExe `
        --noconfirm `
        --onedir `
        --noconsole `
        --name "SmartManager" `
        --icon "$AppIcon" `
        --distpath "$ProjectRoot\dist" `
        --workpath "$ProjectRoot\build" `
        --add-data "backend;backend" `
        --add-data "frontend\dist;frontend\dist" `
        --hidden-import "uvicorn" `
        --hidden-import "fastapi" `
        --hidden-import "pydantic" `
        --hidden-import "pydantic_settings" `
        --hidden-import "webview" `
        --hidden-import "clr_loader" `
        --hidden-import "pythonnet" `
        "backend\desktop_launcher.py"
} finally {
    Pop-Location
}

# 3. Create launch shortcut / batch helper in dist
Write-Host "[3/3] Creating distribution assets..." -ForegroundColor Yellow
$DistDir = "$ProjectRoot\dist\SmartManager"
$BatContent = @"
@echo off
start "" "%~dp0SmartManager.exe"
"@
Set-Content -Path "$DistDir\Launch-SmartManager.bat" -Value $BatContent

Write-Host "=========================================================" -ForegroundColor Green
Write-Host "Build complete! Standalone app located at:" -ForegroundColor Green
Write-Host "  $DistDir\SmartManager.exe" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
