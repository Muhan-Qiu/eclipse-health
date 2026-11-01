"""自定义仪表盘卡片 API：``/api/v1/dashboard/...``。

- 所有字段经 Pydantic 枚举校验，白名单之外直接 422；
- 卡片不保存数据副本，读取时按当前成员 + 时间窗聚合 ``records``；
- 助手草稿与正式卡片分开存放，确认后才进入仪表盘。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlmodel import Session

from ..api.deps import SessionDep
from ..db.repositories import ensure_default_member, get_member_row
from ..domain.errors import not_found
from . import service
from .catalog import templates
from .models import (
    CardData,
    CardFields,
    CardTemplate,
    DashboardCard,
    DashboardCardCreate,
    DashboardCardDraft,
    DashboardCardDraftList,
    DashboardCardList,
    DashboardCardOut,
    DashboardCardUpdate,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MemberQuery = Annotated[str | None, Query(alias="memberId", max_length=64)]


def _resolve_member(session: Session, member_id: str | None) -> str:
    if member_id:
        if get_member_row(session, member_id) is None:
            raise not_found("member", member_id)
        return member_id
    return ensure_default_member(session).id


def _card_out(session: Session, card: DashboardCard, include_data: bool) -> DashboardCardOut:
    out = DashboardCardOut(**card.model_dump())
    if include_data:
        out.data = service.card_data(session, card)
    return out


@router.get("/cards", response_model=DashboardCardList, summary="列出当前成员的自定义卡片")
def list_cards(
    session: SessionDep,
    memberId: MemberQuery = None,
    includeData: bool = False,
) -> DashboardCardList:
    member_id = _resolve_member(session, memberId)
    items = [
        _card_out(session, card, includeData)
        for card in service.list_cards(session, member_id)
    ]
    return DashboardCardList(items=items)


@router.post(
    "/cards",
    response_model=DashboardCard,
    status_code=status.HTTP_201_CREATED,
    summary="创建自定义卡片",
)
def create_card(payload: DashboardCardCreate, session: SessionDep) -> DashboardCard:
    member_id = _resolve_member(session, payload.memberId)
    fields = CardFields.model_validate(
        payload.model_dump(exclude={"memberId", "createdBy"})
    )
    return service.create_card(
        session,
        member_id=member_id,
        fields=fields,
        created_by=payload.createdBy,
    )


@router.get(
    "/cards/{card_id}/data",
    response_model=CardData,
    summary="读取一张卡片在当前时间窗的聚合数据",
)
def get_card_data(card_id: str, session: SessionDep, memberId: MemberQuery = None) -> CardData:
    member_id = _resolve_member(session, memberId)
    card = service.get_card(session, member_id, card_id)
    return service.card_data(session, card)


@router.get("/cards/{card_id}", response_model=DashboardCard, summary="读取一张卡片")
def get_card(card_id: str, session: SessionDep, memberId: MemberQuery = None) -> DashboardCard:
    member_id = _resolve_member(session, memberId)
    return service.get_card(session, member_id, card_id)


@router.patch("/cards/{card_id}", response_model=DashboardCard, summary="更新卡片")
def patch_card(
    card_id: str,
    payload: DashboardCardUpdate,
    session: SessionDep,
    memberId: MemberQuery = None,
) -> DashboardCard:
    member_id = _resolve_member(session, memberId)
    return service.update_card(
        session,
        member_id=member_id,
        card_id=card_id,
        updates=payload,
    )


@router.delete(
    "/cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除卡片",
)
def delete_card(
    card_id: str, session: SessionDep, memberId: MemberQuery = None
) -> Response:
    member_id = _resolve_member(session, memberId)
    service.delete_card(session, member_id=member_id, card_id=card_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/card-templates",
    response_model=list[CardTemplate],
    summary="内置卡片模板（压力 / 血氧 / 血压 / 运动 / 睡眠）",
)
def list_card_templates() -> list[CardTemplate]:
    return templates()


@router.get(
    "/card-drafts",
    response_model=DashboardCardDraftList,
    summary="助手生成、等待确认的卡片草稿",
)
def list_card_drafts(
    session: SessionDep, memberId: MemberQuery = None
) -> DashboardCardDraftList:
    member_id = _resolve_member(session, memberId)
    return DashboardCardDraftList(items=service.list_drafts(session, member_id))


@router.post(
    "/card-drafts",
    response_model=DashboardCardDraft,
    status_code=status.HTTP_201_CREATED,
    summary="创建一个卡片草稿（不写入仪表盘）",
)
def create_card_draft(
    payload: CardFields, session: SessionDep, memberId: MemberQuery = None
) -> DashboardCardDraft:
    member_id = _resolve_member(session, memberId)
    return service.create_draft(
        session, member_id=member_id, fields=payload, created_by="user"
    )


@router.post(
    "/card-drafts/{draft_id}/confirm",
    response_model=DashboardCard,
    status_code=status.HTTP_201_CREATED,
    summary="确认草稿并写入仪表盘",
)
def confirm_card_draft(
    draft_id: str, session: SessionDep, memberId: MemberQuery = None
) -> DashboardCard:
    member_id = _resolve_member(session, memberId)
    return service.confirm_draft(session, member_id=member_id, draft_id=draft_id)


@router.delete(
    "/card-drafts/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="丢弃卡片草稿",
)
def delete_card_draft(
    draft_id: str, session: SessionDep, memberId: MemberQuery = None
) -> Response:
    member_id = _resolve_member(session, memberId)
    service.delete_draft(session, member_id=member_id, draft_id=draft_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
