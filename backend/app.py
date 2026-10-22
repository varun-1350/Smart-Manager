import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from storage.database import init_db
from storage.history import HistoryRepository
from agent.model import OllamaClient
from agent.runtime import AgentRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_manager.api")

app = FastAPI(
    title="Smart Manager API",
    description="Autonomous Local AI Agent for Windows",
    version="0.2.0",
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

# Shared Agent Runtime instance
ollama_client = OllamaClient(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    timeout_seconds=settings.ollama_request_timeout_seconds,
)
runtime = AgentRuntime(client=ollama_client)


class HealthResponse(BaseModel):
    status: str
    version: str
    ollama_connected: bool
    ollama_url: str
    active_model: str
    available_models: List[str]


class ConfigUpdateRequest(BaseModel):
    ollama_model: Optional[str] = None
    max_iterations: Optional[int] = None
    confirmation_required: Optional[bool] = None
    num_ctx: Optional[int] = None
    keep_alive: Optional[str] = None


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

    return HealthResponse(
        status="healthy",
        version="0.2.0",
        ollama_connected=ollama_connected,
        ollama_url=settings.ollama_base_url,
        active_model=ollama_client.model,
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
    if req.keep_alive:
        ollama_client.keep_alive = req.keep_alive
        settings.ollama_keep_alive = req.keep_alive
    return {"status": "updated", "config": await get_config()}


@app.post("/api/model/unload")
async def unload_model():
    success = await ollama_client.unload_model()
    return {
        "success": success,
        "message": "Model unloaded from GPU and RAM" if success else "Failed to signal unload to Ollama",
    }


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
        }

    except Exception as e:
        logger.exception("Error executing task")
        raise HTTPException(status_code=500, detail=str(e))
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

        final_response = context.final_result or context.error or "Action processed."

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


# Serve the production React bundle from the same local origin as the API.
# This keeps its absolute /assets paths and relative /api requests working in WebView2.
frontend_dir = settings.project_root / "frontend" / "dist"
if frontend_dir.is_dir() and (frontend_dir / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.smart_manager_host,
        port=settings.smart_manager_port,
        reload=settings.debug,
    )
