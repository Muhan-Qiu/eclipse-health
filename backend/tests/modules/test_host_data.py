"""A2：模块核心数据 API（records.* / signals.read）的可见性、写入、审计。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from module_test_helpers import build_demo_package
from sqlmodel import Session

from eclipse_health_backend.db.base import Base
from eclipse_health_backend.db.repositories import (
    add_record,
    add_signal,
    ensure_default_member,
    make_signal,
)
from eclipse_health_backend.domain.common import utc_now
from eclipse_health_backend.domain.ids import new_id
from eclipse_health_backend.domain.models import HealthRecord
from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manager import ModuleManager
from eclipse_health_backend.settings import get_settings
from eclipse_health_backend.storage.files import write_signal

HOST_ID = "org.eclipsehealth.demo.host"
OTHER_ID = "org.eclipsehealth.demo.other"
HOST_TYPE = "io.github.tester.vitals"
OTHER_TYPE = "io.github.tester.other"
ECG_TYPE = "org.eclipsehealth.ecg"


def _install(
    tmp_path: Path,
    manager: ModuleManager,
    module_id: str,
    record_types: list[str],
    permissions: list[str],
) -> None:
    package = build_demo_package(
        tmp_path,
        permissions=permissions,
        manifest_updates={
            "id": module_id,
            "type": "health-domain",
            "contributes": {
                "recordTypes": [
                    {"id": record_type, "name": record_type, "schema": {"type": "object"}}
                    for record_type in record_types
                ]
            },
        },
    )
    manager.install(package)


@pytest.fixture(autouse=True)
def _host_schema(manager: ModuleManager) -> None:
    """核心表挂在同一个 Base.metadata 上；测试 engine 需要显式建表。"""
    Base.metadata.create_all(manager.engine)
    get_settings().ensure_dirs()


@pytest.fixture()
def member(_host_schema: None, manager: ModuleManager) -> dict:
    with Session(manager.engine) as session:
        default = ensure_default_member(session)
    return default.model_dump(by_alias=True, mode="json")


@pytest.fixture()
def host(manager: ModuleManager, tmp_path: Path) -> str:
    _install(
        tmp_path,
        manager,
        HOST_ID,
        [HOST_TYPE],
        ["records:read", "records:write", "records:delete"],
    )
    return HOST_ID


@pytest.fixture()
def other(manager: ModuleManager, tmp_path: Path) -> str:
    _install(
        tmp_path,
        manager,
        OTHER_ID,
        [OTHER_TYPE],
        ["records:read", "records:write", "records:delete"],
    )
    manager.grant_permission(OTHER_ID, "records:delete")
    return OTHER_ID


def _call(manager: ModuleManager, module_id: str, method: str, params: dict) -> object:
    return manager._handle_core_call(module_id, method, params)


def _create(manager: ModuleManager, module_id: str, member_id: str, **overrides: object) -> dict:
    params: dict[str, object] = {
        "memberId": member_id,
        "recordType": HOST_TYPE,
        "capturedAt": "2026-10-30T10:00:00+08:00",
        "payload": {"hr": 62},
        "tags": ["晨起"],
        "notes": "心悸",
    }
    params.update(overrides)
    return _call(manager, module_id, "records.create", params)  # type: ignore[return-value]


def _insert_record(
    manager: ModuleManager,
    member_id: str,
    *,
    module_id: str | None,
    record_type: str,
    captured_at: datetime | None = None,
) -> str:
    now = captured_at or utc_now()
    record_id = new_id("record")
    record = HealthRecord(
        id=record_id,
        memberId=member_id,
        recordType=record_type,
        moduleId=module_id,
        capturedAt=now,
        createdAt=now,
        updatedAt=now,
    )
    with Session(manager.engine) as session:
        add_record(session, record)
    return record_id


def _insert_record_with_signals(
    manager: ModuleManager,
    member_id: str,
    *,
    module_id: str,
    record_type: str,
    leads: tuple[str, ...] = ("II",),
    n_samples: int = 1_000,
    fs: float = 500.0,
) -> tuple[str, dict[str, np.ndarray]]:
    now = utc_now()
    record_id = new_id("record")
    signal_ids: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    with Session(manager.engine) as session:
        for lead in leads:
            samples = np.arange(n_samples, dtype="<f4")
            arrays[lead] = samples
            signal_id = new_id("signal")
            relative, digest, _size = write_signal(signal_id, samples)
            signal = make_signal(
                signal_id=signal_id,
                record_id=record_id,
                lead=lead,
                fs=fs,
                unit="mV",
                n_samples=n_samples,
                relative_path=relative,
                sha256=digest,
                created_at=now,
            )
            add_signal(session, signal, commit=False)
            signal_ids.append(signal.id)
        record = HealthRecord(
            id=record_id,
            memberId=member_id,
            recordType=record_type,
            moduleId=module_id,
            capturedAt=now,
            signalIds=signal_ids,
            createdAt=now,
            updatedAt=now,
        )
        add_record(session, record)
    return record_id, arrays


def test_create_declared_record_and_read_it_back(
    manager: ModuleManager, host: str, member: dict
) -> None:
    created = _create(manager, host, member["id"])
    assert created["moduleId"] == host
    assert created["recordType"] == HOST_TYPE
    assert created["payload"] == {"hr": 62}
    assert created["signalIds"] == []

    page = _call(manager, host, "records.query", {})
    assert page["total"] == 1
    item = page["items"][0]
    assert item["id"] == created["id"]
    assert item["capturedAt"] == "2026-10-30T10:00:00+08:00"
    assert item["tags"] == ["晨起"]
    assert item["notes"] == "心悸"
    # 摘要不含完整 payload，只给键与大小。
    assert "payload" not in item
    assert item["payloadSummary"]["keys"] == ["hr"]
    assert item["payloadSummary"]["bytes"] > 0

    fetched = _call(manager, host, "records.get", {"recordId": created["id"]})
    assert fetched["payload"] == {"hr": 62}
    assert fetched["memberId"] == member["id"]


def test_create_rejects_undeclared_type_and_extra_fields(
    manager: ModuleManager, host: str, member: dict
) -> None:
    with pytest.raises(ModuleError) as undeclared:
        _create(manager, host, member["id"], recordType=ECG_TYPE)
    assert undeclared.value.code == "INVALID_INPUT"

    with pytest.raises(ModuleError) as extra:
        _create(manager, host, member["id"], signalIds=["sig_00000000-0000-7000-8000-000000000000"])
    assert extra.value.code == "INVALID_INPUT"

    with pytest.raises(ModuleError) as missing_member:
        _create(manager, host, "mem_00000000-0000-7000-8000-000000000000")
    assert missing_member.value.code == "NOT_FOUND"


def test_visibility_is_limited_to_own_or_declared_types(
    manager: ModuleManager, host: str, other: str, member: dict
) -> None:
    own = _create(manager, host, member["id"])
    # 别的模块创建的 ECG 记录：host 既没创建也没声明。
    foreign_ecg = _insert_record(manager, member["id"], module_id=other, record_type=ECG_TYPE)
    # other 声明了 OTHER_TYPE，因此 host 也不可见。
    foreign_declared = _insert_record(
        manager, member["id"], module_id=other, record_type=OTHER_TYPE
    )
    # 核心创建的、但类型在 host 声明范围内的记录：可见。
    core_declared = _insert_record(manager, member["id"], module_id=None, record_type=HOST_TYPE)

    host_page = _call(manager, host, "records.query", {})
    host_ids = {item["id"] for item in host_page["items"]}
    assert host_ids == {own["id"], core_declared}
    assert foreign_ecg not in host_ids
    assert foreign_declared not in host_ids

    other_page = _call(manager, other, "records.query", {})
    other_ids = {item["id"] for item in other_page["items"]}
    assert other_ids == {foreign_ecg, foreign_declared}

    with pytest.raises(ModuleError) as denied:
        _call(manager, host, "records.get", {"recordId": foreign_ecg})
    assert denied.value.code == "NOT_FOUND"
    with pytest.raises(ModuleError) as denied_declared:
        _call(manager, host, "records.get", {"recordId": foreign_declared})
    assert denied_declared.value.code == "NOT_FOUND"


def test_query_filters_by_time_and_paginates(
    manager: ModuleManager, host: str, member: dict
) -> None:
    old = _create(manager, host, member["id"], capturedAt="2026-10-28T10:00:00+08:00")
    new = _create(manager, host, member["id"], capturedAt="2026-10-30T10:00:00+08:00")

    recent = _call(
        manager,
        host,
        "records.query",
        {"from": "2026-10-29T00:00:00+08:00", "limit": 1, "offset": 0},
    )
    assert recent["total"] == 1
    assert [item["id"] for item in recent["items"]] == [new["id"]]

    first_page = _call(manager, host, "records.query", {"limit": 1, "offset": 0})
    second_page = _call(manager, host, "records.query", {"limit": 1, "offset": 1})
    assert first_page["total"] == 2
    assert first_page["items"][0]["id"] != second_page["items"][0]["id"]
    assert {first_page["items"][0]["id"], second_page["items"][0]["id"]} == {
        old["id"],
        new["id"],
    }


def test_update_and_delete_only_own_records(
    manager: ModuleManager, host: str, other: str, member: dict
) -> None:
    created = _create(manager, host, member["id"])

    for method, params in (
        ("records.update", {"recordId": created["id"], "notes": "hijack"}),
        ("records.delete", {"recordId": created["id"]}),
    ):
        with pytest.raises(ModuleError) as denied:
            _call(manager, other, method, params)
        assert denied.value.code == "NOT_FOUND"

    updated = _call(
        manager,
        host,
        "records.update",
        {
            "recordId": created["id"],
            "payload": {"hr": 70},
            "notes": "已复核",
            "tags": ["复核"],
        },
    )
    assert updated["payload"] == {"hr": 70}
    assert updated["notes"] == "已复核"
    assert updated["tags"] == ["复核"]
    assert updated["moduleId"] == host
    assert updated["recordType"] == HOST_TYPE

    with pytest.raises(ModuleError) as immutable:
        _call(manager, host, "records.update", {"recordId": created["id"], "memberId": member["id"]})
    assert immutable.value.code == "INVALID_INPUT"

    manager.grant_permission(host, "records:delete")
    deleted = _call(manager, host, "records.delete", {"recordId": created["id"]})
    assert deleted["deleted"] is True
    with pytest.raises(ModuleError) as gone:
        _call(manager, host, "records.get", {"recordId": created["id"]})
    assert gone.value.code == "NOT_FOUND"
    assert _call(manager, host, "records.query", {})["total"] == 0


def test_delete_requires_grant_and_leaves_audit(
    manager: ModuleManager, host: str, member: dict
) -> None:
    created = _create(manager, host, member["id"])
    # records:delete 默认不授予，即使 manifest 已请求。
    with pytest.raises(ModuleError) as denied:
        _call(manager, host, "records.delete", {"recordId": created["id"]})
    assert denied.value.code == "PERMISSION_DENIED"

    events = manager.audit_events(module_id=host, action="core.call", limit=50)
    denied_event = next(
        event
        for event in events
        if event["detail"]["method"] == "records.delete" and event["detail"]["ok"] is False
    )
    assert denied_event["detail"]["errorCode"] == "PERMISSION_DENIED"
    assert denied_event["scope"] == "records:delete"


def test_signals_read_slices_and_checks_visibility(
    manager: ModuleManager, host: str, other: str, member: dict
) -> None:
    record_id, arrays = _insert_record_with_signals(
        manager, member["id"], module_id=host, record_type=HOST_TYPE, leads=("II", "V1")
    )

    window = _call(
        manager, host, "signals.read", {"recordId": record_id, "lead": "II", "start": 10, "count": 100}
    )
    assert window["lead"] == "II"
    assert window["fs"] == 500.0
    assert window["unit"] == "mV"
    assert window["startSample"] == 10
    assert window["count"] == 100
    assert window["totalSamples"] == 1_000
    assert window["samples"] == arrays["II"][10:110].tolist()

    with pytest.raises(ModuleError) as ambiguous:
        _call(manager, host, "signals.read", {"recordId": record_id})
    assert ambiguous.value.code == "INVALID_INPUT"
    assert ambiguous.value.detail["leads"] == ["II", "V1"]

    with pytest.raises(ModuleError) as no_lead:
        _call(manager, host, "signals.read", {"recordId": record_id, "lead": "V6"})
    assert no_lead.value.code == "NO_SIGNAL"

    with pytest.raises(ModuleError) as hidden:
        _call(manager, other, "signals.read", {"recordId": record_id, "lead": "II"})
    assert hidden.value.code == "NOT_FOUND"

    empty = _create(manager, host, member["id"])
    with pytest.raises(ModuleError) as no_signal:
        _call(manager, host, "signals.read", {"recordId": empty["id"]})
    assert no_signal.value.code == "NO_SIGNAL"


def test_signals_read_large_payload_uses_temp_handle(
    manager: ModuleManager, host: str, member: dict
) -> None:
    record_id, arrays = _insert_record_with_signals(
        manager, member["id"], module_id=host, record_type=HOST_TYPE, n_samples=70_000
    )
    result = _call(manager, host, "signals.read", {"recordId": record_id})
    assert "samples" not in result
    handle = result["fileHandle"]
    assert handle["format"] == "float32-le"
    assert handle["bytes"] == 70_000 * 4
    path = Path(handle["path"])
    assert path.is_file()
    assert np.frombuffer(path.read_bytes(), dtype="<f4").tolist() == arrays["II"].tolist()

    manager.shutdown()
    assert not path.exists()


def test_audit_records_success_and_failure_without_health_data(
    manager: ModuleManager, host: str, other: str, member: dict
) -> None:
    created = _create(
        manager,
        host,
        member["id"],
        notes="SECRET-NOTES",
        payload={"secret": "SECRET-PAYLOAD"},
    )
    with pytest.raises(ModuleError):
        _call(manager, host, "records.get", {"recordId": "rec_00000000-0000-7000-8000-000000000000"})

    events = manager.audit_events(module_id=host, action="core.call", limit=50)
    success = next(
        event
        for event in events
        if event["detail"]["method"] == "records.create" and event["detail"]["ok"] is True
    )
    assert success["detail"]["recordId"] == created["id"]
    assert success["scope"] == "records:write"

    failure = next(
        event
        for event in events
        if event["detail"]["method"] == "records.get" and event["detail"]["ok"] is False
    )
    assert failure["detail"]["errorCode"] == "NOT_FOUND"

    serialized = json.dumps(events, ensure_ascii=False)
    assert "SECRET-NOTES" not in serialized
    assert "SECRET-PAYLOAD" not in serialized


def test_denied_without_read_scope(manager: ModuleManager, tmp_path: Path, member: dict) -> None:
    _install(tmp_path, manager, "org.eclipsehealth.demo.readless", [HOST_TYPE], ["records:write"])
    with pytest.raises(ModuleError) as denied:
        _call(manager, "org.eclipsehealth.demo.readless", "records.query", {})
    assert denied.value.code == "PERMISSION_DENIED"
    assert denied.value.detail["scope"] == "records:read"


def test_unknown_record_and_bad_params(manager: ModuleManager, host: str) -> None:
    with pytest.raises(ModuleError) as missing:
        _call(manager, host, "records.get", {"recordId": "rec_00000000-0000-7000-8000-000000000000"})
    assert missing.value.code == "NOT_FOUND"

    with pytest.raises(ModuleError) as no_id:
        _call(manager, host, "records.get", {})
    assert no_id.value.code == "INVALID_INPUT"

    with pytest.raises(ModuleError) as bad_limit:
        _call(manager, host, "records.query", {"limit": 10_000})
    assert bad_limit.value.code == "INVALID_INPUT"

    with pytest.raises(ModuleError) as bad_time:
        _call(manager, host, "records.query", {"from": "yesterday"})
    assert bad_time.value.code == "INVALID_INPUT"
