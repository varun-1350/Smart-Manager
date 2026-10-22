# Changelog

All notable changes to the Smart Manager project will be documented in this file.

## [0.2.0] - Autonomous Local Agent Runtime, Windows Interaction & Safety Layer (Current)

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
