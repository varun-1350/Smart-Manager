import time
import logging
import sqlite3
from typing import Dict, Any, List, Optional
from pathlib import Path
import httpx
import sys
import secrets
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import settings
from storage.database import init_db, SettingsRepository
from storage.history import HistoryRepository, OperationHistoryRepository
from storage.tasks import TaskRepository
from security.credentials import CredentialVault
from security.permissions import SecurityPolicy
from execution.filesystem import FilesystemOperations, resolve_system_path
from ai import ProviderManager, OllamaProvider, OnlineProvider
from agent.model import OllamaClient, FilePlanPreview, FileActionItem
from agent.planner import Planner
from agent.runtime import AgentRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_manager.api")

app = FastAPI(
    title="Smart Manager API",
    description="Autonomous Local AI Agent for Windows",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Smart-Manager-Session"],
)

# Initialize database schema
init_db()
interrupted_task_count = TaskRepository.reconcile_interrupted()
if interrupted_task_count:
    logger.warning("Marked %s unfinished task(s) interrupted after backend restart", interrupted_task_count)

# Persistent model selection restoration
persisted_local_model = SettingsRepository.get("selected_local_model", settings.ollama_model)
if persisted_local_model:
    settings.ollama_model = persisted_local_model

# Shared Agent Runtime & Provider Manager instance
ollama_client = OllamaClient(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    timeout_seconds=settings.ollama_request_timeout_seconds,
)
ollama_provider = OllamaProvider(client=ollama_client)
provider_manager = ProviderManager(ollama_provider=ollama_provider)
runtime = AgentRuntime(client=ollama_client, provider_manager=provider_manager)


@app.middleware("http")
async def require_desktop_session(request: Request, call_next):
    """Require the per-launch desktop secret when packaged mode configures one."""
    expected = settings.api_session_secret
    if expected and request.url.path.startswith("/api/"):
        supplied = request.headers.get("X-Smart-Manager-Session", "")
        if not secrets.compare_digest(supplied, expected):
            return JSONResponse(status_code=401, content={"detail": "Desktop session authentication required."})
    return await call_next(request)


class HealthResponse(BaseModel):
    status: str
    version: str
    ollama_connected: bool
    ollama_url: str
    active_model: str
    provider_mode: str
    active_provider_label: str
    available_models: List[str]


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ollama_model: Optional[str] = None
    max_iterations: Optional[int] = Field(default=None, ge=1, le=100)
    confirmation_required: Optional[bool] = None
    num_ctx: Optional[int] = Field(default=None, ge=256, le=131_072)
    num_predict: Optional[int] = Field(default=None, ge=1, le=16_384)
    keep_alive: Optional[str] = Field(default=None, min_length=1, max_length=32)
    auto_unload: Optional[bool] = None


@app.get("/api/health", response_model=HealthResponse)
async def get_health():
    ollama_connected = False
    available_models: List[str] = []

    try:
        models = await ollama_client.list_models()
        if models is not None:
            ollama_connected = True
            available_models = models
    except Exception:
        ollama_connected = False

    active_prov, active_label = await provider_manager.get_active_provider()

    return HealthResponse(
        status="healthy",
        version="0.4.0",
        ollama_connected=ollama_connected,
        ollama_url=settings.ollama_base_url,
        active_model=active_prov.model_name,
        provider_mode=provider_manager.mode,
        active_provider_label=active_label,
        available_models=available_models,
    )


@app.get("/api/config")
async def get_config() -> Dict[str, Any]:
    return {
        "host": settings.smart_manager_host,
        "port": settings.smart_manager_port,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": ollama_client.model,
        "max_iterations": settings.agent_max_iterations,
        "confirmation_required": settings.agent_default_confirmation_required,
        "num_ctx": ollama_client.num_ctx,
        "keep_alive": ollama_client.keep_alive,
        "num_predict": ollama_client.num_predict,
        "auto_unload": getattr(settings, "ollama_auto_unload", True),
    }


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest) -> Dict[str, Any]:
    if req.ollama_model is not None:
        model = req.ollama_model.strip()
        if not model:
            raise HTTPException(status_code=422, detail="Model name cannot be empty.")
        ollama_client.model = model
        settings.ollama_model = model
        SettingsRepository.set("selected_local_model", model)
    if req.max_iterations is not None:
        settings.agent_max_iterations = req.max_iterations
    if req.confirmation_required is not None:
        settings.agent_default_confirmation_required = req.confirmation_required
    if req.num_ctx is not None:
        ollama_client.num_ctx = req.num_ctx
        settings.ollama_num_ctx = req.num_ctx
    if req.num_predict is not None:
        ollama_client.num_predict = req.num_predict
        settings.ollama_num_predict = req.num_predict
    if req.keep_alive is not None:
        ollama_client.keep_alive = req.keep_alive.strip()
        settings.ollama_keep_alive = req.keep_alive.strip()
    if req.auto_unload is not None:
        settings.ollama_auto_unload = req.auto_unload

    return {"status": "updated", "config": await get_config()}


@app.post("/api/model/unload")
async def unload_model():
    success = await provider_manager.local_provider.unload()
    return {
        "success": success,
        "message": "Model unloaded from GPU and RAM" if success else "Failed to signal unload to Ollama",
    }


class ModelSelectRequest(BaseModel):
    model: str


class ModelAddRequest(BaseModel):
    provider: str
    model: str
    api_key: str
    base_url: Optional[str] = None


class ModelPullRequest(BaseModel):
    model: str


class ModelTestRequest(BaseModel):
    model: Optional[str] = None
    provider: Optional[str] = "local"


class ProviderConfigRequest(BaseModel):
    mode: Optional[str] = None
    auto_fallback_to_online: Optional[bool] = None
    auto_fallback_to_local: Optional[bool] = None
    online_authorized: Optional[bool] = None
    online_base_url: Optional[str] = None
    online_model: Optional[str] = None
    online_api_key: Optional[str] = None


@app.get("/api/models")
async def list_models() -> List[Dict[str, Any]]:
    models = await provider_manager.list_all_models()
    return [m.model_dump() for m in models]


@app.post("/api/models/select")
async def select_model(req: ModelSelectRequest):
    try:
        selected_id = await provider_manager.select_model(req.model)
        return {
            "success": True,
            "selected_model": selected_id,
            "message": f"Active model switched to '{selected_id}'.",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/models/add")
async def add_model(req: ModelAddRequest):
    try:
        entry = provider_manager.add_online_model(
            provider=req.provider,
            model_name=req.model,
            api_key=req.api_key,
            base_url=req.base_url,
        )
        return {"success": True, "model": entry}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/models/pull")
async def pull_model(req: ModelPullRequest):
    try:
        res = await provider_manager.start_pull_model(req.model)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/models/pull/{model_name:path}/status")
async def get_pull_status(model_name: str):
    status = provider_manager.get_pull_status(model_name)
    if not status:
        raise HTTPException(status_code=404, detail=f"No download active for model '{model_name}'.")
    return status


@app.post("/api/models/pull/{model_name:path}/cancel")
async def cancel_pull(model_name: str):
    cancelled = provider_manager.cancel_pull(model_name)
    return {"success": cancelled, "model": model_name}


@app.delete("/api/models/{model_name:path}")
async def delete_model(model_name: str):
    try:
        success = await provider_manager.remove_model(model_name)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete model '{model_name}'.")
        return {"success": True, "deleted_model": model_name}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/models/test")
async def test_model(req: ModelTestRequest):
    try:
        res = await provider_manager.test_model(req.model)
        return res.model_dump()
    except Exception as e:
        return {
            "success": False,
            "latency_ms": 0.0,
            "model": req.model or "unknown",
            "provider": req.provider or "unknown",
            "message": f"Test failed: {str(e)}",
            "structured_output_supported": False,
        }


@app.get("/api/providers")
async def get_providers_info():
    active_prov, active_label = await provider_manager.get_active_provider()
    has_key = CredentialVault.has_secret("online_api_key")
    masked_key = CredentialVault.mask_secret(CredentialVault.get_secret("online_api_key")) if has_key else ""

    return {
        "mode": provider_manager.mode,
        "active_provider_label": active_label,
        "active_model": active_prov.model_name,
        "auto_fallback_to_online": provider_manager.auto_fallback_to_online,
        "auto_fallback_to_local": provider_manager.auto_fallback_to_local,
        "online_authorized": provider_manager.online_authorized,
        "online_base_url": provider_manager.online_provider.base_url,
        "online_model": provider_manager.online_provider.model_name,
        "has_online_api_key": has_key,
        "online_api_key_masked": masked_key,
    }


@app.post("/api/providers")
async def update_providers_info(req: ProviderConfigRequest):
    try:
        if req.mode is not None:
            provider_manager.set_mode(req.mode)
        if req.auto_fallback_to_online is not None:
            provider_manager.set_auto_fallback_to_online(req.auto_fallback_to_online)
        if req.auto_fallback_to_local is not None:
            provider_manager.set_auto_fallback_to_local(req.auto_fallback_to_local)
        if req.online_authorized is not None:
            provider_manager.set_online_authorized(req.online_authorized)
        if req.online_base_url is not None:
            provider_manager.online_provider.base_url = req.online_base_url
        if req.online_model is not None:
            provider_manager.online_provider.model_name = req.online_model
        if req.online_api_key is not None:
            if req.online_api_key.strip():
                CredentialVault.set_secret("online_api_key", req.online_api_key.strip())
            else:
                CredentialVault.delete_secret("online_api_key")

        return {"status": "updated", "providers": await get_providers_info()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.get("/api/system/resources")
async def get_system_resources():
    import psutil
    import subprocess

    vm = psutil.virtual_memory()

    # Relevant AI & python process memory
    proc_info = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = p.info["name"].lower()
            if any(k in name for k in ["python", "ollama", "llama"]):
                mem_mb = round(p.info["memory_info"].rss / (1024 * 1024), 2)
                proc_info.append({"pid": p.info["pid"], "name": p.info["name"], "memory_mb": mem_mb})
        except Exception:
            continue

    # GPU VRAM inspection via nvidia-smi
    gpu_info = None
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 4:
                gpu_info = {
                    "vram_total_mb": float(parts[0]),
                    "vram_used_mb": float(parts[1]),
                    "vram_free_mb": float(parts[2]),
                    "gpu_util_percent": float(parts[3]),
                }
    except Exception:
        gpu_info = None

    return {
        "system_ram": {
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "used_gb": round(vm.used / (1024**3), 2),
            "percent": vm.percent,
        },
        "gpu_vram": gpu_info,
        "ai_processes": proc_info,
        "active_settings": {
            "model": ollama_client.model,
            "num_ctx": ollama_client.num_ctx,
            "keep_alive": ollama_client.keep_alive,
            "num_predict": ollama_client.num_predict,
        },
    }


@app.get("/api/conversations")
async def get_conversations():
    return HistoryRepository.list_conversations()


@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    return HistoryRepository.get_messages(conv_id)


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = TaskRepository.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task, "events": TaskRepository.events(task_id)}


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    deleted = HistoryRepository.delete_conversation(conv_id)
    return {"success": True, "conversation_id": conv_id, "deleted": deleted}


@app.delete("/api/conversations")
async def clear_all_conversations():
    HistoryRepository.clear_all_conversations()
    return {"success": True, "message": "All conversations cleared"}


# ============================================================================
# File Explorer Core APIs
# ============================================================================

@app.get("/api/explorer/locations")
async def get_explorer_locations():
    return FilesystemOperations.get_quick_locations()


@app.get("/api/explorer/browse")
async def browse_explorer(
    path: Optional[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    show_hidden: bool = False,
    limit: int = 500,
    offset: int = 0,
):
    try:
        return FilesystemOperations.browse_directory(
            path=path,
            sort_by=sort_by,
            sort_order=sort_order,
            show_hidden=show_hidden,
            limit=limit,
            offset=offset,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/explorer/preview")
async def preview_explorer_file(path: str):
    try:
        return FilesystemOperations.file_preview(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ExplorerActionRequest(BaseModel):
    action: str = Field(description="Action: mkdir, rename, trash, move, copy, open")
    path: Optional[str] = None
    paths: Optional[List[str]] = None
    new_name: Optional[str] = None
    destination: Optional[str] = None
    folder_name: Optional[str] = None


@app.post("/api/explorer/action")
async def handle_explorer_action(req: ExplorerActionRequest):
    try:
        action = req.action.lower()
        if action == "mkdir":
            if not req.path or not req.folder_name:
                raise HTTPException(status_code=400, detail="path and folder_name required for mkdir")
            target = str(Path(req.path) / req.folder_name)
            perm = SecurityPolicy.evaluate_action("fs_make_dir", {"path": target})
            if not perm.allowed:
                raise HTTPException(status_code=403, detail=perm.reason)
            return FilesystemOperations.make_dir(target)

        elif action == "rename":
            if not req.path or not req.new_name:
                raise HTTPException(status_code=400, detail="path and new_name required for rename")
            perm = SecurityPolicy.evaluate_action("fs_rename_file", {"path": req.path, "new_name": req.new_name})
            if not perm.allowed:
                raise HTTPException(status_code=403, detail=perm.reason)
            return FilesystemOperations.safe_rename(req.path, req.new_name)

        elif action == "trash":
            targets = req.paths or ([req.path] if req.path else [])
            if not targets:
                raise HTTPException(status_code=400, detail="paths required for trash")
            perm = SecurityPolicy.evaluate_action("fs_trash_files", {"paths": targets})
            if not perm.allowed:
                raise HTTPException(status_code=403, detail=perm.reason)
            return FilesystemOperations.safe_trash(targets)

        elif action == "move":
            targets = req.paths or ([req.path] if req.path else [])
            if not targets or not req.destination:
                raise HTTPException(status_code=400, detail="paths and destination required for move")
            perm = SecurityPolicy.evaluate_action("fs_move_files", {"src_paths": targets, "dest_folder": req.destination})
            if not perm.allowed:
                raise HTTPException(status_code=403, detail=perm.reason)
            return FilesystemOperations.safe_move(targets, req.destination)

        elif action == "copy":
            targets = req.paths or ([req.path] if req.path else [])
            if not targets or not req.destination:
                raise HTTPException(status_code=400, detail="paths and destination required for copy")
            perm = SecurityPolicy.evaluate_action("fs_copy_files", {"src_paths": targets, "dest_folder": req.destination})
            if not perm.allowed:
                raise HTTPException(status_code=403, detail=perm.reason)
            return FilesystemOperations.safe_copy(targets, req.destination)

        elif action == "open":
            if not req.path:
                raise HTTPException(status_code=400, detail="path required to open")
            return FilesystemOperations.open_file(req.path)

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported explorer action: '{req.action}'")

    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        logger.exception("Error in explorer action")
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/explorer/duplicates")
async def get_explorer_duplicates(folder: str, min_size: int = 1024):
    try:
        return FilesystemOperations.find_duplicates(folder, min_size_bytes=min_size)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/explorer/storage-analysis")
async def get_explorer_storage_analysis(folder: str):
    try:
        return FilesystemOperations.analyze_storage(folder)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ExplorerPlanRequest(BaseModel):
    folder_path: str = Field(min_length=1)
    instruction: str = Field(min_length=1, max_length=5000)


@app.post("/api/explorer/plan")
async def generate_explorer_plan(req: ExplorerPlanRequest):
    req_id = f"plan-{uuid4().hex[:8]}"
    start_time = time.perf_counter()
    logger.info(f"[{req_id}] Explorer plan requested: path='{req.folder_path}', instruction='{req.instruction[:80]}'")

    # Validate target directory
    target = resolve_system_path(req.folder_path)
    if not target.exists():
        logger.warning(f"[{req_id}] Folder not found: {req.folder_path}")
        raise HTTPException(status_code=404, detail=f"Directory does not exist: {req.folder_path}")
    if not target.is_dir():
        logger.warning(f"[{req_id}] Target is not a directory: {req.folder_path}")
        raise HTTPException(status_code=400, detail=f"Target path is not a directory: {req.folder_path}")

    # Resolve active AI provider dynamically
    try:
        active_provider, provider_label = await provider_manager.get_active_provider()
    except Exception as e:
        logger.error(f"[{req_id}] Failed to get active provider: {e}")
        raise HTTPException(status_code=503, detail=f"AI Provider unavailable: {str(e)}")

    if not provider_manager.provider_available_for_task(provider_label):
        logger.warning(f"[{req_id}] Provider '{provider_label}' unavailable due to circuit breaker")
        raise HTTPException(
            status_code=503,
            detail=f"AI Provider '{provider_label}' is temporarily unavailable. Please verify API key or settings.",
        )

    try:
        planner = Planner(active_provider)
        runtime.planner = planner
        plan = await planner.plan_file_batch_task(
            folder_path=str(target),
            instruction=req.instruction,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[{req_id}] Explorer plan generated in {elapsed_ms:.1f}ms: {len(plan.actions)} action(s)")
        return plan.model_dump()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(f"[{req_id}] Error generating explorer plan in {elapsed_ms:.1f}ms")
        raise HTTPException(status_code=500, detail=f"Plan generation failed: {str(e)}")


class ExplorerExecutePlanRequest(BaseModel):
    batch_id: str
    actions: List[Dict[str, Any]]


@app.post("/api/explorer/execute-plan")
async def execute_explorer_plan(req: ExplorerExecutePlanRequest):
    executed = []
    errors = []
    for item in req.actions:
        tool = item.get("tool")
        src = item.get("source")
        dst = item.get("destination")
        try:
            if tool in ("fs_move_file", "fs_move_files"):
                res = FilesystemOperations.safe_move([src], str(Path(dst).parent), batch_id=req.batch_id)
                executed.append({"tool": tool, "source": src, "destination": dst, "success": True})
            elif tool in ("fs_copy_file", "fs_copy_files"):
                res = FilesystemOperations.safe_copy([src], str(Path(dst).parent), batch_id=req.batch_id)
                executed.append({"tool": tool, "source": src, "destination": dst, "success": True})
            elif tool in ("fs_trash_files", "fs_delete_file"):
                res = FilesystemOperations.safe_trash([src], batch_id=req.batch_id)
                executed.append({"tool": tool, "source": src, "success": True})
            elif tool == "fs_rename_file":
                res = FilesystemOperations.safe_rename(src, Path(dst).name, batch_id=req.batch_id)
                executed.append({"tool": tool, "source": src, "new_name": Path(dst).name, "success": True})
        except Exception as e:
            errors.append({"action": item, "error": str(e)})

    return {
        "batch_id": req.batch_id,
        "executed_count": len(executed),
        "executed": executed,
        "errors": errors,
        "success": len(errors) == 0,
    }


@app.post("/api/explorer/undo")
async def undo_explorer_last_operation():
    return FilesystemOperations.undo_last_operation()


@app.get("/api/explorer/history")
async def get_explorer_operation_history(limit: int = 15):
    return OperationHistoryRepository.list_recent_batches(limit=limit)


class PingPromptRequest(BaseModel):
    prompt: str = "Hello, are you operational?"


class PingPromptResponse(BaseModel):
    success: bool
    model: str
    response: str
    total_duration_ms: float = 0.0


class TaskExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    prompt: str = Field(min_length=1, max_length=20_000)
    conversation_id: str = Field(default="default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class TaskApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    approved: bool
    approval_token: str = Field(min_length=32, max_length=256)


@app.post("/api/task/execute")
async def execute_task(req: TaskExecuteRequest):
    try:
        TaskRepository.create(req.task_id, req.conversation_id, req.prompt)
        # Record user message in local history
        HistoryRepository.create_or_update_conversation(
            req.conversation_id,
            req.prompt[:32],
        )
        HistoryRepository.save_message(
            msg_id=f"user-{req.task_id}",
            conversation_id=req.conversation_id,
            role="user",
            content=req.prompt,
        )

        # Run autonomous agent loop
        TaskRepository.transition(req.task_id, "planning")
        context = await runtime.run_task(
            task_id=req.task_id,
            goal=req.prompt,
            conversation_id=req.conversation_id,
        )

        # Log actions in local SQLite database
        all_actions = []
        for step in context.history:
            for obs in step.observations:
                all_actions.append(obs.model_dump())
                HistoryRepository.log_action(
                    task_id=req.task_id,
                    conversation_id=req.conversation_id,
                    tool=obs.tool,
                    parameters=obs.parameters,
                    success=obs.success,
                    result=obs.result,
                    error=obs.error,
                    duration_ms=obs.duration_ms,
                    verified=obs.verified,
                )
                TaskRepository.record_action(req.task_id, obs.model_dump())

        final_response = (
            context.final_result
            or context.error
            or (
                "Approval is required before I can continue."
                if context.status == "waiting_approval"
                else "Task completed."
            )
        )

        # Save agent response in history
        HistoryRepository.save_message(
            msg_id=f"agent-{req.task_id}",
            conversation_id=req.conversation_id,
            role="agent",
            content=final_response,
            status=context.status,
        )

        ledger_status = "awaiting_approval" if context.status == "waiting_approval" else context.status
        TaskRepository.transition(
            context.task_id,
            ledger_status,
            provider=context.provider,
            result=context.final_result,
            error=context.error,
            event_payload={"iterations": context.iteration},
        )

        plan_summary = (
            context.history[-1].thought_summary
            if context.history
            else "Task execution plan"
        )

        return {
            "task_id": context.task_id,
            "status": context.status,
            "response": final_response,
            "plan": {"summary": plan_summary},
            "actions": all_actions,
            "pending_approval": context.pending_approval,
            "iterations": context.iteration,
            "provider": context.provider or f"local:{provider_manager.local_provider.model_name}",
        }

    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Task identifier already exists.")
    except Exception as e:
        logger.exception("Error executing task")
        try:
            TaskRepository.transition(req.task_id, "failed", error=str(e))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Minimal RAM guarantee: unload model from GPU VRAM and process RAM when idle
        if getattr(settings, "ollama_auto_unload", True):
            try:
                await provider_manager.local_provider.unload()
            except Exception:
                pass


class TaskStopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@app.post("/api/task/stop")
async def stop_task(req: TaskStopRequest):
    stopped = runtime.cancel_task(req.task_id)
    # Immediately release llama-server RAM
    try:
        await provider_manager.local_provider.unload()
    except Exception:
        pass
    if stopped:
        TaskRepository.transition(req.task_id, "cancelled", event_payload={"reason": "user_stop"})
    return {"success": True, "task_id": req.task_id, "stopped": stopped}


@app.post("/api/task/approve")
async def approve_task(req: TaskApprovalRequest):
    try:
        context = await runtime.resume_task_approval(
            task_id=req.task_id,
            approved=req.approved,
            approval_token=req.approval_token,
        )

        all_actions = []
        for step in context.history:
            for obs in step.observations:
                all_actions.append(obs.model_dump())

        # The initial execute endpoint logs only the proposal that paused for
        # approval. Persist the resulting approved action as well so history
        # reflects what actually happened on the machine.
        approved_observation = next(
            (
                obs
                for step in reversed(context.history)
                for obs in reversed(step.observations)
                if obs.tool in {"fs_delete_file", "proc_kill", "fs_write_text_file", "fs_copy_file", "fs_move_file", "fs_rename_file", "fs_make_dir", "proc_launch"}
                and "WAITING_APPROVAL" not in (obs.error or "")
            ),
            None,
        )
        if approved_observation:
            HistoryRepository.log_action(
                task_id=context.task_id,
                conversation_id=context.conversation_id,
                tool=approved_observation.tool,
                parameters=approved_observation.parameters,
                success=approved_observation.success,
                result=approved_observation.result,
                error=approved_observation.error,
                duration_ms=approved_observation.duration_ms,
                verified=approved_observation.verified,
            )
            TaskRepository.record_action(context.task_id, approved_observation.model_dump())

        final_response = context.final_result or context.error or (
            "Approved action completed and was verified."
            if approved_observation and approved_observation.success and approved_observation.verified
            else "Approved action processed."
        )

        # Approval responses are separate agent turns. Persist them so a reload
        # does not erase the outcome of a destructive action.
        HistoryRepository.save_message(
            msg_id=f"agent-approval-{uuid4()}",
            conversation_id=context.conversation_id,
            role="agent",
            content=final_response,
            status=context.status,
        )
        ledger_status = "awaiting_approval" if context.status == "waiting_approval" else context.status
        TaskRepository.transition(
            context.task_id,
            ledger_status,
            provider=context.provider,
            result=context.final_result,
            error=context.error,
        )

        return {
            "task_id": context.task_id,
            "status": context.status,
            "response": final_response,
            "actions": all_actions,
            "pending_approval": context.pending_approval,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found or not waiting for approval")
    except Exception as e:
        logger.exception("Error handling approval")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/model/ping", response_model=PingPromptResponse)
async def ping_model(request: PingPromptRequest):
    try:
        start_time = httpx.Timeout(settings.ollama_request_timeout_seconds)
        response_text = await ollama_client.generate(request.prompt)
        return PingPromptResponse(
            success=True,
            model=ollama_client.model,
            response=response_text,
            total_duration_ms=0.0,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_frontend_dist() -> Optional[Path]:
    p1 = settings.project_root / "frontend" / "dist"
    if p1.exists() and (p1 / "index.html").exists():
        return p1
    if hasattr(sys, "_MEIPASS"):
        p2 = Path(getattr(sys, "_MEIPASS")) / "frontend" / "dist"
        if p2.exists() and (p2 / "index.html").exists():
            return p2
    return None


frontend_dir = get_frontend_dist()
if frontend_dir:
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.smart_manager_host,
        port=settings.smart_manager_port,
        reload=settings.debug,
    )
