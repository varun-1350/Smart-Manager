# Changelog

All notable changes to the Smart Manager project will be documented in this file.

## [0.4.0] - AI-Powered File Explorer Transformation (Current)

### Added
- **Core File Explorer Interface**:
  - Breadcrumb navigation with clickable path segments.
  - Switchable Grid and List views with file size, modified date, and category classification tags.
  - Multi-select batch operations bar (Copy, Move, Trash, Preview).
  - Right-click context menus for files and folders.
  - Quick access locations (Desktop, Downloads, Documents, Pictures, Videos, Music) and active physical drive detection with storage meters.
  - Real-time client-side search filtering.
  - Safe in-memory text, markdown, JSON, and source file preview modal with native OS launcher.
- **Natural-Language Action Plans & AI Command Panel**:
  - Natural-language command bar with instant suggested action chips.
  - Structured `FilePlanPreview` displaying affected files, source/destination mappings, conflict warnings, and risk levels.
  - Deterministic rule-based fallback organization engine for zero-latency offline operation.
- **Cryptographic Duplicate & Storage Diagnostics**:
  - 2-pass exact duplicate detection engine using size filtering and 64KB-chunked SHA-256 cryptographic hashing.
  - Storage reclamation analyzer for large files (>50MB), empty folders, and temporary files.
- **Atomic Operation Ledger & Reversible Undo**:
  - SQLite `operation_history` table recording batch IDs, actions, and inverse operation payloads.
  - Single-click rollback engine restoring moved, renamed, copied, or trashed files.
  - Reversible `safe_trash` staging area (`.smart_manager_trash`) preventing permanent data loss.
- **Security & Path Traversal Shields**:
  - Strict path traversal detection (`..`, `~`) and canonicalization via `pathlib.Path.resolve()`.
  - Windows protected directory prevention for `C:\Windows`, `System32`, `Program Files`, and system partitions.
  - Deterministic risk classification matrix independent of AI model suggestions.
- **Comprehensive Documentation**:
  - `docs/audit-report.md`: Initial audit findings and verified bug fixes.
  - `docs/project-comparison.md`: Architecture analysis comparing Super Productivity, Plane, Khoj, and Everything.
  - `docs/architecture.md`: Detailed component blueprints, data flows, and subsystem specifications.
  - `docs/security-model.md`: Threat model, zero-trust policies, and traversal defenses.
  - `docs/development.md`: Developer guide, local environment setup, testing, and contribution patterns.
- **Testing & Verification**:
  - Added `backend/tests/test_explorer.py` covering directory browsing, quick locations, file previews, safe move/trash undo, SHA-256 duplicate detection, storage analysis, and API routes.
  - Full backend test suite passing with 37 tests.
  - Frontend production build verified with Vite 5.4.

### Fixed
- **Windows CMD Batch Quoting in `Launch-SmartManager.bat`**: Fixed `The system cannot find the path specified` error caused by CMD backtick quote stripping when evaluating launch mode.
- **Hardware Telemetry Test Assertion**: Dynamic comparison against `settings.ollama_num_ctx` in `test_hardware_resource.py`.

## [0.3.0] - Phase 11: Windows Packaging, Native Desktop Launcher & Turnkey Distribution

### Added
- **Native Windows Desktop Window Launcher** ([backend/desktop_launcher.py](file:///d:/my%20projects/Smart-Manager/backend/desktop_launcher.py)):
  - Launches a native desktop window utilizing Microsoft Edge WebView2 (`155.0.4283.62`).
  - Automatically manages background FastAPI backend startup, health polling, and clean shutdown on window close.
- **Turnkey One-Click Launch Script** ([Launch-SmartManager.bat](file:///d:/my%20projects/Smart-Manager/Launch-SmartManager.bat)):
  - Starts the desktop application with a single click, checking Ollama status and launching the environment automatically.
- **Automated Windows Distribution Builder** ([scripts/build_windows_dist.ps1](file:///d:/my%20projects/Smart-Manager/scripts/build_windows_dist.ps1)):
  - Bundles the frontend production bundle and Python backend via PyInstaller into a standalone portable folder in `dist/SmartManager/`.
- **Environment Verification & Setup Script** ([scripts/setup_environment.ps1](file:///d:/my%20projects/Smart-Manager/scripts/setup_environment.ps1)):
  - Reproducible 5-step installer verifying Python, Node, Ollama model availability, virtualenv, and frontend production builds.
- **Tauri Shell Configuration**:
  - Full configuration maintained in [src-tauri/tauri.conf.json](file:///d:/my%20projects/Smart-Manager/src-tauri/tauri.conf.json) and [src-tauri/Cargo.toml](file:///d:/my%20projects/Smart-Manager/src-tauri/Cargo.toml) for building Windows `.msi` installers when `rustup` is configured.
- **Unit Tests**:
  - Added [backend/tests/test_launcher.py](file:///d:/my%20projects/Smart-Manager/backend/tests/test_launcher.py) (23 passing tests total).

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
