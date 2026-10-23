@echo off
setlocal
cd /d "%~dp0"

echo =========================================================
echo               Starting Smart Manager Desktop             
echo =========================================================

REM Check if virtualenv python exists
if not exist ".venv\Scripts\python.exe" (
    echo Error: Python virtual environment not found in .venv.
    echo Please run scripts\setup_environment.ps1 first.
    pause
    exit /b 1
)

REM Start Ollama only for Local or Auto inference. Online models such as
REM Gemini do not need a local daemon or an additional command window.
set "AI_MODE=local"
for /f "usebackq delims=" %%M in (`".venv\Scripts\python.exe" "backend\launch_mode.py"`) do set "AI_MODE=%%M"

if /I "%AI_MODE%"=="online" (
    echo [Info] Online provider selected; Ollama will not be started.
) else (
    curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [Notice] Starting Ollama daemon in the background...
        powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -Command "Start-Process -FilePath 'ollama.exe' -ArgumentList 'serve' -WindowStyle Hidden" >nul 2>&1
        timeout /t 2 /nobreak >nul
    )
)

REM Run desktop launcher
echo Launching Smart Manager...
start "" ".venv\Scripts\python.exe" "backend\desktop_launcher.py"
exit /b 0
