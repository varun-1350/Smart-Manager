from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel
from typing import Dict, Any, List

from config import settings

app = FastAPI(
    title="Smart Manager API",
    description="Autonomous Local AI Agent for Windows",
    version="0.1.0",
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


class HealthResponse(BaseModel):
    status: str
    version: str
    ollama_connected: bool
    ollama_url: str
    active_model: str
    available_models: List[str]


class PingPromptRequest(BaseModel):
    prompt: str = "Hello, are you operational?"


class PingPromptResponse(BaseModel):
    success: bool
    model: str
    response: str
    total_duration_ms: float = 0.0


@app.get("/api/health", response_model=HealthResponse)
async def get_health():
    ollama_connected = False
    available_models: List[str] = []

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{settings.ollama_base_url}/api/tags")
            if res.status_code == 200:
                ollama_connected = True
                data = res.json()
                available_models = [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        ollama_connected = False

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        ollama_connected=ollama_connected,
        ollama_url=settings.ollama_base_url,
        active_model=settings.ollama_model,
        available_models=available_models,
    )


@app.get("/api/config")
async def get_config() -> Dict[str, Any]:
    return {
        "host": settings.smart_manager_host,
        "port": settings.smart_manager_port,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
        "max_iterations": settings.agent_max_iterations,
        "confirmation_required": settings.agent_default_confirmation_required,
    }


@app.post("/api/model/ping", response_model=PingPromptResponse)
async def ping_model(request: PingPromptRequest):
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_request_timeout_seconds) as client:
            payload = {
                "model": settings.ollama_model,
                "prompt": request.prompt,
                "stream": False,
            }
            res = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
            if res.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama returned HTTP {res.status_code}: {res.text}",
                )
            data = res.json()
            duration_ms = data.get("total_duration", 0) / 1_000_000.0
            return PingPromptResponse(
                success=True,
                model=settings.ollama_model,
                response=data.get("response", "").strip(),
                total_duration_ms=round(duration_ms, 2),
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Could not connect to local Ollama daemon.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.smart_manager_host,
        port=settings.smart_manager_port,
        reload=settings.debug,
    )
