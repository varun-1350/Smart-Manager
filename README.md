# Smart-Manager: AI-Powered File Explorer for Windows

Smart-Manager is a modern, privacy-focused, AI-powered file explorer for Windows. It lets users navigate their filesystem normally or manage files using natural-language commands—inspecting structured action previews before any changes occur, with instant undo support for all operations.

---

## What It Does

- **Modern File Explorer Interface:**
  - Interactive breadcrumb navigation with clickable directory segments.
  - Switchable Grid and List layouts with file size, modified date, and category tags (Documents, Spreadsheets, Images, Videos, Audio, Code, Archives).
  - Quick-access shortcuts to standard Windows profile folders (Desktop, Downloads, Documents, Pictures, Videos, Music).
  - Real-time physical drive capacity meters with free/used storage metrics.
  - Multi-select batch operations, right-click context menus, and inline file search.
  - Safe in-memory text, markdown, JSON, and source code previews without risk of binary execution.

- **Natural-Language File Operations:**
  - Execute commands such as:
    - *"Organize my Downloads folder based on file type."*
    - *"Find duplicate files in my Documents folder."*
    - *"Group my images by year and month."*
    - *"Show me files that look like temporary files."*
    - *"Clean up large files I haven't used recently."*

- **Structured Action Plans & Approval:**
  - Before modifying files, the AI produces a typed `FilePlanPreview` displaying exact source paths, destination paths, conflict warnings, and risk levels.
  - The application deterministically evaluates all proposed paths against security policies.

- **Atomic Undo & Recovery Ledger:**
  - Moves, copies, renames, and deletions are recorded in an atomic SQLite history ledger with inverse operations.
  - One-click rollback restores relocated, renamed, or trashed files.
  - Non-destructive `safe_trash` stages deleted items in `.smart_manager_trash` rather than permanently erasing them.

- **Cryptographic Duplicate & Storage Diagnostics:**
  - 2-pass exact duplicate detection combining size filtering with chunked SHA-256 hashing.
  - Storage reclamation analyzer for large files (>50MB), empty directories, and temporary files (`.tmp`, `.log`, `.bak`, `.cache`).

- **Flexible AI Engine:**
  - Runs with local models via [Ollama](https://ollama.ai) for 100% offline privacy.
  - Supports high-speed hosted endpoints (Groq, Cerebras, OpenAI).
  - Features an instant, deterministic rule-based organization fallback when models are offline or unavailable.

---

## Architecture & Security

```text
React Frontend (Vite / Desktop Window)
        │ Authenticated loopback requests
        ▼
FastAPI Backend (127.0.0.1:8000 / 8765)
 ├─ File Explorer Service: native os.scandir, sorting, pagination, SHA-256 hashing
 ├─ AI Planning Engine: structured JSON plans & deterministic semantic fallbacks
 ├─ Security Policy Gate: traversal shield (..), protected Windows dir protection
 ├─ Operation History: SQLite ledger with inverse action rollback
 └─ Windows DPAPI: encrypted credential storage for API keys
```

- **Loopback Only:** Binds strictly to `127.0.0.1`.
- **Zero Trust:** Models never execute arbitrary shell commands. All operations use parameterized Python filesystem handlers.
- **Protected Paths:** Direct access or manipulation of `C:\Windows`, `System32`, `Program Files`, and system partitions is blocked.

---

## Getting Started

### Prerequisites
- Windows 10 or 11 (64-bit)
- Python 3.10 to 3.12
- Node.js 18+ and npm

### Double-Click Launch
Run the turnkey Windows launcher:
```powershell
.\Launch-SmartManager.bat
```
The launcher automatically evaluates whether an online or local AI provider is configured, launches the FastAPI backend with health validation, and opens the application.

---

## Development & Testing

### Backend
Activate virtual environment and run the server:
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Run test suite (37 tests):
```powershell
.\.venv\Scripts\pytest.exe -v
```

### Frontend
Install dependencies and run Vite dev server:
```powershell
cd frontend
npm install
npm run dev
```

Build production bundle:
```powershell
cd frontend
npm run build
```

---

## Documentation

- [Architecture Guide](file:///d:/my%20projects/Smart-Manager/docs/architecture.md)
- [Security & Threat Model](file:///d:/my%20projects/Smart-Manager/docs/security-model.md)
- [Codebase Audit Report](file:///d:/my%20projects/Smart-Manager/docs/audit-report.md)
- [Project Comparison (Super Productivity, Plane, Khoj, Everything)](file:///d:/my%20projects/Smart-Manager/docs/project-comparison.md)
- [Developer Guide](file:///d:/my%20projects/Smart-Manager/docs/development.md)
