# Changelog

All notable changes to the Smart Manager project will be documented in this file.

## [0.2.1] - Hardware-Aware Development & Resource Optimization Add-on (Current)

### Added
- **Hardware Diagnostic & Benchmark Suite** ([backend/benchmark_hardware.py](file:///d:/my%20projects/Smart-Manager/backend/benchmark_hardware.py)):
  - Empirical benchmarking for RTX 3050 (6GB VRAM) and 16GB RAM.
  - Measured 4096 vs 2048 token context windows: 2048-token context window runs at 121.4 tok/s and 2940 MB VRAM, keeping >3.2 GB VRAM free.
  - On-demand and automated VRAM unloading: drops GPU VRAM from 2952 MB to 112 MB and process RAM from 3008 MB to 52 MB.
- **Hardware-Aware Ollama Client** ([backend/agent/model.py](file:///d:/my%20projects/Smart-Manager/backend/agent/model.py)):
  - Added strict concurrency control (`asyncio.Semaphore(1)`) to guarantee only 1 model executes at any time, eliminating memory collisions.
  - Added configurable parameters for context size (`num_ctx`), prediction length (`num_predict`), evaluation batch (`num_batch`), and idle unload (`keep_alive`).
  - Added `unload_model()` to purge model weights and memory on demand.
- **Resource Monitoring & Control API** ([backend/app.py](file:///d:/my%20projects/Smart-Manager/backend/app.py)):
  - Added `GET /api/system/resources` endpoint reporting live system RAM, process RAM, and GPU VRAM via `nvidia-smi`.
  - Added `POST /api/model/unload` endpoint for on-demand memory liberation.
  - Added resource configuration update support in `POST /api/config`.
- **UI Diagnostics & Memory Controls** ([frontend/src/components/SettingsModal.jsx](file:///d:/my%20projects/Smart-Manager/frontend/src/components/SettingsModal.jsx)):
  - Added live hardware telemetry card displaying RAM and RTX 3050 VRAM usage.
  - Added "Free VRAM Now" button for instant memory release.
  - Added interactive context window selector (2048 vs 4096 tokens) and idle timeout selector (2m, 5m, 15m, 0s).
- **Prompt Token Guarding**:
  - Bounded directory listing to 50 items in [backend/execution/filesystem.py](file:///d:/my%20projects/Smart-Manager/backend/execution/filesystem.py).
  - Bounded recent prompt history to 3 steps in [backend/agent/planner.py](file:///d:/my%20projects/Smart-Manager/backend/agent/planner.py).
- **Automated Tests**:
  - Added [backend/tests/test_hardware_resource.py](file:///d:/my%20projects/Smart-Manager/backend/tests/test_hardware_resource.py) (all 21 backend tests passing).

### Added
- **Local AI Integration & Structured Action Pipeline**:
  - Implemented `OllamaClient` in [backend/agent/model.py](file:///d:/my%20projects/Smart-Manager/backend/agent/model.py) with Pydantic v2 validation (`AgentStepDecision`, `ProposedAction`).
  - Added robust JSON schema extraction, malformed output recovery, and configurable model selection (`gemma4:e2b`).
- **Autonomous Agent Runtime Loop**:
  - Implemented dynamic planning in [backend/agent/planner.py](file:///d:/my%20projects/Smart-Manager/backend/agent/planner.py).
  - Built the Observe-Plan-Act-Verify iterative loop in [backend/agent/runtime.py](file:///d:/my%20projects/Smart-Manager/backend/agent/runtime.py).
  - Implemented context management, working memory, and step bounds in [backend/agent/context.py](file:///d:/my%20projects/Smart-Manager/backend/agent/context.py).
- **Controlled Windows Interaction Layer**:
  - Filesystem capabilities in [backend/execution/filesystem.py](file:///d:/my%20projects/Smart-Manager/backend/execution/filesystem.py): directory listing, file metadata inspection, recursive search, folder creation, copying, moving, renaming, safe deletion, and native opening.
  - Process and storage capabilities in [backend/execution/processes.py](file:///d:/my%20projects/Smart-Manager/backend/execution/processes.py): process enumeration, info, launch (including Windows apps & games), termination, and partition storage diagnostics.
  - Browser and web capabilities in [backend/execution/browser.py](file:///d:/my%20projects/Smart-Manager/backend/execution/browser.py): Google search, URL navigation, and YouTube media requests.
  - Controlled PowerShell command execution in [backend/execution/shell.py](file:///d:/my%20projects/Smart-Manager/backend/execution/shell.py).
- **Security & Approval Engine**:
  - Built strict permission evaluation in [backend/security/permissions.py](file:///d:/my%20projects/Smart-Manager/backend/security/permissions.py).
  - Classified action risk levels (`READ_ONLY`, `LOW`, `MODERATE`, `HIGH`, `CRITICAL`).
  - Enforced path traversal prevention and blocked tampering with protected OS directories (`C:\Windows`, `System32`, etc.).
  - Added approval pause and resumption for destructive operations (`fs_delete_file`, `proc_kill`, `shell_run_command`).
- **Local Persistence & Action Audit Trails**:
  - SQLite database in [backend/storage/database.py](file:///d:/my%20projects/Smart-Manager/backend/storage/database.py) and repository in [backend/storage/history.py](file:///d:/my%20projects/Smart-Manager/backend/storage/history.py) for conversations, messages, and action logs.
- **Modern Desktop Conversational UI**:
  - React/Vite interface featuring sidebar history, model status indicators, action timelines, confirmation modals for dangerous actions, and runtime settings.
- **Comprehensive Test Suite**:
  - 18 passing tests covering configuration, app foundation, execution layer, security policies, model schema parsing, and multi-step agent runtime workflows.

## [0.1.0] - Phase 1: Environment and Project Foundation

### Added
- Initialized Git repository and comprehensive `.gitignore`.
- Created Python 3.12 virtual environment (`.venv`) and installed backend dependencies.
- Scaffolding of React/Vite frontend application in `frontend/`.
- Scaffolding of Tauri 2 shell configuration and capabilities in `src-tauri/`.
- Environment configuration (`.env.example`, `.env`) with loopback-only host binding.
- Initial project documentation in `README.md`.
