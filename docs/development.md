# Smart-Manager: Developer Guide

This guide covers setting up, developing, testing, and building the Smart-Manager AI-powered file explorer application.

---

## 1. Prerequisites

- **Operating System:** Windows 10 or Windows 11 (64-bit)
- **Python:** 3.10 to 3.12 (64-bit)
- **Node.js:** v18.0.0 or higher
- **Package Manager:** npm (v9+)
- **Optional Local LLM:** [Ollama](https://ollama.ai) (for fully offline local AI planning)

---

## 2. Repository Structure

```
Smart-Manager/
├── backend/
│   ├── app.py                   # FastAPI REST application & routing
│   ├── agent/
│   │   ├── planner.py           # AI task & file batch plan generator
│   │   ├── model.py             # Pydantic schemas (FilePlanPreview, etc.)
│   │   └── runtime.py           # Multi-step agent execution engine
│   ├── execution/
│   │   ├── filesystem.py        # Secure filesystem service (browse, duplicates, storage, undo)
│   │   └── action_dispatcher.py # Parameterized operation dispatcher
│   ├── security/
│   │   ├── permissions.py       # SecurityPolicy, traversal protection, risk classification
│   │   └── dpapi.py             # Windows DPAPI credential encryption
│   ├── storage/
│   │   ├── database.py          # SQLite schema & connection management
│   │   └── history.py           # Operation history & undo ledger repository
│   └── tests/                   # Pytest test suites (37 passing tests)
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FileBrowser.jsx          # Explorer list/grid, breadcrumbs, search, context menu
│   │   │   ├── AiCommandPanel.jsx       # Natural language command bar & plan preview
│   │   │   ├── FilePreviewModal.jsx     # Safe text/code/metadata viewer
│   │   │   ├── DuplicatesModal.jsx      # SHA-256 duplicate clusters & clean up
│   │   │   ├── StorageAnalysisModal.jsx # Large files, empty folders, temp file analyzer
│   │   │   ├── Sidebar.jsx              # Quick folders, drives, storage meters, undo banner
│   │   │   └── Header.jsx               # Status indicators & top bar
│   │   ├── services/
│   │   │   └── api.js                   # REST client with Explorer endpoints
│   │   ├── App.jsx                      # Main React view coordinator
│   │   └── style.css                    # Modern dark glassmorphic styling
│   └── vite.config.js
├── docs/                        # Architecture, audit report, security model, comparison
├── Launch-SmartManager.bat      # Windows double-click launcher
└── requirements.txt             # Python dependencies
```

---

## 3. Local Development Setup

### 3.1 Backend Setup

1. **Create and activate virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Copy `.env.example` to `.env` (or configure via application settings UI). Key settings:
   ```ini
   AI_MODE=online          # or 'local' for Ollama
   GROQ_API_KEY=           # Optional: for online Groq LLM
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5-coder:7b
   ```

4. **Run FastAPI dev server:**
   ```powershell
   .\.venv\Scripts\uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
   ```

### 3.2 Frontend Setup

1. **Install dependencies:**
   ```powershell
   cd frontend
   npm install
   ```

2. **Run Vite development server:**
   ```powershell
   npm run dev
   ```
   Vite starts on `http://localhost:5173`, automatically proxying API calls to backend port 8000.

### 3.3 One-Click Launcher

To launch both backend and frontend together with health checking:
```powershell
.\Launch-SmartManager.bat
```

---

## 4. Running Tests

### 4.1 Backend Test Suite

Run the full pytest suite (37 tests):
```powershell
.\.venv\Scripts\pytest.exe -v
```

Run file explorer-specific tests:
```powershell
.\.venv\Scripts\pytest.exe -v backend/tests/test_explorer.py
```

Run security and traversal tests:
```powershell
.\.venv\Scripts\pytest.exe -v backend/tests/test_security.py
```

### 4.2 Frontend Build Validation

Verify that all JSX components, icons, and CSS compile without errors:
```powershell
cd frontend
npm run build
```

---

## 5. Adding New Capabilities

### 5.1 Adding a File Category
In `backend/execution/filesystem.py`, update `get_file_category()`:
```python
def get_file_category(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    # Add new extensions to mapping:
    if ext in [".rs", ".go", ".ts", ".jsx"]:
        return "code"
    ...
```

### 5.2 Adding a Safe File Operation
1. Implement the deterministic operation in `backend/execution/filesystem.py` with an inverse action payload for undo support.
2. Record the inverse operation in `history_repo.record_operation()` inside `backend/storage/history.py`.
3. Add the route in `backend/app.py`.
4. Add the frontend API call in `frontend/src/services/api.js`.
5. Add unit tests in `backend/tests/test_explorer.py`.

---

## 6. Coding Standards & Safety Guidelines

- **Never introduce shell execution:** Avoid `os.system`, `subprocess.call` with shell=True, or passing user input to `cmd.exe`.
- **Always validate paths:** Use `security_policy.validate_target_path()` or `security_policy.validate_file_explorer_path()`.
- **No silent overwrites:** Always verify destination existence and handle collisions with explicit numbering or conflict flagging.
- **Support Undo:** Every write, move, or trash operation should produce a corresponding entry in `operation_history`.
