"""教练测试的共用工具：直接写合成记录，不读 uploads/ 或真实样本。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.models import RecordTable
from eclipse_health_backend.domain.ids import new_id


def seed_record(
    member_id: str,
    record_type: str,
    payload: dict[str, Any],
    *,
    captured_at: datetime | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    record_id = new_id("record")
    with session_scope() as session:
        session.add(
            RecordTable(
                id=record_id,
                member_id=member_id,
                record_type=record_type,
                module_id=None,
                captured_at=captured_at or now,
                data=data or {"capturedAt": (captured_at or now).isoformat()},
                payload=payload,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
        )
        session.commit()
    return record_id
