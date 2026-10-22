import json
import re
import time
import asyncio
import logging
from typing import Optional, Dict, Any, List, Type, TypeVar, Tuple
import httpx

from config import settings
from ai.provider_base import AIProvider, ModelMetadata, TestResult
from ai.ollama_provider import OllamaProvider
from ai.online_provider import OnlineProvider
from security.credentials import CredentialVault
from storage.database import SettingsRepository

logger = logging.getLogger("smart_manager.ai")
T = TypeVar("T")

# Safe model name pattern (letters, numbers, colons, dashes, dots, underscores, forward slash)
SAFE_MODEL_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\/]+(:[a-zA-Z0-9_\-\.]+)?$")

PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "label": "Google Gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "suggested_models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"],
    },
    "groq": {
        "label": "Groq",
        "default_base_url": "https://api.groq.com/openai/v1",
        "suggested_models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
    },
    "openai": {
        "label": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "suggested_models": ["gpt-4o-mini", "gpt-4o"],
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "default_base_url": "",
        "suggested_models": [],
    },
}


class ProviderManager:
    """
    Unified Model Manager and AI Provider Coordinator.
    Manages local Ollama models and added online models (Gemini, Groq, OpenAI, custom).
    Users select their model directly from the unified models list.
    """

    def __init__(self, ollama_provider: Optional[OllamaProvider] = None):
        self.local_provider = ollama_provider or OllamaProvider()
        self.online_provider = OnlineProvider()

        # Load persisted settings
        self._mode = SettingsRepository.get("ai_provider_mode", "local")
        self._auto_fallback_to_online = SettingsRepository.get("auto_fallback_to_online", "false").lower() == "true"
        self._auto_fallback_to_local = SettingsRepository.get("auto_fallback_to_local", "true").lower() == "true"
        self._online_authorized = SettingsRepository.get("online_authorized", "false").lower() == "true"

        # Active downloads tracker
        self._active_downloads: Dict[str, Dict[str, Any]] = {}
        self._active_tasks: set = set()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, new_mode: str) -> None:
        if new_mode not in ("local", "online", "auto"):
            raise ValueError(f"Invalid mode: '{new_mode}'. Must be 'local', 'online', or 'auto'.")
        if self._active_tasks:
            raise RuntimeError("Cannot change AI provider mode while a task is actively running.")
        self._mode = new_mode
        SettingsRepository.set("ai_provider_mode", new_mode)

    @property
    def online_authorized(self) -> bool:
        return self._online_authorized

    def set_online_authorized(self, authorized: bool) -> None:
        self._online_authorized = authorized
        SettingsRepository.set("online_authorized", "true" if authorized else "false")

    @property
    def auto_fallback_to_online(self) -> bool:
        return self._auto_fallback_to_online

    def set_auto_fallback_to_online(self, enabled: bool) -> None:
        self._auto_fallback_to_online = enabled
        SettingsRepository.set("auto_fallback_to_online", "true" if enabled else "false")

    @property
    def auto_fallback_to_local(self) -> bool:
        return self._auto_fallback_to_local

    def set_auto_fallback_to_local(self, enabled: bool) -> None:
        self._auto_fallback_to_local = enabled
        SettingsRepository.set("auto_fallback_to_local", "true" if enabled else "false")

    def register_task_start(self, task_id: str) -> None:
        self._active_tasks.add(task_id)

    def register_task_end(self, task_id: str) -> None:
        self._active_tasks.discard(task_id)

    def has_active_tasks(self) -> bool:
        return len(self._active_tasks) > 0

    # ================= UNIFIED MODEL LIST & MANAGEMENT =================

    def get_active_model_id(self) -> str:
        return SettingsRepository.get("active_model_id", self.local_provider.model_name or "gemma4:e2b")

    def get_configured_online_models(self) -> List[Dict[str, Any]]:
        raw = SettingsRepository.get("configured_online_models", "[]")
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_configured_online_models(self, models: List[Dict[str, Any]]) -> None:
        SettingsRepository.set("configured_online_models", json.dumps(models))

    async def list_all_models(self) -> List[ModelMetadata]:
        """
        Returns all installed local Ollama models and user-added online models.
        """
        all_models: List[ModelMetadata] = []
        active_id = self.get_active_model_id()

        # 1. Local Models from Ollama
        try:
            local_models = await self.local_provider.list_models_detailed()
            for m in local_models:
                m.id = m.name
                m.type = "local"
                m.provider = "ollama"
                m.is_selected = (m.name == active_id)
                all_models.append(m)
        except Exception as e:
            logger.warning(f"Could not retrieve local Ollama models: {e}")

        # 2. Configured Online Models
        online_models = self.get_configured_online_models()
        for om in online_models:
            mid = om.get("id", f"{om.get('provider')}:{om.get('name')}")
            key_name = f"online_key_{mid}"
            has_key = CredentialVault.has_secret(key_name) or CredentialVault.has_secret("online_api_key")
            key_raw = CredentialVault.get_secret(key_name) or CredentialVault.get_secret("online_api_key")
            masked = CredentialVault.mask_secret(key_raw) if key_raw else ""

            meta = ModelMetadata(
                id=mid,
                name=om.get("name", mid),
                tag=om.get("provider", "online"),
                provider=om.get("provider", "custom"),
                type="online",
                base_url=om.get("base_url"),
                has_api_key=has_key,
                api_key_masked=masked,
                size_formatted="Cloud API",
                capabilities=["chat", "structured_json"],
                is_selected=(mid == active_id),
            )
            all_models.append(meta)

        # Fallback: if no model matched active_id, mark first model as selected
        if all_models and not any(m.is_selected for m in all_models):
            all_models[0].is_selected = True

        return all_models

    def add_online_model(
        self,
        provider: str,
        model_name: str,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Adds or updates a model from Gemini, Groq, OpenAI, or a custom provider.
        Stores the API key securely via Windows DPAPI.
        """
        prov_key = provider.strip().lower()
        clean_name = model_name.strip()
        if not clean_name:
            raise ValueError("Model name cannot be empty.")
        if not api_key or not api_key.strip():
            raise ValueError("API key is required for online models.")

        preset = PROVIDER_PRESETS.get(prov_key, PROVIDER_PRESETS["custom"])
        final_base_url = (base_url.strip() if base_url and base_url.strip() else preset["default_base_url"]).rstrip("/")
        if not final_base_url:
            raise ValueError(f"Base URL is required for provider '{prov_key}'.")

        model_id = f"{prov_key}:{clean_name}"
        # Save key in Windows DPAPI
        CredentialVault.set_secret(f"online_key_{model_id}", api_key.strip())
        if not CredentialVault.has_secret("online_api_key"):
            CredentialVault.set_secret("online_api_key", api_key.strip())

        online_models = self.get_configured_online_models()
        # Remove previous entry if updating
        online_models = [m for m in online_models if m.get("id") != model_id]
        new_entry = {
            "id": model_id,
            "name": clean_name,
            "provider": prov_key,
            "base_url": final_base_url,
            "created_at": time.time(),
        }
        online_models.append(new_entry)
        self.save_configured_online_models(online_models)

        # Automatically select if requested or if it's the only one
        return new_entry

    async def select_model(self, model_identifier: str) -> str:
        """
        Selects an active model (local or online).
        Prevents switching while tasks are running.
        """
        if self.has_active_tasks():
            raise RuntimeError("Cannot switch model while an active task is running.")

        clean_id = model_identifier.strip()
        online_models = self.get_configured_online_models()
        matching_online = next(
            (m for m in online_models if m.get("id") == clean_id or m.get("name") == clean_id),
            None,
        )

        if matching_online:
            SettingsRepository.set("active_model_id", matching_online["id"])
            SettingsRepository.set("online_authorized", "true")
            self._mode = "online"
            SettingsRepository.set("ai_provider_mode", "online")
            return matching_online["id"]

        # Check local models in Ollama
        installed = await self.local_provider.list_models_detailed()
        installed_names = [m.name for m in installed]
        if not any(clean_id == m or clean_id.split(":")[0] == m.split(":")[0] for m in installed_names):
            raise FileNotFoundError(f"Model '{clean_id}' is not installed in local Ollama or added as an online model.")

        self.local_provider.model_name = clean_id
        settings.ollama_model = clean_id
        SettingsRepository.set("selected_local_model", clean_id)
        SettingsRepository.set("active_model_id", clean_id)
        self._mode = "local"
        SettingsRepository.set("ai_provider_mode", "local")
        return clean_id

    async def remove_model(self, model_identifier: str) -> bool:
        """
        Safely removes an online model or local Ollama model.
        """
        if self.has_active_tasks():
            raise RuntimeError("Cannot delete a model while a task is running.")

        clean_id = model_identifier.strip()
        online_models = self.get_configured_online_models()
        matching_online = next(
            (m for m in online_models if m.get("id") == clean_id or m.get("name") == clean_id),
            None,
        )

        if matching_online:
            # Delete DPAPI key
            CredentialVault.delete_secret(f"online_key_{matching_online['id']}")
            updated = [m for m in online_models if m.get("id") != matching_online["id"]]
            self.save_configured_online_models(updated)

            # If removed model was the active one, fallback to local default
            if self.get_active_model_id() == matching_online["id"]:
                default_local = self.local_provider.model_name or "gemma4:e2b"
                SettingsRepository.set("active_model_id", default_local)
                self._mode = "local"
                SettingsRepository.set("ai_provider_mode", "local")
            return True

        # Local model deletion
        return await self.delete_local_model(clean_id)

    async def test_model(self, model_identifier: Optional[str] = None) -> TestResult:
        """
        Tests structured JSON generation and latency for a given model.
        """
        target = (model_identifier or self.get_active_model_id()).strip()
        online_models = self.get_configured_online_models()
        matching_online = next(
            (m for m in online_models if m.get("id") == target or m.get("name") == target),
            None,
        )

        if matching_online:
            key = CredentialVault.get_secret(f"online_key_{matching_online['id']}") or CredentialVault.get_secret("online_api_key")
            prov = OnlineProvider(
                base_url=matching_online.get("base_url"),
                model=matching_online.get("name"),
                api_key_override=key,
                provider_name=matching_online.get("provider", "online"),
            )
            return await prov.test_capabilities()

        # Local model
        return await self.local_provider.test_capabilities(target_model=target)

    async def get_active_provider(self) -> Tuple[AIProvider, str]:
        """
        Returns the active AI provider and user-facing status label.
        Automatically routes to the selected local or online model.
        """
        active_id = self.get_active_model_id()
        online_models = self.get_configured_online_models()
        matching_online = next(
            (m for m in online_models if m.get("id") == active_id or m.get("name") == active_id),
            None,
        )

        if matching_online:
            key = CredentialVault.get_secret(f"online_key_{matching_online['id']}") or CredentialVault.get_secret("online_api_key")
            if not key:
                raise PermissionError(
                    f"API key missing for online model '{matching_online['name']}'. "
                    f"Please re-enter the API key in Settings."
                )
            prov = OnlineProvider(
                base_url=matching_online.get("base_url"),
                model=matching_online.get("name"),
                api_key_override=key,
                provider_name=matching_online.get("provider", "online"),
            )
            label = f"{matching_online.get('provider', 'online').capitalize()}: {matching_online['name']}"
            return prov, label

        # Fallback mode logic (if explicitly in online mode without active online model)
        if self._mode == "online":
            if not self._online_authorized:
                raise PermissionError(
                    "Online Mode is not active because explicit user authorization has not been granted. "
                    "Please authorize online inference in Settings."
                )
            if not CredentialVault.has_secret("online_api_key"):
                raise PermissionError("Online Mode requires an API key. Please configure it in Settings.")
            return self.online_provider, f"online:{self.online_provider.model_name}"

        if self._mode == "auto":
            local_healthy = await self.local_provider.is_available()
            if local_healthy:
                return self.local_provider, f"local:{self.local_provider.model_name}"
            if self._auto_fallback_to_online and self._online_authorized and CredentialVault.has_secret("online_api_key"):
                logger.info("Auto Mode: Local Ollama unreachable. Falling back to online provider.")
                return self.online_provider, f"online:{self.online_provider.model_name} (fallback)"

        # Default Local Provider
        local_model = active_id if active_id and ":" not in active_id else self.local_provider.model_name
        self.local_provider.model_name = local_model
        return self.local_provider, f"local:{self.local_provider.model_name}"

    # ================= BACKWARD-COMPATIBLE HELPERS FOR TESTS =================

    async def select_local_model(self, model_name: str) -> None:
        await self.select_model(model_name)

    async def delete_local_model(self, model_name: str) -> bool:
        if self.has_active_tasks():
            raise RuntimeError("Cannot delete a model while a task is running.")

        clean_name = model_name.strip()
        if not SAFE_MODEL_NAME_REGEX.match(clean_name):
            raise ValueError(f"Invalid model identifier: '{clean_name}'.")

        installed = await self.local_provider.list_models_detailed()
        if len(installed) <= 1 and self._mode == "local":
            raise PermissionError(
                "Cannot delete the only available local model while Local Mode is active. "
                "Download an alternative model first."
            )

        if self.local_provider.model_name == clean_name:
            other = next((m.name for m in installed if m.name != clean_name), None)
            if other:
                await self.select_local_model(other)

        return await self.local_provider.delete_model(clean_name)

    async def start_pull_model(self, model_name: str) -> Dict[str, Any]:
        clean_name = model_name.strip()
        if not SAFE_MODEL_NAME_REGEX.match(clean_name):
            raise ValueError(f"Invalid model identifier: '{clean_name}'.")

        if clean_name in self._active_downloads:
            info = self._active_downloads[clean_name]
            if info["status"] in ("downloading", "starting", "verifying"):
                return {"status": "already_in_progress", "model": clean_name, "progress": info}

        cancel_event = asyncio.Event()
        progress_info: Dict[str, Any] = {
            "model": clean_name,
            "status": "starting",
            "completed_bytes": 0,
            "total_bytes": 0,
            "percent": 0.0,
            "error": None,
            "cancel_event": cancel_event,
            "started_at": time.time(),
        }
        self._active_downloads[clean_name] = progress_info
        asyncio.create_task(self._pull_worker(clean_name, progress_info, cancel_event))
        return {"status": "started", "model": clean_name}

    async def _pull_worker(self, model_name: str, progress_info: Dict[str, Any], cancel_event: asyncio.Event) -> None:
        try:
            base_url = self.local_provider.client.base_url
            async with httpx.AsyncClient(timeout=3600.0) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/api/pull",
                    json={"model": model_name, "stream": True},
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        progress_info["status"] = "error"
                        progress_info["error"] = f"Ollama download failed: {error_text.decode('utf-8', errors='ignore')}"
                        return

                    async for line in response.aiter_lines():
                        if cancel_event.is_set():
                            progress_info["status"] = "cancelled"
                            return
                        if not line or not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            status_str = data.get("status", "")
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)
                            progress_info["status"] = status_str
                            if total > 0:
                                progress_info["completed_bytes"] = completed
                                progress_info["total_bytes"] = total
                                progress_info["percent"] = round((completed / total) * 100, 1)
                            if status_str == "success":
                                progress_info["status"] = "completed"
                                progress_info["percent"] = 100.0
                                return
                        except Exception:
                            continue

            progress_info["status"] = "completed"
            progress_info["percent"] = 100.0
        except Exception as e:
            progress_info["status"] = "error"
            progress_info["error"] = str(e)

    def get_pull_status(self, model_name: str) -> Optional[Dict[str, Any]]:
        clean_name = model_name.strip()
        info = self._active_downloads.get(clean_name)
        if not info:
            return None
        return {
            "model": info["model"],
            "status": info["status"],
            "completed_bytes": info["completed_bytes"],
            "total_bytes": info["total_bytes"],
            "percent": info["percent"],
            "error": info["error"],
        }

    def cancel_pull(self, model_name: str) -> bool:
        clean_name = model_name.strip()
        info = self._active_downloads.get(clean_name)
        if info and "cancel_event" in info:
            info["cancel_event"].set()
            info["status"] = "cancelled"
            return True
        return False
