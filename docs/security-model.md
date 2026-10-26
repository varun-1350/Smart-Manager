# Smart-Manager: Security & Threat Model

Smart-Manager operates on Windows with access to user files. Security is a primary design pillar. The application is designed to prevent AI hallucinations, prompt injections, or malformed requests from corrupting, stealing, or destroying user data.

---

## 1. Threat Model & Design Principles

### 1.1 Threat Vectors
1. **Model Hallucination & Prompt Injection:**
   An AI model might hallucinate dangerous paths (e.g. `C:\Windows\System32`), generate recursive delete commands, or be coerced via malicious filenames containing prompt injection payloads.
2. **Directory & Path Traversal Attacks:**
   Payloads attempting to break out of permitted folders using relative paths (`../../Windows`), encoded characters, or Windows junctions/symbolic links.
3. **Accidental Data Loss:**
   Bulk file reorganizations silently overwriting existing files with identical names, or moving files into inaccessible directories.
4. **Credential Theft:**
   External API keys (Groq, Cerebras, OpenAI) stored insecurely in plain text configuration files.
5. **Unauthorized Network Access:**
   Exposing local file manipulation endpoints to the local network or internet.

### 1.2 Core Security Invariants
- **Untrusted Model:** AI models generate *intent*, never *execution*. Model outputs are treated as untrusted user input.
- **Independent Security Gate:** Risk classification and path validation are performed deterministically by Python backend code, not by the model.
- **No Arbitrary Shell Execution:** The system uses explicit, parameterized Python filesystem APIs (`shutil.move`, `shutil.copy2`, `os.rename`, `os.scandir`). Model-generated shell commands (`cmd.exe`, `powershell.exe`, `bash`) are strictly prohibited and disabled in the tool dispatcher.
- **Fail-Safe Defaults:** If a path cannot be validated, an operation fails safely with a descriptive error without partial corruptions.
- **Reversible by Default:** Destructive actions default to a staging trash area with inverse undo capabilities.

---

## 2. Path Validation & Traversal Shield

All filesystem operations pass through `SecurityPolicy.validate_target_path()` and `SecurityPolicy.validate_file_explorer_path()` in `backend/security/permissions.py`.

```
Target Path Input ──► [ Path Normalization & Canonicalization ]
                             │
                             ├──► Check for Path Traversal (`..`, `~`)
                             │
                             ├──► Check Protected Windows Directories
                             │    (Windows, System32, Program Files, Boot)
                             │
                             ├──► Check Allowed Scope Roots
                             │
                             └──► Success / ValidationError
```

### 2.1 Canonical Path Resolution
Paths are resolved using `pathlib.Path.resolve()`, stripping redundant separators, resolving relative segments (`.`, `..`), and canonicalizing drive letters. If the resolved path attempts to step outside the target or allowed boundaries, the operation is rejected.

### 2.2 Protected Windows Directories
Operations targeting critical operating system directories are blocked unconditionally:
- `C:\Windows` (including `System32`, `SysWOW64`, `WinSxS`)
- `C:\Program Files` and `C:\Program Files (x86)`
- `C:\ProgramData`
- Root system partitions (e.g. direct modification of `C:\` root)
- System boot files (`bootmgr`, `pagefile.sys`, `hiberfil.sys`)

---

## 3. Risk-Based Approval Matrix

The backend `SecurityPolicy` assigns risk tiers to operations deterministically:

| Operation Type | Risk Level | Description | Approval Policy |
| :--- | :--- | :--- | :--- |
| `fs_browse_dir`, `fs_list_dir` | **LOW** | Read folder directory listing | Automatic (No prompt) |
| `fs_read_file`, `fs_file_preview` | **LOW** | Read file content preview (<=32KB) | Automatic (No prompt) |
| `fs_find_duplicates` | **LOW** | Size & SHA-256 content hashing | Automatic (No prompt) |
| `fs_storage_analysis` | **LOW** | Scan folder for size & empty dirs | Automatic (No prompt) |
| `fs_create_folder` | **MEDIUM** | Create a new directory | Approval required via plan |
| `fs_move_files` | **MEDIUM** | Relocate files between directories | Approval required via plan |
| `fs_copy_files` | **MEDIUM** | Duplicate files to target | Approval required via plan |
| `fs_rename_file` | **MEDIUM** | Rename an existing file | Approval required via plan |
| `fs_trash_files` | **HIGH** | Move files to staging trash | Explicit confirmation required |
| Shell Execution | **CRITICAL** | Executing arbitrary commands | **Blocked unconditionally** |

### 3.1 Untrusted Model Risk Ratings
If an AI model proposes an action and marks it as `risk_level: "low"` or `requires_approval: false`, the backend overrides those values:
```python
# Model output is untrusted. Security policy computes actual risk tier:
action.risk_level = security_policy.calculate_risk(action.action_type)
action.requires_approval = action.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
```

---

## 4. Reversible Trash & Overwrite Defense

### 4.1 Reversible Trash Architecture
Rather than calling permanent deletion APIs (`os.remove`, `shutil.rmtree`), Smart-Manager implements `safe_trash`:
1. Creates a local staging trash folder: `<parent_folder>\.smart_manager_trash`.
2. Appends an ISO timestamp to avoid collisions: `original_name.20261026_224500.trashed`.
3. Stores the original path and restore location in the SQLite `operation_history` table.
4. When the user clicks **Undo**, the file is cleanly restored to its original path.

### 4.2 Overwrite Prevention
When moving or copying files:
1. `dest_path` existence is checked before execution.
2. If the destination exists, the planner marks the file with a `conflict` flag.
3. If executed with collision avoidance, a counter is appended (`filename (1).ext`) rather than silently clobbering existing user files.

---

## 5. Network & Credential Security

1. **Loopback Binding Only:**
   The FastAPI server binds strictly to `127.0.0.1` (`localhost`). It does not bind to `0.0.0.0` or open external listening interfaces.
2. **CORS Isolation:**
   Cross-Origin Resource Sharing is locked down to the local frontend Vite dev/production origin.
3. **Windows DPAPI Credential Storage:**
   External API keys (Groq, Cerebras, OpenAI) are encrypted at rest using Windows Data Protection API (`CryptProtectData`). Only the current logged-in Windows user account can decrypt the saved keys.
4. **Local-First Privacy:**
   File content and directory trees are never sent to external cloud APIs by default. File categorization and organization run locally or against local Ollama models.
