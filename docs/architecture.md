# Smart-Manager: System Architecture

Smart-Manager is an AI-powered file explorer for Windows designed to combine native filesystem performance with natural-language file organization, duplicate detection, storage cleanup, and atomic reversible operations.

---

## 1. Architectural Principles

1. **Filesystem as Source of Truth:**
   Directory browsing, metadata queries, and storage stats read directly from the native Windows filesystem using OS APIs (`os.scandir`, `os.stat`, `shutil`) rather than routing routine navigation through an AI model.
2. **Untrusted Model Planning:**
   The AI generates structured JSON action proposals (`FilePlanPreview`). The model is never granted direct shell execution or unvalidated filesystem access.
3. **Deterministic Security Verification:**
   All proposed paths and operations pass through an independent, deterministic security policy (`SecurityPolicy`) before any preview is displayed or action is executed.
4. **Inspect Before Execution:**
   Natural-language operations produce an explicit, typed action plan showing exact source paths, destination paths, potential overwrites, and risk levels. Execution requires user approval.
5. **Reversibility & Auditability:**
   Destructive operations (trash, move, copy, rename) are logged with inverse operations in an atomic SQLite history ledger, enabling single-click rollback.

---

## 2. High-Level Component Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite)                           │
│  ┌───────────────────────┐  ┌────────────────────────────────────────┐ │
│  │   Sidebar Navigation  │  │            File Browser                │ │
│  │ - Quick Locations     │  │ - Breadcrumb Navigation                │ │
│  │ - Physical Drives     │  │ - List / Grid View & Sorting           │ │
│  │ - Storage Meters      │  │ - Multi-Select & Context Menus         │ │
│  │ - Mode Switcher       │  │ - Safe File Previews                   │ │
│  └───────────────────────┘  └────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │              AI Command & Action Plan Panel                       │ │
│  │ - Natural Language Input ("Organize Downloads by type")           │ │
│  │ - Typed Action Plan Preview (Move, Copy, Trash, Skip)             │ │
│  │ - Risk Ratings, Conflict Warnings, One-Click Execution & Undo     │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST (FastAPI)
┌───────────────────────────────────▼────────────────────────────────────┐
│                       FastAPI Backend Server                           │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                         API Routes                                │ │
│  │ /api/explorer/browse          /api/explorer/plan                  │ │
│  │ /api/explorer/locations       /api/explorer/execute-plan          │ │
│  │ /api/explorer/preview         /api/explorer/undo                  │ │
│  │ /api/explorer/duplicates      /api/explorer/storage-analysis      │ │
│  └──────────────────┬────────────────────────────────┬───────────────┘ │
│                     │                                │                 │
│  ┌──────────────────▼──────────────┐  ┌──────────────▼──────────────┐  │
│  │       AI Planning Engine        │  │     Filesystem Service      │  │
│  │ - Prompt formulation            │  │ - Fast Directory Traverser  │  │
│  │ - Ollama / Online Provider      │  │ - SHA-256 Duplicate Finder  │  │
│  │ - Structured Plan Extractor     │  │ - Storage Analyzer          │  │
│  │ - Deterministic Rule Fallback   │  │ - Safe Trash / Move / Copy  │  │
│  └──────────────────┬──────────────┘  └──────────────┬──────────────┘  │
│                     │                                │                 │
│  ┌──────────────────▼────────────────────────────────▼──────────────┐  │
│  │                     Security Policy Gate                         │  │
│  │ - Strict Path Traversal Defense (..)                             │  │
│  │ - Protected Windows System Directory Blocking (System32, etc.)   │  │
│  │ - Deterministic Risk Rating Calculation (LOW, MEDIUM, HIGH)      │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     │                                  │
│  ┌──────────────────────────────────▼───────────────────────────────┐  │
│  │             Operation History & Reversible Ledger                │  │
│  │ - SQLite `operation_history` table (batch IDs, inverse actions)  │  │
│  │ - Reversible trash, move, copy, rename rollback engine           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend Subsystems

### 3.1 Filesystem Service (`backend/execution/filesystem.py`)
Provides deterministic filesystem interactions:
- **`browse_directory`**: Uses `os.scandir` to retrieve folder contents with pagination, sorting by name/size/date/type, and categorizing files (Documents, Spreadsheets, Images, Videos, Audio, Code, Archives).
- **`get_quick_locations`**: Resolves standard Windows profile directories (Desktop, Downloads, Documents, Pictures, Videos, Music) and detects active physical drives with total/free byte metrics.
- **`safe_trash` / `safe_move` / `safe_copy` / `safe_rename`**: Implements non-destructive actions. `safe_trash` moves files to a designated `.smart_manager_trash` recovery staging area rather than invoking permanent deletion.
- **`find_duplicates`**: 2-pass duplicate discovery:
  1. Size grouping filter (`os.stat().st_size` > 0).
  2. SHA-256 chunked cryptographic hashing (64KB blocks) for size collisions.
- **`analyze_storage`**: Identifies storage reclaim opportunities:
  - Large files (> 50 MB)
  - Empty directories
  - Temporary and cache files (`.tmp`, `.log`, `.bak`, `.cache`, `~*`)
- **`file_preview`**: Provides safe text and code previews (up to 32KB) with syntax classification, preventing UI lockups on binary files.

### 3.2 Operation Ledger & Undo Engine (`backend/storage/history.py`)
Maintains an audit ledger in SQLite:
- Each batch execution is assigned an ISO timestamp and UUID `batch_id`.
- Records `src_path`, `dest_path`, `action_type`, and an `inverse_action` payload.
- `undo_last_operation()` reverses operations in inverse chronological order:
  - `move` $\rightarrow$ moves file back to original location.
  - `rename` $\rightarrow$ restores original filename.
  - `copy` $\rightarrow$ removes copied target file if unchanged.
  - `trash` $\rightarrow$ restores file from `.smart_manager_trash` to its original directory.

### 3.3 AI Planning Engine (`backend/agent/planner.py`)
Translates natural-language commands into structured file actions:
- **Online & Local Modes**: Works with local models (Ollama) or hosted endpoints (Groq, Cerebras, OpenAI).
- **Structured Schema**: Produces a `FilePlanPreview` consisting of `FileActionItem` items:
  ```json
  {
    "summary": "Organize 15 files into categorized folders",
    "target_directory": "C:\\Users\\User\\Downloads",
    "actions": [
      {
        "id": "act-1",
        "action_type": "move",
        "src_path": "C:\\Users\\User\\Downloads\\invoice.pdf",
        "dest_path": "C:\\Users\\User\\Downloads\\Documents\\invoice.pdf",
        "reason": "Categorize PDF as Document",
        "risk_level": "medium",
        "requires_approval": true
      }
    ],
    "skipped": [],
    "conflicts": [],
    "total_affected": 15,
    "requires_approval": true,
    "risk_level": "medium"
  }
  ```
- **Deterministic Rule-Based Fallback**: When an AI model is unavailable, offline, or slow, a built-in semantic rule planner handles common organization tasks (by extension, by date/year-month, or by cleanup patterns) with zero latency.

### 3.4 Security Policy (`backend/security/permissions.py`)
- **Path Traversal Shield**: Resolves relative segments (`..`, `~`) into canonical paths and rejects escapes outside allowed roots.
- **Protected Windows Directories**: Restricts operations targeting `C:\Windows`, `C:\Program Files`, `System32`, `Boot`, and user profile roots.
- **Independent Risk Evaluation**: The security policy calculates risk tiers (`LOW`, `MEDIUM`, `HIGH`) regardless of what the AI model suggests.

---

## 4. Frontend Subsystems

### 4.1 File Browser (`frontend/src/components/FileBrowser.jsx`)
- Interactive breadcrumbs with click-to-navigate path hierarchy.
- Switchable Grid and List layouts with file size, modified date, and category badge.
- Multi-selection with batch action toolbar (Copy, Move, Trash, Preview).
- Right-click context menu for quick file actions.
- Client-side search filter for instantaneous name matching.

### 4.2 AI Command Panel (`frontend/src/components/AiCommandPanel.jsx`)
- Prominent natural-language prompt bar with preconfigured action chips.
- Interactive plan preview displaying affected file counts, destination directories, and conflict warnings.
- Risk level badges (`LOW`, `MEDIUM`, `HIGH`) indicating required approval levels.
- One-click plan execution with real-time feedback.
- Instant single-click Undo button with badge indicating reversible operations.

### 4.3 Diagnostic Modals
- **File Preview Modal** (`FilePreviewModal.jsx`): In-memory viewer for text, markdown, JSON, and source files with open-with-OS launcher.
- **Duplicates Modal** (`DuplicatesModal.jsx`): Visual grouping of SHA-256 duplicate clusters with total wasted disk space calculation and selective trash options.
- **Storage Analysis Modal** (`StorageAnalysisModal.jsx`): Tabbed inspector for large files, empty folders, and temporary files with selective cleaning.

---

## 5. End-to-End Data Flow

```
User Prompt: "Organize Downloads by file type"
                   │
                   ▼
       [ Frontend AI Command Panel ]
                   │ POST /api/explorer/plan
                   ▼
         [ Backend AI Planner ]
        ├── Scans Downloads directory metadata
        ├── Evaluates file types & categorization
        └── Generates typed FilePlanPreview
                   │
                   ▼
         [ Security Policy Gate ]
        ├── Validates all source and target paths
        ├── Assigns deterministic risk rating
        └── Detects existing destination collisions
                   │
                   ▼
     [ Frontend Action Plan Preview ]
        ├── User reviews proposed moves
        └── User clicks "Approve & Execute"
                   │ POST /api/explorer/execute-plan
                   ▼
       [ Execution & Ledger Engine ]
        ├── Executes atomic filesystem operations
        ├── Writes records to `operation_history`
        └── Returns execution summary
                   │
                   ▼
       [ File Browser UI Updates ]
        ├── Automatically reloads directory contents
        └── Activates Undo banner
```
