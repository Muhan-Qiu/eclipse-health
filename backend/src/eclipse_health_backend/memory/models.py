"""个性化记忆的数据模型。"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

MAX_MEMORY_CHARS = 20_000


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=MAX_MEMORY_CHARS)
    enabled: bool = False


class MemoryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=MAX_MEMORY_CHARS)
    enabled: bool = False
    updatedAt: AwareDatetime | None = None


__all__ = ["MAX_MEMORY_CHARS", "MemoryDocument", "MemoryUpdate"]
