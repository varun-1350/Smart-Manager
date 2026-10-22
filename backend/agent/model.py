import json
import re
from typing import Dict, Any, List, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel, Field

from config import settings

T = TypeVar("T", bound=BaseModel)


class ProposedAction(BaseModel):
    tool: str = Field(description="Name of the approved operating system tool to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated parameters for the action")
    reasoning: str = Field(default="", description="Why this action is being taken at this step")


class AgentStepDecision(BaseModel):
    summary: str = Field(description="Summary of the agent's current understanding and plan")
    actions: List[ProposedAction] = Field(default_factory=list, description="List of proposed actions to execute in order")
    is_complete: bool = Field(default=False, description="Whether the user goal has been completely achieved and verified")
    final_answer: Optional[str] = Field(default=None, description="Final user-facing response if task is complete")
    clarification_question: Optional[str] = Field(default=None, description="Question for the user if request is ambiguous")


class OllamaClient:
    def __init__(
        self,
        base_url: str = settings.ollama_base_url,
        model: str = settings.ollama_model,
        timeout_seconds: float = settings.ollama_request_timeout_seconds,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

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
        # Check both exact match and without tag prefix/suffix
        return any(target == m or target.split(":")[0] == m.split(":")[0] for m in models)

    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

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
        retries: int = 2,
    ) -> T:
        """
        Requests model generation and strictly validates the output against a Pydantic schema.
        Handles JSON extraction, cleaning, and retry on malformed outputs.
        """
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        system_instruction = (
            (system or "")
            + f"\n\nYou MUST respond ONLY with a valid JSON object matching this JSON Schema:\n{schema_json}\n"
            "Do NOT include markdown formatting or explanations outside the JSON."
        )

        for attempt in range(retries + 1):
            raw_output = await self.generate(prompt=prompt, system=system_instruction)
            cleaned_json = self._extract_json(raw_output)

            if cleaned_json:
                try:
                    parsed_dict = json.loads(cleaned_json)
                    validated = response_model.model_validate(parsed_dict)
                    return validated
                except Exception as e:
                    if attempt == retries:
                        raise ValueError(f"Failed to validate model output against {response_model.__name__}: {e}\nRaw output: {raw_output}")
            elif attempt == retries:
                raise ValueError(f"Model output did not contain valid JSON.\nRaw output: {raw_output}")

            # Prompt correction for retry
            prompt = f"{prompt}\n\nNOTE: Your previous response was invalid. Return ONLY a valid JSON object matching the requested schema."

        raise RuntimeError("Failed to obtain valid structured output from Ollama")

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        text = text.strip()
        # Direct JSON match
        if text.startswith("{") and text.endswith("}"):
            return text

        # Check for ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)

        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        return None
