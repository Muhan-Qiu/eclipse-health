"""B4-07 · 手动指标 CRUD、过滤、软删除与范围校验。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/metrics"
RECORD_TYPE = "org.eclipsehealth.metric"


def _post(client: TestClient, kind: str, values: dict, measured_at: str, **extra):
    return client.post(
        BASE,
        json={"kind": kind, "measuredAt": measured_at, "values": values, **extra},
    )


def test_create_all_kinds(client: TestClient, default_member: dict) -> None:
    cases = [
        ("blood_pressure", {"systolic": 120, "diastolic": 78}, "mmHg"),
        ("weight", {"weight": 62.5}, "kg"),
        ("spo2", {"spo2": 97}, "%"),
        ("glucose", {"glucose": 5.4}, "mmol/L"),
    ]
    for index, (kind, values, unit) in enumerate(cases):
        response = _post(
            client, kind, values, f"2026-10-2{index + 1}T08:00:00+08:00"
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["kind"] == kind
        assert body["values"] == values
        assert body["unit"] == unit
        assert body["memberId"] == default_member["id"]
        assert body["warnings"] == []


def test_abnormal_values_only_warn(client: TestClient) -> None:
    response = _post(
        client,
        "blood_pressure",
        {"systolic": 190, "diastolic": 100},
        "2026-10-20T08:00:00+08:00",
    )
    assert response.status_code == 201, response.text
    codes = {item["code"] for item in response.json()["warnings"]}
    assert {"systolic_high", "diastolic_high"} <= codes

    # 收缩压不高于舒张压属于可疑输入，但契约要求只警告、不拒绝。
    suspicious = _post(
        client,
        "blood_pressure",
        {"systolic": 80, "diastolic": 90},
        "2026-10-20T08:00:00+08:00",
    )
    assert suspicious.status_code == 201
    assert "systolic_not_above_diastolic" in {
        item["code"] for item in suspicious.json()["warnings"]
    }


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        ("spo2", {"spo2": 120}),
        ("glucose", {"glucose": 0}),
        ("blood_pressure", {"systolic": 120}),
        ("weight", {"weight": 62, "extra": 1}),
    ],
)
def test_invalid_values_rejected(client: TestClient, kind: str, values: dict) -> None:
    response = _post(client, kind, values, "2026-10-20T08:00:00+08:00")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_metric_values"


def test_list_filters_time_and_pagination(client: TestClient) -> None:
    _post(client, "blood_pressure", {"systolic": 120, "diastolic": 80}, "2026-10-01T08:00:00Z")
    _post(client, "weight", {"weight": 60}, "2026-10-05T08:00:00Z")
    _post(client, "weight", {"weight": 61}, "2026-10-09T08:00:00Z")
    _post(client, "spo2", {"spo2": 97}, "2026-10-12T08:00:00Z")

    page = client.get(BASE).json()
    assert page["total"] == 4
    assert [item["kind"] for item in page["items"]] == [
        "spo2",
        "weight",
        "weight",
        "blood_pressure",
    ]

    weights = client.get(BASE, params={"kind": "weight"}).json()
    assert weights["total"] == 2

    window = client.get(
        BASE,
        params={"from": "2026-10-05T00:00:00Z", "to": "2026-10-09T23:59:59Z"},
    ).json()
    assert window["total"] == 2

    first = client.get(BASE, params={"limit": 2, "offset": 0}).json()
    second = client.get(BASE, params={"limit": 2, "offset": 2}).json()
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_patch_metric(client: TestClient) -> None:
    created = _post(
        client, "weight", {"weight": 60}, "2026-10-20T08:00:00+08:00", notes="morning"
    ).json()
    response = client.patch(
        f"{BASE}/{created['id']}",
        json={
            "values": {"weight": 61.2},
            "notes": "after breakfast",
            "measuredAt": "2026-10-20T09:00:00+08:00",
            "timezone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["values"] == {"weight": 61.2}
    assert body["notes"] == "after breakfast"
    assert body["timezone"] == "Asia/Shanghai"

    # kind 不可变：用血压形状更新体重应失败
    bad = client.patch(
        f"{BASE}/{created['id']}",
        json={"values": {"systolic": 120, "diastolic": 80}},
    )
    assert bad.status_code == 422


def test_delete_is_soft(client: TestClient) -> None:
    created = _post(
        client, "spo2", {"spo2": 96}, "2026-10-20T08:00:00+08:00"
    ).json()
    assert client.delete(f"{BASE}/{created['id']}").status_code == 204

    assert client.get(BASE).json()["total"] == 0
    assert client.delete(f"{BASE}/{created['id']}").status_code == 404
    assert client.patch(f"{BASE}/{created['id']}", json={"notes": "x"}).status_code == 404

    # 软删除只影响列表，底层记录仍在（includeDeleted 可查）
    records = client.get(
        "/api/v1/records",
        params={"recordType": RECORD_TYPE, "includeDeleted": "true"},
    ).json()
    assert records["total"] == 1


def test_metric_is_record_without_signal(client: TestClient) -> None:
    created = _post(
        client, "glucose", {"glucose": 6.1}, "2026-10-20T08:00:00+08:00", notes="fasting"
    ).json()
    records = client.get("/api/v1/records", params={"recordType": RECORD_TYPE}).json()
    assert records["total"] == 1
    record = records["items"][0]
    assert record["id"] == created["id"]
    assert record["moduleId"] is None
    assert record["signalIds"] == []
    assert record["source"]["kind"] == "manual"
    assert record["payload"] == {"kind": "glucose", "values": {"glucose": 6.1}}
    assert record["notes"] == "fasting"


def test_unknown_member(client: TestClient) -> None:
    response = client.post(
        BASE,
        json={
            "kind": "weight",
            "measuredAt": "2026-10-20T08:00:00Z",
            "values": {"weight": 60},
            "memberId": "mem_missing",
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "member_not_found"


def test_empty_first_run(client: TestClient) -> None:
    page = client.get(BASE).json()
    assert page == {"items": [], "total": 0, "limit": 50, "offset": 0}
