"""安装审计：成功与失败都写入 marketplace.install，且不包含健康数据。"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from marketplace_test_helpers import FakeManager, local_market
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eclipse_health_backend.marketplace.errors import MarketplaceError
from eclipse_health_backend.marketplace.index import reset_cache
from eclipse_health_backend.marketplace.service import MarketplaceService
from eclipse_health_backend.modules.audit import AuditEvent


def _events(engine) -> list[AuditEvent]:
    with Session(engine) as session:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.action == "marketplace.install")
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return list(session.scalars(statement))


def test_install_success_and_failure_are_audited(
    tmp_path: Path, key: Ed25519PrivateKey
) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'audit.sqlite3').as_posix()}")
    AuditEvent.__table__.create(bind=engine)
    try:
        config, item, package = local_market(tmp_path, key)
        manager = FakeManager(engine=engine)
        service = MarketplaceService(manager, config=config)

        service.install("official", item["id"], item["version"])

        # 篡改包体让 sha256 校验失败，确认失败也会留痕。
        package.write_bytes(b"tampered")
        reset_cache()
        try:
            service.install("official", item["id"], item["version"])
        except MarketplaceError as exc:
            assert exc.code == "marketplace_checksum_mismatch"
        else:  # pragma: no cover - 校验失效时测试必须失败
            raise AssertionError("tampered package should not install")

        events = _events(engine)
        assert len(events) == 2
        success = json.loads(events[0].detail_json or "{}")
        failure = json.loads(events[1].detail_json or "{}")
        assert success["ok"] is True
        assert success["source"] == "official"
        assert success["keyId"] == "test-2026"
        assert success["sha256"] == item["sha256"]
        assert failure["ok"] is False
        assert failure["errorCode"] == "marketplace_checksum_mismatch"
        # 审计只记录元数据，不写包内容或健康数据。
        assert "payload" not in (events[1].detail_json or "")
    finally:
        engine.dispose()
