"""个性化记忆 API：``GET/PUT /api/v1/memory``。

路由自带 ``/memory`` 前缀；由 ``api/__init__.py`` 统一挂载到 ``/api/v1``。
"""

from __future__ import annotations

from fastapi import APIRouter

from .models import MemoryDocument, MemoryUpdate
from .storage import read_memory, write_memory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=MemoryDocument, summary="读取个人记忆")
def get_memory() -> MemoryDocument:
    return read_memory()


@router.put("", response_model=MemoryDocument, summary="保存个人记忆")
def put_memory(payload: MemoryUpdate) -> MemoryDocument:
    return write_memory(payload)


__all__ = ["router"]
