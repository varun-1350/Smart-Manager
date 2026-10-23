# Smart Manager

Smart Manager is a privacy-focused Windows desktop assistant. Describe a task in plain language; Smart Manager plans it, shows any required approval, performs the approved action, and records the result locally.

## What it does

- Finds, opens, organizes, copies, moves, renames, and deletes files.
- Creates folders and text files after your approval.
- Opens applications, lists processes, and reports storage use.
- Searches the web and opens approved HTTP(S) links.
- Uses local Ollama models or an explicitly configured online provider.

## Safety model

Smart Manager treats model output as untrusted input.

- The backend listens only on loopback.
- The desktop app uses a per-launch session secret for backend requests.
- Every state-changing action requires explicit approval.
- The approval dialog states the intended change in plain language; technical details are optional.
- Generic shell execution is disabled.
- Protected operating-system directories and path traversal attempts are blocked.
- API keys are stored with Windows DPAPI and online endpoints must use HTTPS.

## Interface

The interface is intentionally concise:

- The chat shows the request, outcome, and current status first.
- Activity, results, and technical diagnostics are collapsed under **Activity**.
- Approval is a dedicated decision screen—no change happens before approval.
- The sidebar contains tasks, current model status, settings, and one memory-release action.

## Architecture

```text
React UI in Edge WebView2
        │ authenticated loopback requests
        ▼
FastAPI backend
 ├─ task coordinator and approval state
 ├─ provider adapters: Ollama or opt-in online provider
 ├─ validated OS action dispatcher
 └─ SQLite task ledger, history, and action audit log
        │
        ├─ Windows filesystem / process / browser APIs
        └─ Ollama or configured HTTPS AI provider
```

SQLite uses WAL mode, foreign keys, a busy timeout, indexed history, and a durable task-event ledger. Unfinished tasks are marked as interrupted after a backend restart.

## Start the app

Double-click SmartManager.exe

The launcher reads the selected provider:

- **Online provider selected:** Ollama is not started.
- **Local or Auto mode:** Ollama starts only when required and not already running. It starts hidden.

## Development

Set up dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_environment.ps1
```

Run the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8765
```

Run the frontend:

```powershell
cd frontend
npm run dev
```

## Tests and build

Run backend tests:

```powershell
.\.venv\Scripts\pytest.exe -v
```

Build the frontend:

```powershell
cd frontend
npm run build
```

Build the Windows distribution:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_dist.ps1
```
