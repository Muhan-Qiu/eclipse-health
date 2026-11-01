"""自定义卡片的持久化与聚合。

REST API 与助手工具都走这里：创建 / 更新 / 编辑 / 草稿确认共用
``CardFields`` 校验，聚合逻辑只读 ``records`` 表。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlmodel import Session, select

from ..db.models import DashboardCardDraftTable, DashboardCardTable
from ..domain.common import to_storage_dt, utc_now
from ..domain.errors import InvalidInputError, not_found
from ..domain.ids import new_id
from .catalog import aggregate, build_series, query_points, spec_for
from .models import (
    CardCreator,
    CardData,
    CardFields,
    CardPoint,
    DashboardCard,
    DashboardCardDraft,
    DashboardCardUpdate,
)

# 每成员最多保留的助手草稿数；超出时删除最旧的，避免无限堆积。
MAX_DRAFTS_PER_MEMBER = 20


def _card_from_row(row: DashboardCardTable) -> DashboardCard:
    data = dict(row.data or {})
    fields = CardFields.model_validate(
        {key: value for key, value in data.items() if key != "createdBy"}
    )
    return DashboardCard(
        id=row.id,
        memberId=row.member_id,
        **fields.model_dump(),
        createdBy=data.get("createdBy", "user"),
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


def list_cards(session: Session, member_id: str) -> list[DashboardCard]:
    statement = (
        select(DashboardCardTable)
        .where(DashboardCardTable.member_id == member_id)
        .order_by(DashboardCardTable.created_at, DashboardCardTable.id)
    )
    return [_card_from_row(row) for row in session.exec(statement)]


def get_card(session: Session, member_id: str, card_id: str) -> DashboardCard:
    row = session.get(DashboardCardTable, card_id)
    if row is None or row.member_id != member_id:
        raise not_found("card", card_id)
    return _card_from_row(row)


def _insert_card_row(
    session: Session,
    *,
    member_id: str,
    fields: CardFields,
    created_by: CardCreator,
    now: Any,
):
    row = DashboardCardTable(
        id=new_id("card"),
        member_id=member_id,
        kind=fields.kind,
        data={**fields.model_dump(mode="json"), "createdBy": created_by},
        created_at=to_storage_dt(now),
        updated_at=to_storage_dt(now),
    )
    session.add(row)
    return row


def create_card(
    session: Session,
    *,
    member_id: str,
    fields: CardFields,
    created_by: CardCreator = "user",
) -> DashboardCard:
    row = _insert_card_row(
        session,
        member_id=member_id,
        fields=fields,
        created_by=created_by,
        now=utc_now(),
    )
    session.commit()
    return _card_from_row(row)


def update_card(
    session: Session,
    *,
    member_id: str,
    card_id: str,
    updates: DashboardCardUpdate,
) -> DashboardCard:
    row = session.get(DashboardCardTable, card_id)
    if row is None or row.member_id != member_id:
        raise not_found("card", card_id)

    current = dict(row.data or {})
    created_by = current.pop("createdBy", "user")
    merged = {**CardFields.model_validate(current).model_dump(mode="json")}
    merged.update(updates.model_dump(exclude_unset=True, mode="json"))
    try:
        fields = CardFields.model_validate(merged)
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "card fields are invalid",
            code="invalid_card",
            details={"errors": exc.errors(include_url=False)},
        ) from exc

    row.kind = fields.kind
    row.data = {**fields.model_dump(mode="json"), "createdBy": created_by}
    row.updated_at = to_storage_dt(utc_now())
    session.add(row)
    session.commit()
    return _card_from_row(row)


def delete_card(session: Session, *, member_id: str, card_id: str) -> None:
    row = session.get(DashboardCardTable, card_id)
    if row is None or row.member_id != member_id:
        raise not_found("card", card_id)
    session.delete(row)
    session.commit()


# --------------------------------------------------------------------------- #
# 聚合
# --------------------------------------------------------------------------- #


def _unit_for(fields: CardFields) -> tuple[str | None, str]:
    if fields.unit:
        return fields.unit, "card"
    if fields.aggregation == "count":
        return "count", "kind"
    spec = spec_for(fields.kind)
    if spec is not None and spec.unit:
        return spec.unit, "kind"
    return None, "missing"


def compute_card_data(
    session: Session,
    *,
    member_id: str,
    card_id: str,
    fields: CardFields,
) -> CardData:
    points = query_points(
        session,
        member_id=member_id,
        kind=fields.kind,
        window_days=fields.windowDays,
    )
    values = [point[1] for point in points]
    value = aggregate(values, fields.aggregation)
    secondary = None
    spec = spec_for(fields.kind)
    if spec is not None and spec.mode == "pair":
        secondary = aggregate(
            [point[2] for point in points if point[2] is not None],
            fields.aggregation,
        )
    unit, unit_source = _unit_for(fields)
    series = [CardPoint(**point) for point in build_series(points, fields.aggregation)]
    return CardData(
        cardId=card_id,
        kind=fields.kind,
        aggregation=fields.aggregation,
        value=value,
        secondaryValue=secondary,
        series=series,
        unit=unit,
        unitSource=unit_source,
        hasData=bool(points),
        sampleCount=len(points),
        windowDays=fields.windowDays,
        missingReason=None if points else "no_data",
    )


def _fields_of_card(card: DashboardCard) -> CardFields:
    return CardFields.model_validate(
        {
            "title": card.title,
            "kind": card.kind,
            "aggregation": card.aggregation,
            "windowDays": card.windowDays,
            "view": card.view,
            "unit": card.unit,
            "colorToken": card.colorToken,
        }
    )


def card_data(session: Session, card: DashboardCard) -> CardData:
    return compute_card_data(
        session,
        member_id=card.memberId,
        card_id=card.id,
        fields=_fields_of_card(card),
    )


# --------------------------------------------------------------------------- #
# 助手草稿
# --------------------------------------------------------------------------- #


def _draft_from_row(session: Session, row: DashboardCardDraftTable) -> DashboardCardDraft:
    data = dict(row.data or {})
    fields = CardFields.model_validate(
        {key: value for key, value in data.items() if key != "createdBy"}
    )
    preview = compute_card_data(
        session,
        member_id=row.member_id,
        card_id=row.id,
        fields=fields,
    )
    return DashboardCardDraft(
        id=row.id,
        memberId=row.member_id,
        card=fields,
        createdBy=data.get("createdBy", "agent"),
        createdAt=row.created_at,
        updatedAt=row.updated_at,
        preview=preview,
    )


def create_draft(
    session: Session,
    *,
    member_id: str,
    fields: CardFields,
    created_by: CardCreator = "agent",
) -> DashboardCardDraft:
    now = utc_now()
    row = DashboardCardDraftTable(
        id=new_id("cardDraft"),
        member_id=member_id,
        data={**fields.model_dump(mode="json"), "createdBy": created_by},
        created_at=to_storage_dt(now),
        updated_at=to_storage_dt(now),
    )
    session.add(row)

    existing = list(
        session.exec(
            select(DashboardCardDraftTable)
            .where(DashboardCardDraftTable.member_id == member_id)
            .order_by(DashboardCardDraftTable.created_at.asc(), DashboardCardDraftTable.id.asc())
        )
    )
    overflow = max(0, len(existing) - MAX_DRAFTS_PER_MEMBER)
    for stale in existing[:overflow]:
        session.delete(stale)
    session.commit()
    return _draft_from_row(session, row)


def list_drafts(session: Session, member_id: str) -> list[DashboardCardDraft]:
    statement = (
        select(DashboardCardDraftTable)
        .where(DashboardCardDraftTable.member_id == member_id)
        .order_by(DashboardCardDraftTable.created_at.desc(), DashboardCardDraftTable.id.desc())
    )
    return [_draft_from_row(session, row) for row in session.exec(statement)]


def get_draft_row(
    session: Session, member_id: str, draft_id: str
) -> DashboardCardDraftTable:
    row = session.get(DashboardCardDraftTable, draft_id)
    if row is None or row.member_id != member_id:
        raise not_found("card_draft", draft_id)
    return row


def confirm_draft(
    session: Session, *, member_id: str, draft_id: str
) -> DashboardCard:
    row = get_draft_row(session, member_id, draft_id)
    data = dict(row.data or {})
    created_by = data.pop("createdBy", "agent")
    try:
        fields = CardFields.model_validate(data)
    except PydanticValidationError as exc:
        raise InvalidInputError(
            "draft fields are invalid",
            code="invalid_card_draft",
            details={"errors": exc.errors(include_url=False)},
        ) from exc

    card_row = _insert_card_row(
        session,
        member_id=member_id,
        fields=fields,
        created_by=created_by,
        now=utc_now(),
    )
    session.delete(row)
    session.commit()
    return _card_from_row(card_row)


def delete_draft(session: Session, *, member_id: str, draft_id: str) -> None:
    row = get_draft_row(session, member_id, draft_id)
    session.delete(row)
    session.commit()


__all__ = [
    "MAX_DRAFTS_PER_MEMBER",
    "card_data",
    "compute_card_data",
    "confirm_draft",
    "create_card",
    "create_draft",
    "delete_card",
    "delete_draft",
    "get_card",
    "get_draft_row",
    "list_cards",
    "list_drafts",
    "update_card",
]
