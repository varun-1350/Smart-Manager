# Smart Manager — Autonomous Local AI Agent for Windows

Smart Manager is a privacy-first, desktop-native AI assistant for Windows. Powered by a local language model running through Ollama (defaulting to `gemma4:e2b`), Smart Manager translates high-level natural language instructions into dynamic multi-step plans and executes them through controlled operating system interfaces.

---

## Architecture Overview

Smart Manager strictly separates model decision-making from operating system interaction:

```
+-----------------------------------------------------------+
|                   Tauri 2 Desktop Shell                   |
|  +-----------------------------------------------------+  |
|  |             React 19 / Vite Web Frontend            |  |
|  |  (Conversational UI, Action Timeline, Confirmations)|  |
|  +---------------------------+-------------------------+  |
+------------------------------|----------------------------+
                               | REST API (Loopback only)
                               v
+-----------------------------------------------------------+
|               Smart Manager Python 3.12 Backend           |
|                                                           |
|  +-------------------+       +-------------------------+  |
|  |   FastAPI App     | <---> | Autonomous Agent Loop   |  |
|  +-------------------+       | (Observe-Plan-Act-Verify|  |
|                              +------------+------------+  |
|                                           |               |
|            +------------------------------+               |
|            v                              v               |
|  +-------------------+       +-------------------------+  |
|  |  Security Policy  |       | Windows Action Runtime  |  |
|  |  & Approvals      |       | - Filesystem Operations |  |
|  +-------------------+       | - Processes & Storage   |  |
|                              | - Applications & Web    |  |
|  +-------------------+       +-------------------------+  |
|  | SQLite Local DB   |                    |               |
|  | (Conversations    |                    v               |
|  |  & Action Logs)   |         Windows Operating System   |
|  +-------------------+                                    |
+------------------------------|----------------------------+
                               v
                 +---------------------------+
                 |    Local Ollama Daemon    |
                 |      (gemma4:e2b)         |
                 +---------------------------+
```

1. **100% Local Inference**: All planning and reasoning happens on your local machine using Ollama. No personal data, file content, or telemetry is sent to third-party cloud AI services.
2. **Observe-Plan-Act-Verify Loop**: The agent inspects context, formulates actions, enforces safety gates, interacts with Windows APIs, and verifies outcomes before reporting completion.
3. **Structured Outputs**: Model suggestions are parsed and validated through strict Pydantic schemas before any action dispatcher executes them.
4. **Approval & Risk Gates**: Destructive operations (such as file deletion, process termination, shell command execution) trigger explicit confirmation prompts in the UI.

---

## Technology Stack

- **Desktop Shell**: Tauri 2 with Rust (Windows desktop wrapper)
- **Frontend**: React 18, Vite, Lucide Icons, Custom CSS
- **Backend**: Python 3.12, FastAPI, Uvicorn, WebSockets
- **Agent Intelligence**: Local Ollama (`gemma4:e2b`, configurable)
- **Validation**: Pydantic v2
- **Persistence**: SQLite (Local history, action audit trails in `data/smart_manager.db`)
- **Testing**: Pytest, Pytest-asyncio

---

## Current Status: Version 0.2.0

- [x] **Local AI Integration**: Ollama client with structured JSON Schema output validation and malformed recovery.
- [x] **Hardware-Aware Resource Optimization (RTX 3050 6GB / 16GB RAM)**:
  - Strict single-model concurrency gate (`asyncio.Semaphore(1)`).
  - Configurable context window (2048 tokens default, saving memory while keeping >3.2 GB VRAM free).
  - Empirical benchmarking tool ([backend/benchmark_hardware.py](file:///d:/my%20projects/Smart-Manager/backend/benchmark_hardware.py)): ~121-123 tokens/sec on RTX 3050.
  - On-demand and automatic VRAM/RAM unloading (`keep_alive` & `/api/model/unload`) dropping VRAM to 112 MB and process RAM to 52 MB.
  - Live hardware telemetry endpoint (`/api/system/resources`) and UI memory gauge.
- [x] **Autonomous Agent Loop**: Iterative observe-plan-act-verify loop with bounded execution.
- [x] **Windows Interaction Layer**:
  - Filesystem: search, list, metadata, directory creation, copy, move, rename, delete, open.
  - System: drive storage inspection, process enumeration, process launch, process termination.
  - Browser: Google search, URL navigation, YouTube queries.
  - Shell: Controlled PowerShell commands.
- [x] **Security Engine**: Path traversal protection, system directory shielding, risk classification (`READ_ONLY`, `LOW`, `MODERATE`, `HIGH`, `CRITICAL`), and user approval gates.
- [x] **Local Persistence**: SQLite database for conversations, message history, and action audit logs.
- [x] **Conversational Interface**: ChatGPT/Gemini-style React interface with action timeline and approval modals.
- [x] **Test Suite**: 18 unit and integration tests passing.

---

## Prerequisites & Installation

### 1. Windows Runtimes
- **Python**: 3.12+ (64-bit recommended)
- **Node.js**: v20+ (Node v22 installed)
- **Ollama**: Installed and running on `http://127.0.0.1:11434` with `gemma4:e2b` pulled.

### 2. Ollama Model Setup
```powershell
ollama pull gemma4:e2b
```

### 3. Backend Setup
```powershell
# In project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 4. Frontend Setup
```powershell
cd frontend
npm install
```

---

## Running in Development

### 1. Start the Python Backend:
```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8765
```
The API server will listen on `http://127.0.0.1:8765`. Health check is available at `http://127.0.0.1:8765/api/health`.

### 2. Start the React Frontend:
```powershell
cd frontend
npm run dev
```
The UI will be accessible in your browser at `http://127.0.0.1:5173`.

---

## Running Tests

Run the full backend test suite:
```powershell
.\.venv\Scripts\pytest.exe -v
```

Build the frontend production bundle:
```powershell
cd frontend
npm run build
```

---

## Security Notes

- **Loopback Binding**: The backend server is strictly bound to `127.0.0.1` (`SMART_MANAGER_HOST`) to prevent unauthorized local network exposure.
- **Safety Enforcement**: High-risk actions (`fs_delete_file`, `proc_kill`, `shell_run_command`) require user approval before execution.
- **Data Privacy**: Conversation history and logs are stored locally in `data/smart_manager.db`. No telemetry or personal file data is ever transmitted externally.
