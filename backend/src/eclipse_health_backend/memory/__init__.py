"""个性化记忆：本机单文档，供助手注入上下文（G4 调用 ``memory_context``）。"""

from .models import MAX_MEMORY_CHARS, MemoryDocument, MemoryUpdate
from .storage import memory_context, read_memory, write_memory

__all__ = [
    "MAX_MEMORY_CHARS",
    "MemoryDocument",
    "MemoryUpdate",
    "memory_context",
    "read_memory",
    "write_memory",
]
