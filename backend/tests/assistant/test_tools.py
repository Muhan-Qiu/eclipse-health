"""只读工具：最小切片、越权、软删除、趋势能力探测。"""

from __future__ import annotations

import json
from typing import Any

from assistant_helpers import create_record, seed_analysis
from fastapi.testclient import TestClient

from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.llm.tools import TOOL_NAMES, ToolBox


def _call(member_id: str, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    with session_scope() as session:
        return ToolBox(session, member_id).execute(name, args or {})


def test_list_records_has_no_notes_or_waveform(
    client: TestClient, default_member: dict
) -> None:
    create_record(client, default_member["id"], notes="绝不外传的备注")
    outcome = _call(default_member["id"], "list_records", {"limit": 5})
    assert outcome["ok"] is True
    text = json.dumps(outcome["result"], ensure_ascii=False)
    assert "绝不外传的备注" not in text
    assert "samples" not in text
    # 标签也可能是敏感描述，只允许数量
    assert "synthetic" not in text
    assert outcome["result"]["count"] == 1
    assert outcome["citations"][0]["kind"] == "record"


def test_get_record_is_member_scoped(client: TestClient, default_member: dict) -> None:
    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    foreign = create_record(client, other["id"])
    outcome = _call(default_member["id"], "get_record", {"recordId": foreign["id"]})
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "NOT_FOUND"
    # 数据里也不能出现别人记录的痕迹
    assert foreign["id"] not in json.dumps(outcome, ensure_ascii=False)


def test_deleted_record_is_not_found(client: TestClient, default_member: dict) -> None:
    record = create_record(client, default_member["id"])
    assert client.delete(f"/api/v1/records/{record['id']}").status_code in {200, 204}
    outcome = _call(default_member["id"], "get_record", {"recordId": record["id"]})
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "NOT_FOUND"


def test_analysis_and_measurements(
    client: TestClient, default_member: dict, record_with_analysis: dict
) -> None:
    analysis_id = record_with_analysis["analysisId"]
    analysis = _call(default_member["id"], "get_analysis", {"analysisId": analysis_id})
    assert analysis["ok"] is True
    assert analysis["result"]["status"] == "completed"
    assert analysis["result"]["measurementsIncluded"] is False
    assert "beats" not in analysis["result"]

    measurements = _call(
        default_member["id"], "get_measurements", {"analysisId": analysis_id}
    )
    assert measurements["ok"] is True
    codes = {item["code"] for item in measurements["result"]["items"]}
    assert {"heart_rate_mean", "rmssd", "n_ratio"} <= codes
    assert measurements["citations"][0]["kind"] == "analysis"


def test_analysis_of_foreign_member_is_not_found(
    client: TestClient, default_member: dict
) -> None:
    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    foreign_record = create_record(client, other["id"])
    foreign_analysis = seed_analysis(foreign_record["id"])
    outcome = _call(default_member["id"], "get_analysis", {"analysisId": foreign_analysis})
    assert outcome["ok"] is False
    assert outcome["result"]["error"]["code"] == "NOT_FOUND"


def test_invalid_arguments(default_member: dict) -> None:
    missing = _call(default_member["id"], "get_record", {})
    assert missing["ok"] is False
    assert missing["result"]["error"]["code"] == "INVALID_ARGUMENT"

    unknown = _call(default_member["id"], "drop_table", {})
    assert unknown["ok"] is False
    assert unknown["result"]["error"]["code"] == "UNKNOWN_TOOL"


def test_trends_tool_degrades_gracefully(
    client: TestClient, default_member: dict, record_with_analysis: dict
) -> None:
    outcome = _call(
        default_member["id"], "get_trends", {"metrics": ["heart_rate_mean"], "days": 30}
    )
    assert outcome["ok"] is True
    result = outcome["result"]
    assert "available" in result
    if result["available"]:
        assert result["series"][0]["metric"] == "heart_rate_mean"
        assert result["series"][0]["points"][0]["value"] == 72.0

    unknown_metric = _call(default_member["id"], "get_trends", {"metrics": ["nope"]})
    if result["available"]:
        assert unknown_metric["ok"] is False
        assert unknown_metric["result"]["error"]["code"] == "INVALID_ARGUMENT"


def test_model_card_tool(client: TestClient, default_member: dict) -> None:
    outcome = _call(default_member["id"], "get_model_card")
    assert outcome["ok"] is True
    assert "available" in outcome["result"]
    assert "status" in outcome["result"]


def test_analysis_control_tools_are_registered() -> None:
    assert {
        "get_analysis_queue",
        "list_analyses",
        "start_analysis",
        "cancel_analysis",
        "retry_analysis",
        "pause_analysis_queue",
        "resume_analysis_queue",
        "recover_stuck_analyses",
    } <= set(TOOL_NAMES)


def test_analysis_queue_and_pause_resume(client: TestClient, default_member: dict) -> None:
    queue = _call(default_member["id"], "get_analysis_queue")
    assert queue["ok"] is True
    assert "paused" in queue["result"]
    assert "engine" in queue["result"]

    paused = _call(default_member["id"], "pause_analysis_queue")
    assert paused["ok"] is True and paused["result"]["paused"] is True
    try:
        assert _call(default_member["id"], "get_analysis_queue")["result"]["paused"] is True
    finally:
        resumed = _call(default_member["id"], "resume_analysis_queue")
    assert resumed["ok"] is True
    assert resumed["result"]["paused"] is False


def test_start_analysis_validates_ownership_and_signal(
    client: TestClient, default_member: dict, empty_record: dict
) -> None:
    no_signal = _call(
        default_member["id"], "start_analysis", {"recordId": empty_record["id"]}
    )
    assert no_signal["ok"] is False
    assert no_signal["result"]["error"]["code"] == "NO_SIGNAL"

    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    foreign = create_record(client, other["id"])
    foreign_result = _call(
        default_member["id"], "start_analysis", {"recordId": foreign["id"]}
    )
    assert foreign_result["ok"] is False
    assert foreign_result["result"]["error"]["code"] == "NOT_FOUND"


def test_cancel_and_retry_are_member_scoped(
    client: TestClient, default_member: dict
) -> None:
    other = client.post("/api/v1/members", json={"displayName": "Other"}).json()
    foreign_record = create_record(client, other["id"])
    foreign_analysis = seed_analysis(foreign_record["id"])
    for name in ("cancel_analysis", "retry_analysis"):
        outcome = _call(
            default_member["id"], name, {"analysisId": foreign_analysis}
        )
        assert outcome["ok"] is False
        assert outcome["result"]["error"]["code"] == "NOT_FOUND"


def test_recover_stuck_tool(client: TestClient, default_member: dict) -> None:
    outcome = _call(default_member["id"], "recover_stuck_analyses", {"maxAgeSeconds": 0})
    assert outcome["ok"] is True
    assert outcome["result"]["recovered"] >= 0
