
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class UserRequest(BaseModel):
    request_id: str
    original_text: str = Field(min_length=1, max_length=10_000)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    context: dict[str, Any] = Field(default_factory=dict)
