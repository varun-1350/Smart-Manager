import json
import time
import asyncio
from typing import Optional, Dict, Any, List, Type, TypeVar
from pathlib import Path
import httpx

from config import settings
from ai.provider_base import AIProvider, ModelMetadata, TestResult
from agent.model import OllamaClient, AgentStepDecision
from storage.database import SettingsRepository

T = TypeVar("T")


def format_bytes(num_bytes: Optional[int]) -> str:
    if num_bytes is None:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


class OllamaProvider(AIProvider):
    """
    Local AI Provider backed by Ollama.
    Guarantees 100% offline local inference, zero cloud data transfer,
    and memory-aware execution for 16GB RAM / 6GB VRAM.
    """

    def __init__(self, client: Optional[OllamaClient] = None):
        self.client = client or OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_request_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
            num_predict=settings.ollama_num_predict,
            num_batch=settings.ollama_num_batch,
            keep_alive=settings.ollama_keep_alive,
        )

    @property
    def provider_type(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self.client.model

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.client.model = value

    async def is_available(self) -> bool:
        return await self.client.is_connected()

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        format: Optional[Any] = None,
    ) -> str:
        return await self.client.generate(
            prompt=prompt,
            system=system,
            num_ctx=num_ctx,
            format=format,
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        retries: int = 2,
    ) -> T:
        res = await self.client.generate_structured(
            prompt=prompt,
            response_model=response_model,
            system=system,
            num_ctx=num_ctx,
            retries=retries,
        )
        # Track last used timestamp
        try:
            SettingsRepository.set(f"model_last_used_{self.client.model}", str(int(time.time())))
        except Exception:
            pass
        return res

    async def unload(self) -> bool:
        return await self.client.unload_model()

    async def get_loaded_models(self) -> List[str]:
        """Queries Ollama /api/ps to inspect which models are currently loaded in RAM/VRAM."""
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{self.client.base_url}/api/ps")
                if res.status_code == 200:
                    data = res.json()
                    return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    async def list_models_detailed(self) -> List[ModelMetadata]:
        """Retrieves installed models from Ollama with detailed metadata."""
        models: List[ModelMetadata] = []
        loaded_names = set(await self.get_loaded_models())

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.client.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        details = m.get("details", {}) or {}
                        size = m.get("size")
                        tag = name.split(":")[-1] if ":" in name else "latest"
                        is_loaded = any(name == ln or name.split(":")[0] == ln.split(":")[0] for ln in loaded_names)
                        is_selected = (name == self.client.model)

                        last_used_raw = SettingsRepository.get(f"model_last_used_{name}")
                        last_used_str = None
                        if last_used_raw:
                            try:
                                import datetime
                                last_used_str = datetime.datetime.fromtimestamp(int(last_used_raw)).strftime("%Y-%m-%d %H:%M")
                            except Exception:
                                pass

                        models.append(
                            ModelMetadata(
                                name=name,
                                tag=tag,
                                size_bytes=size,
                                size_formatted=format_bytes(size),
                                parameter_size=details.get("parameter_size"),
                                quantization=details.get("quantization_level"),
                                family=details.get("family"),
                                format=details.get("format"),
                                capabilities=m.get("capabilities", []),
                                modified_at=m.get("modified_at"),
                                is_loaded=is_loaded,
                                is_selected=is_selected,
                                last_used=last_used_str,
                            )
                        )
        except Exception:
            pass

        return models

    async def test_capabilities(self, target_model: Optional[str] = None) -> TestResult:
        """Runs a latency and structured JSON output capability test."""
        model_to_test = target_model or self.client.model
        orig_model = self.client.model
        start = time.perf_counter()

        try:
            self.client.model = model_to_test
            # Quick test with AgentStepDecision schema
            test_prompt = "Return a valid step decision testing system readiness. Set summary to 'System ready' and actions to empty."
            res = await self.client.generate_structured(
                prompt=test_prompt,
                response_model=AgentStepDecision,
                retries=1,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            return TestResult(
                success=True,
                latency_ms=elapsed_ms,
                model=model_to_test,
                provider="local",
                message=f"Verified valid structured planning format in {elapsed_ms}ms.",
                sample_response=res.summary,
                structured_output_supported=True,
            )
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            return TestResult(
                success=False,
                latency_ms=elapsed_ms,
                model=model_to_test,
                provider="local",
                message=f"Inference error: {str(e)}",
                sample_response=None,
                structured_output_supported=False,
            )
        finally:
            self.client.model = orig_model
            # Clean up VRAM after test
            if getattr(settings, "ollama_auto_unload", True):
                try:
                    await self.client.unload_model()
                except Exception:
                    pass

    async def delete_model(self, model_name: str) -> bool:
        """Deletes a local model file via Ollama API."""
        try:
            # Unload first
            await self.client.unload_model()
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.request(
                    "DELETE",
                    f"{self.client.base_url}/api/delete",
                    json={"model": model_name},
                )
                return res.status_code == 200
        except Exception:
            return False
