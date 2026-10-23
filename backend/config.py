from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smart_manager_host: str = Field(default="127.0.0.1", description="Host to bind backend API (loopback only)")
    smart_manager_port: int = Field(default=8765, description="Port for backend API")

    ollama_base_url: str = Field(default="http://127.0.0.1:11434", description="Base URL of local Ollama instance")
    ollama_model: str = Field(default="gemma4:e2b", description="Active local Ollama model")
    ollama_request_timeout_seconds: float = Field(default=60.0, description="Timeout for model inference requests")
    ollama_num_ctx: int = Field(default=4096, description="Context window size in tokens")
    # Planning decisions are small JSON objects. Limiting their output avoids
    # spending most of a task generating unused tokens.
    ollama_num_predict: int = Field(default=256, description="Maximum tokens to generate per planning step")
    ollama_num_batch: int = Field(default=128, description="Batch size for prompt evaluation (128 conserves memory)")
    # Never use 0s here: Ollama would unload after each planning step and need
    # to reload the model again for the next step of the same task.
    ollama_keep_alive: str = Field(default="5m", description="Idle unload duration between model requests")
    ollama_auto_unload: bool = Field(default=True, description="Automatically unload model after task execution to minimize RAM")
    ollama_think: bool = Field(default=False, description="Whether to include thinking tokens in model responses")

    agent_max_iterations: int = Field(default=15, description="Maximum loop iterations per task")
    agent_history_steps: int = Field(default=3, description="Recent execution steps included in prompt context")
    agent_max_parallel_tasks: int = Field(default=1, description="Strict concurrency limit to prevent duplicate inference loads")
    agent_default_confirmation_required: bool = Field(
        default=True, description="Require user confirmation for critical actions"
    )

    database_url: str = Field(default="sqlite:///data/smart_manager.db", description="SQLite database path")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode flag")
    api_session_secret: str = Field(default="", description="Per-launch desktop-to-backend session secret")

    @field_validator("smart_manager_host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        """The API can execute local actions, so never expose it on the LAN."""
        if value not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("SMART_MANAGER_HOST must be a loopback address.")
        return value

    @field_validator("smart_manager_port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("SMART_MANAGER_PORT must be between 1 and 65535.")
        return value

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        path = self.project_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
