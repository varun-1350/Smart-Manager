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

REM Check if Ollama is running
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [Notice] Starting Ollama daemon...
    start "" ollama serve
    timeout /t 2 /nobreak >nul
)

REM Run desktop launcher
echo Launching Smart Manager...
start "" ".venv\Scripts\python.exe" "backend\desktop_launcher.py"
exit /b 0
