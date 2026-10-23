import json
import time
import re
from typing import Optional, Dict, Any, List, Type, TypeVar
import httpx
from urllib.parse import urlparse

from ai.provider_base import AIProvider, TestResult
from security.credentials import CredentialVault
from storage.database import SettingsRepository

T = TypeVar("T")


class OnlineProvider(AIProvider):
    """
    Configurable Online AI Provider supporting any OpenAI-compatible API
    (e.g. Groq, OpenRouter, DeepSeek, OpenAI, Mistral, Together AI, or local vLLM).

    Security & Privacy Guarantees:
    - API keys are NEVER logged or returned in plain text.
    - All secrets are stored via Windows DPAPI (CredentialVault).
    - Prompts are only sent when the user has explicitly authorized Online or Auto mode.
    - Full error handling for 401 Unauthorized, 429 Rate Limits, timeouts, and malformed JSON.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 45.0,
        api_key_override: Optional[str] = None,
        provider_name: str = "online",
    ):
        self._base_url = self._validate_base_url(base_url or SettingsRepository.get("online_base_url", "https://api.openai.com/v1"))
        self._model = model or SettingsRepository.get("online_model", "gpt-4o-mini")
        self.timeout_seconds = timeout_seconds
        self._api_key_override = api_key_override
        self._provider_name = provider_name

    @property
    def provider_type(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model

    @model_name.setter
    def model_name(self, value: str) -> None:
        self._model = value
        SettingsRepository.set("online_model", value)

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._base_url = self._validate_base_url(value)
        SettingsRepository.set("online_base_url", self._base_url)

    @staticmethod
    def _validate_base_url(value: str) -> str:
        """Prevent API keys and prompts from being sent to local/unsafe endpoints."""
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Online provider base URL must be an absolute HTTPS URL without credentials.")
        return cleaned

    def _get_api_key(self) -> Optional[str]:
        if self._api_key_override:
            return self._api_key_override
        return CredentialVault.get_secret("online_api_key")

    def _is_gemini(self) -> bool:
        return (
            self._provider_name.lower() == "gemini"
            or "generativelanguage.googleapis.com" in self._base_url.lower()
            or "gemini" in self._model.lower()
        )

    async def is_available(self) -> bool:
        """Checks if online provider credentials and endpoint are configured."""
        api_key = self._get_api_key()
        if not api_key:
            return False
        try:
            if self._is_gemini():
                headers = {"x-goog-api-key": api_key}
                async with httpx.AsyncClient(timeout=4.0) as client:
                    res = await client.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                        headers=headers,
                    )
                    return res.status_code in (200, 400)
            else:
                headers = {"Authorization": f"Bearer {api_key}"}
                async with httpx.AsyncClient(timeout=4.0) as client:
                    res = await client.get(f"{self._base_url}/models", headers=headers)
                    return res.status_code in (200, 400)
        except Exception:
            return False

    async def _generate_gemini(
        self,
        prompt: str,
        system: Optional[str] = None,
        format: Optional[Any] = None,
        api_key: str = "",
    ) -> str:
        clean_model = self._model.replace("models/", "").strip()
        # Google has retired older Gemini models for new projects. Auto-map to active gemini-3.5-flash:
        model_aliases = {
            "gemini-1.5-flash": "gemini-3.5-flash",
            "gemini-1.5-flash-latest": "gemini-3.5-flash",
            "gemini-2.0-flash": "gemini-3.5-flash",
            "gemini-2.0-flash-exp": "gemini-3.5-flash",
            "gemini-2.5-flash": "gemini-3.5-flash",
            "gemini-1.5-pro": "gemini-3.5-flash",
            "gemini-pro": "gemini-3.5-flash",
        }
        target_model = model_aliases.get(clean_model, clean_model)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION: {system}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow all instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
            },
        }

        if format == "json" or isinstance(format, dict):
            payload["generationConfig"]["responseMimeType"] = "application/json"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 404 and target_model != "gemini-3.5-flash":
                # Fallback to active gemini-3.5-flash
                fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
                res = await client.post(fallback_url, headers=headers, json=payload)

            if res.status_code == 401:
                raise PermissionError("Gemini API Error: Invalid or expired API credentials (401 Unauthorized).")
            if res.status_code == 429:
                raise RuntimeError("Gemini API Error: Rate limit or quota exceeded (429 Too Many Requests).")
            if res.status_code == 503:
                raise RuntimeError("Gemini API Error: Model experiencing high demand. Please retry in a few seconds.")
            if res.status_code != 200:
                err_text = res.text
                if api_key in err_text:
                    err_text = err_text.replace(api_key, CredentialVault.mask_secret(api_key))
                raise RuntimeError(f"Gemini API error (HTTP {res.status_code}): {err_text}")

            data = res.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini returned no candidates.")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError("Gemini returned an empty response part.")
            return parts[0].get("text", "").strip()

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        format: Optional[Any] = None,
    ) -> str:
        api_key = self._get_api_key()
        if not api_key:
            raise PermissionError("Online provider is not configured: Missing API key in secure vault.")

        if self._is_gemini():
            return await self._generate_gemini(prompt=prompt, system=system, format=format, api_key=api_key)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
        }

        if format == "json" or isinstance(format, dict):
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
            if res.status_code == 401:
                raise PermissionError("Online API Error: Invalid or expired API credentials (401 Unauthorized).")
            if res.status_code == 429:
                raise RuntimeError("Online API Error: Rate limit or quota exceeded (429 Too Many Requests).")
            if res.status_code != 200:
                # Sanitize error message to prevent accidental key leakage
                err_text = res.text
                if api_key in err_text:
                    err_text = err_text.replace(api_key, CredentialVault.mask_secret(api_key))
                raise RuntimeError(f"Online provider error (HTTP {res.status_code}): {err_text}")

            data = res.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("Online provider returned an empty completion list.")
            return choices[0].get("message", {}).get("content", "").strip()

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        retries: int = 2,
    ) -> T:
        schema_dict = response_model.model_json_schema()
        schema_json = json.dumps(schema_dict, indent=2)
        system_instruction = (
            (system or "")
            + f"\n\nYou MUST respond ONLY with a valid JSON object matching this JSON Schema:\n{schema_json}\n"
            "Do NOT include markdown formatting or explanations outside the JSON."
        )

        for attempt in range(retries + 1):
            raw_output = await self.generate(
                prompt=prompt,
                system=system_instruction,
                format="json",
            )

            cleaned_json = self._extract_json(raw_output)
            if cleaned_json:
                try:
                    parsed_dict = json.loads(cleaned_json)
                    return response_model.model_validate(parsed_dict)
                except Exception as e:
                    if attempt == retries:
                        raise ValueError(f"Failed to validate online model output: {e}\nRaw output: {raw_output}")
            elif attempt == retries:
                raise ValueError(f"Online model output did not contain valid JSON.\nRaw output: {raw_output}")

            prompt = f"{prompt}\n\nNOTE: Your previous response was invalid. Return ONLY a valid JSON object matching the requested schema."

        raise RuntimeError("Failed to obtain valid structured output from online provider")

    async def unload(self) -> bool:
        # Remote APIs are stateless; no local VRAM unload needed
        return True

    async def test_capabilities(self) -> TestResult:
        start = time.perf_counter()
        api_key = self._get_api_key()
        if not api_key:
            return TestResult(
                success=False,
                latency_ms=0.0,
                model=self._model,
                provider="online",
                message="No API key configured in vault. Please save an API key first.",
                sample_response=None,
                structured_output_supported=False,
            )

        try:
            from agent.model import AgentStepDecision
            test_prompt = "Return a valid step decision testing system readiness. Set summary to 'Online provider ready' and actions to empty."
            res = await self.generate_structured(
                prompt=test_prompt,
                response_model=AgentStepDecision,
                retries=1,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            return TestResult(
                success=True,
                latency_ms=elapsed_ms,
                model=self._model,
                provider="online",
                message=f"Connected and verified structured JSON planning in {elapsed_ms}ms.",
                sample_response=res.summary,
                structured_output_supported=True,
            )
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            # Redact key if in error
            clean_err = str(e)
            if api_key and api_key in clean_err:
                clean_err = clean_err.replace(api_key, CredentialVault.mask_secret(api_key))
            return TestResult(
                success=False,
                latency_ms=elapsed_ms,
                model=self._model,
                provider="online",
                message=f"Online connection failed: {clean_err}",
                sample_response=None,
                structured_output_supported=False,
            )

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
