"""成员 API：默认只有一个「本人」，但数据模型已按多成员预留。"""

from __future__ import annotations

from fastapi import APIRouter, status

from ..db.repositories import (
    add_member,
    get_member_row,
    list_member_rows,
    member_from_row,
    update_member_row,
)
from ..domain.common import utc_now
from ..domain.errors import not_found
from ..domain.ids import new_id
from ..domain.models import Member, MemberCreate, MemberUpdate
from .deps import SessionDep

router = APIRouter()


@router.get("", response_model=list[Member], summary="列出所有成员")
def list_members(session: SessionDep) -> list[Member]:
    return [member_from_row(row) for row in list_member_rows(session)]


@router.post("", response_model=Member, status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberCreate, session: SessionDep) -> Member:
    now = utc_now()
    member = Member(
        id=new_id("member"),
        displayName=payload.displayName,
        birthYear=payload.birthYear,
        sex=payload.sex,
        heightCm=payload.heightCm,
        weightKg=payload.weightKg,
        conditions=payload.conditions,
        medications=payload.medications,
        notes=payload.notes,
        createdAt=now,
        updatedAt=now,
    )
    return add_member(session, member)


@router.get("/{member_id}", response_model=Member, summary="按 ID 读取成员")
def get_member(member_id: str, session: SessionDep) -> Member:
    row = get_member_row(session, member_id)
    if row is None:
        raise not_found("member", member_id)
    return member_from_row(row)


@router.patch("/{member_id}", response_model=Member, summary="更新成员资料")
def patch_member(member_id: str, payload: MemberUpdate, session: SessionDep) -> Member:
    row = get_member_row(session, member_id)
    if row is None:
        raise not_found("member", member_id)

    current = member_from_row(row)
    merged = current.model_dump(by_alias=True, mode="json")
    merged.update(payload.model_dump(exclude_unset=True, by_alias=True, mode="json"))
    merged["updatedAt"] = utc_now()
    updated = Member.model_validate(merged)
    return update_member_row(session, row, updated)
