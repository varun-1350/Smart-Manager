# Smart Manager — Autonomous Local AI Agent for Windows

Smart Manager is a privacy-first, desktop-native AI assistant for Windows. Powered by a local language model running through Ollama, Smart Manager translates high-level natural language instructions into dynamic multi-step plans and executes them through controlled operating system interfaces.

---

## Architecture Overview

Smart Manager follows a strict separation of concerns between model decision-making and operating system interaction:

```
+-----------------------------------------------------------+
|                   Tauri 2 Desktop Shell                   |
|  +-----------------------------------------------------+  |
|  |             React 19 / Vite Web Frontend            |  |
|  |  (Conversational UI, Action Timeline, Confirmations)|  |
|  +---------------------------+-------------------------+  |
+------------------------------|----------------------------+
                               | REST / WebSocket API
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
|  |  & Approvals      |       | - Filesystem            |  |
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
                 |   (e.g., gemma2:2b)       |
                 +---------------------------+
```

1. **No Cloud LLMs**: All planning and reasoning happens on your local machine using Ollama. No personal data, file content, or telemetry is sent to third-party AI services.
2. **Observe-Plan-Act-Verify Loop**: The agent inspects context, formulates actions, enforces safety gates, interacts with Windows APIs, and verifies outcomes before reporting completion.
3. **Structured Outputs**: Model suggestions are parsed and validated through strict Pydantic schemas before any action dispatcher executes them.
4. **Approval & Risk Gates**: Destructive operations (such as file deletion, process termination, bulk movement) trigger explicit confirmation prompts in the UI.

---

## Technology Stack

- **Desktop Shell**: Tauri 2 with Rust (Windows desktop wrapper)
- **Frontend**: React 19, Vite, Vanilla CSS
- **Backend**: Python 3.12, FastAPI, Uvicorn, WebSockets
- **Agent Intelligence**: Local Ollama (`gemma2:2b`, configurable)
- **Validation**: Pydantic v2
- **Persistence**: SQLite (Local history, action audit trails)
- **Testing**: Pytest, Pytest-asyncio

---

## Current Status: Phase 1 (Foundation)

- [x] Project architecture established and repository initialized.
- [x] Python virtual environment configured with core backend packages.
- [x] React/Vite frontend scaffolded.
- [x] Tauri 2 configuration and Rust shell scaffolded.
- [x] Environment configuration (`.env.example`, `.env`) with loopback-only defaults.
- [x] Initial FastAPI health and model ping endpoints implemented.
- [x] Ollama daemon verification and model provisioning in progress.

---

## Prerequisites & Installation

### 1. Windows Runtimes
- **Python**: 3.12+ (64-bit recommended)
- **Node.js**: v20+ (Node v22 installed)
- **Ollama**: Installed and running on `http://127.0.0.1:11434`
- **Rust / Cargo**: Optional during development, required for Tauri binary packaging.

### 2. Ollama Model Setup
Ensure Ollama is running, then pull the recommended model:
```powershell
ollama pull gemma2:2b
```

You can customize the model by setting `OLLAMA_MODEL` in `.env`.

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

### Start the Python Backend:
```powershell
.\.venv\Scripts\python.exe backend\app.py
```
The API server will listen on `http://127.0.0.1:8765`. Health check is available at `http://127.0.0.1:8765/api/health`.

### Start the React Frontend:
```powershell
cd frontend
npm run dev
```
The UI will be accessible at `http://127.0.0.1:5173`.

---

## Running Tests

Run the test suite using pytest:
```powershell
.\.venv\Scripts\pytest.exe backend\tests -v
```

---

## Configuration & Security Notes

- **Loopback Binding**: The backend server is strictly bound to `127.0.0.1` (`SMART_MANAGER_HOST`) to prevent unauthorized local network exposure.
- **Safety Enforcement**: High-risk actions require user approval before execution.
- **Data Privacy**: Conversation history and logs are stored locally in `data/smart_manager.db`. No telemetry or personal file data is ever transmitted externally.

---

## Known Limitations

- Packaging as a standalone `.exe` installer via Tauri requires Rust and cargo to be configured in PATH.
- Local model performance and planning accuracy depend on available CPU/GPU resources and model size.
