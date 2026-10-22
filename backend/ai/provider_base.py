from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ModelMetadata(BaseModel):
    id: Optional[str] = None
    name: str
    tag: str = "latest"
    provider: str = "ollama"  # ollama, gemini, openai, groq, custom
    type: str = "local"  # local, online
    base_url: Optional[str] = None
    has_api_key: bool = False
    api_key_masked: Optional[str] = None
    size_bytes: Optional[int] = None
    size_formatted: str = "Unknown"
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    family: Optional[str] = None
    format: Optional[str] = None
    capabilities: List[str] = []
    modified_at: Optional[str] = None
    is_loaded: bool = False
    is_selected: bool = False
    last_used: Optional[str] = None


class TestResult(BaseModel):
    success: bool
    latency_ms: float
    model: str
    provider: str
    message: str
    sample_response: Optional[str] = None
    structured_output_supported: bool = False


class AIProvider(ABC):
    @property
    @abstractmethod
    def provider_type(self) -> str:
        """e.g. 'local' or 'online'"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Active model identifier"""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider endpoint and model are reachable"""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        format: Optional[Any] = None,
    ) -> str:
        """Generate raw text from provider"""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
        retries: int = 2,
    ) -> T:
        """Generate and validate structured output against Pydantic schema"""
        pass

    @abstractmethod
    async def unload(self) -> bool:
        """Release GPU VRAM and process RAM if supported"""
        pass

    @abstractmethod
    async def test_capabilities(self) -> TestResult:
        """Validate live connectivity and structured planning generation"""
        pass
