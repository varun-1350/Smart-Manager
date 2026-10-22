import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import httpx
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from storage.database import init_db, SettingsRepository
from storage.history import HistoryRepository
from security.credentials import CredentialVault
from ai import ProviderManager, OllamaProvider, OnlineProvider
from agent.model import OllamaClient
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database schema
init_db()

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
    ollama_model: Optional[str] = None
    max_iterations: Optional[int] = None
    confirmation_required: Optional[bool] = None
    num_ctx: Optional[int] = None
    num_predict: Optional[int] = None
    keep_alive: Optional[str] = None
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
    if req.ollama_model:
        ollama_client.model = req.ollama_model
        settings.ollama_model = req.ollama_model
    if req.max_iterations:
        settings.agent_max_iterations = req.max_iterations
    if req.confirmation_required is not None:
        settings.agent_default_confirmation_required = req.confirmation_required
    if req.num_ctx:
        ollama_client.num_ctx = req.num_ctx
        settings.ollama_num_ctx = req.num_ctx
    if req.num_predict:
        ollama_client.num_predict = req.num_predict
        settings.ollama_num_predict = req.num_predict
    if req.keep_alive:
        ollama_client.keep_alive = req.keep_alive
        settings.ollama_keep_alive = req.keep_alive
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


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    deleted = HistoryRepository.delete_conversation(conv_id)
    return {"success": True, "conversation_id": conv_id, "deleted": deleted}


@app.delete("/api/conversations")
async def clear_all_conversations():
    HistoryRepository.clear_all_conversations()
    return {"success": True, "message": "All conversations cleared"}


class PingPromptRequest(BaseModel):
    prompt: str = "Hello, are you operational?"


class PingPromptResponse(BaseModel):
    success: bool
    model: str
    response: str
    total_duration_ms: float = 0.0


class TaskExecuteRequest(BaseModel):
    task_id: str
    prompt: str
    conversation_id: str = "default"


class TaskApprovalRequest(BaseModel):
    task_id: str
    approved: bool


@app.post("/api/task/execute")
async def execute_task(req: TaskExecuteRequest):
    try:
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

    except Exception as e:
        logger.exception("Error executing task")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Minimal RAM guarantee: unload model from GPU VRAM and process RAM when idle
        if getattr(settings, "ollama_auto_unload", True):
            try:
                await provider_manager.local_provider.unload()
            except Exception:
                pass


class TaskStopRequest(BaseModel):
    task_id: str


@app.post("/api/task/stop")
async def stop_task(req: TaskStopRequest):
    stopped = runtime.cancel_task(req.task_id)
    # Immediately release llama-server RAM
    try:
        await provider_manager.local_provider.unload()
    except Exception:
        pass
    return {"success": True, "task_id": req.task_id, "stopped": stopped}


@app.post("/api/task/approve")
async def approve_task(req: TaskApprovalRequest):
    try:
        context = await runtime.resume_task_approval(
            task_id=req.task_id,
            approved=req.approved,
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
                if obs.tool in {"fs_delete_file", "proc_kill", "shell_run_command"}
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

        final_response = context.final_result or context.error or (
            "Approved action completed and was verified."
            if approved_observation and approved_observation.success and approved_observation.verified
            else "Approved action processed."
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
