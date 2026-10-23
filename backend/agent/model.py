import json
import re
import asyncio
from typing import Dict, Any, List, Optional, Type, TypeVar, Literal
import httpx
import psutil
from pydantic import BaseModel, Field, model_validator

from config import settings

T = TypeVar("T", bound=BaseModel)

ToolName = Literal[
    "fs_list_dir",
    "fs_file_metadata",
    "fs_search_files",
    "fs_make_dir",
    "fs_write_text_file",
    "fs_copy_file",
    "fs_move_file",
    "fs_rename_file",
    "fs_delete_file",
    "fs_open_file",
    "fs_read_text_file",
    "fs_list_downloads",
    "proc_list",
    "proc_info",
    "proc_launch",
    "proc_kill",
    "sys_storage_info",
    "browser_search",
    "browser_open_url",
    "browser_play_youtube",
]


class ProposedAction(BaseModel):
    tool: ToolName = Field(description="Name of the approved operating system tool to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated parameters for the action")
    reasoning: str = Field(default="", description="Why this action is being taken at this step")


class AgentStepDecision(BaseModel):
    summary: str = Field(description="Summary of the agent's current understanding and plan")
    actions: List[ProposedAction] = Field(default_factory=list, description="List of proposed actions to execute in order")
    is_complete: bool = Field(default=False, description="Whether the user goal has been completely achieved and verified")
    final_answer: Optional[str] = Field(default=None, description="Final user-facing response if task is complete")
    clarification_question: Optional[str] = Field(default=None, description="Question for the user if request is ambiguous")

    @model_validator(mode="after")
    def infer_is_complete(self) -> "AgentStepDecision":
        if self.final_answer and not self.actions:
            self.is_complete = True
        return self


class OllamaClient:
    """
    Hardware-aware Ollama client for local language model inference.
    Enforces concurrency limits, configurable token context windows, batch limits,
    and automatic or on-demand VRAM unloading.
    """

    def __init__(
        self,
        base_url: str = settings.ollama_base_url,
        model: str = settings.ollama_model,
        timeout_seconds: float = settings.ollama_request_timeout_seconds,
        num_ctx: int = settings.ollama_num_ctx,
        num_predict: int = settings.ollama_num_predict,
        num_batch: int = settings.ollama_num_batch,
        keep_alive: str = settings.ollama_keep_alive,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.num_batch = num_batch
        self.keep_alive = keep_alive
        # Concurrency limit: strict single-model execution to protect 16GB RAM / 6GB VRAM
        self._semaphore = asyncio.Semaphore(settings.agent_max_parallel_tasks)

    async def is_connected(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    async def is_model_available(self, model_name: Optional[str] = None) -> bool:
        target = model_name or self.model
        models = await self.list_models()
        return any(target == m or target.split(":")[0] == m.split(":")[0] for m in models)

    async def unload_model(self) -> bool:
        """
        Explicitly unloads the current model from GPU VRAM and system memory
        by issuing an empty prompt with keep_alive: 0.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "keep_alive": 0},
                )
                return res.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        format: Optional[Any] = None,
        think: Optional[bool] = None,
    ) -> str:
        ctx_size = num_ctx or self.num_ctx

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": ctx_size,
                "num_predict": self.num_predict,
                "num_batch": self.num_batch,
                "temperature": 0.2,
            },
        }
        if format is not None:
            payload["format"] = format

        # Handle chain-of-thought thinking suppression to prevent token starvation
        think_flag = think if think is not None else getattr(settings, "ollama_think", False)
        payload["think"] = think_flag

        if system:
            payload["system"] = system

        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama error (HTTP {res.status_code}): {res.text}")
                data = res.json()
                return data.get("response", "").strip()

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        retries: int = 2,
    ) -> T:
        """
        Requests model generation and strictly validates the output against a Pydantic schema.
        Uses Ollama's grammar-constrained generation (format=schema) with think=False to prevent
        thinking tokens from consuming the token budget before JSON generation.
        """
        schema_dict = response_model.model_json_schema()
        schema_json = json.dumps(schema_dict, indent=2)
        system_instruction = (
            (system or "")
            + f"\n\nYou MUST respond ONLY with a valid JSON object matching this JSON Schema:\n{schema_json}\n"
            "Do NOT include markdown formatting or explanations outside the JSON."
        )

        use_schema_format = True

        for attempt in range(retries + 1):
            format_payload = schema_dict if use_schema_format else "json"
            try:
                raw_output = await self.generate(
                    prompt=prompt,
                    system=system_instruction,
                    num_ctx=num_ctx,
                    format=format_payload,
                    think=False,
                )
            except Exception as exc:
                # Fallback to format="json" if Ollama rejects grammar schema
                if use_schema_format and "format" in str(exc).lower():
                    use_schema_format = False
                    raw_output = await self.generate(
                        prompt=prompt,
                        system=system_instruction,
                        num_ctx=num_ctx,
                        format="json",
                        think=False,
                    )
                else:
                    raise

            cleaned_json = self._extract_json(raw_output)

            if cleaned_json:
                try:
                    parsed_dict = json.loads(cleaned_json)
                    validated = response_model.model_validate(parsed_dict)
                    return validated
                except Exception as e:
                    if attempt == retries:
                        raise ValueError(
                            f"Failed to validate model output against {response_model.__name__}: {e}\nRaw output: {raw_output}"
                        )
            elif attempt == retries:
                raise ValueError(f"Model output did not contain valid JSON.\nRaw output: {raw_output}")

            # Prompt correction for retry
            prompt = f"{prompt}\n\nNOTE: Your previous response was invalid. Return ONLY a valid JSON object matching the requested schema."

        raise RuntimeError("Failed to obtain valid structured output from Ollama")

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        return None
