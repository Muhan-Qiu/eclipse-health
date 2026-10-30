"""隐私中心 API（D6）。

- ``GET /privacy/storage``：各表数量与文件占用；
- ``DELETE /privacy/all?confirm=DELETE_ALL``：清空记录/波形/分析/测量/报告。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..domain.errors import InvalidInputError
from ..privacy.service import purge_all, storage_info
from .deps import SessionDep

router = APIRouter(tags=["privacy"])

CONFIRM_TOKEN = "DELETE_ALL"


class StorageCounts(BaseModel):
    members: int
    records: int
    signals: int
    analyses: int
    measurements: int
    annotations: int
    reports: int
    deletedRecords: int


class StorageBytes(BaseModel):
    signals: int
    reports: int
    imports: int
    database: int
    total: int


class StorageResponse(BaseModel):
    dataDir: str
    counts: StorageCounts
    bytes: StorageBytes
    localOnly: bool
    telemetry: bool


class PurgeCounts(BaseModel):
    records: int
    signals: int
    analyses: int
    measurements: int
    annotations: int
    reports: int


class PurgeResponse(BaseModel):
    deleted: PurgeCounts
    removedFiles: dict[str, int]


@router.get("/privacy/storage", response_model=StorageResponse, summary="本机存储用量")
def storage(session: SessionDep) -> Any:
    return storage_info(session)


@router.delete(
    "/privacy/all",
    response_model=PurgeResponse,
    summary="清空记录、波形、分析、测量与报告（保留成员与设置）",
    responses={422: {"description": "缺少或错误的确认令牌"}},
)
def purge(
    session: SessionDep,
    confirm: Annotated[str, Query(description="必须为 DELETE_ALL")],
) -> Any:
    if confirm != CONFIRM_TOKEN:
        raise InvalidInputError(
            "confirmation token does not match",
            code="confirmation_required",
            details={"expected": CONFIRM_TOKEN},
        )
    return purge_all(session)


__all__ = ["CONFIRM_TOKEN", "router"]
