from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smart_manager_host: str = Field(default="127.0.0.1", description="Host to bind backend API (loopback only)")
    smart_manager_port: int = Field(default=8765, description="Port for backend API")

    ollama_base_url: str = Field(default="http://127.0.0.1:11434", description="Base URL of local Ollama instance")
    ollama_model: str = Field(default="gemma2:2b", description="Active local Ollama model")
    ollama_request_timeout_seconds: float = Field(default=60.0, description="Timeout for model inference requests")

    agent_max_iterations: int = Field(default=15, description="Maximum loop iterations per task")
    agent_default_confirmation_required: bool = Field(
        default=True, description="Require user confirmation for critical actions"
    )

    database_url: str = Field(default="sqlite:///data/smart_manager.db", description="SQLite database path")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode flag")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        path = self.project_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
