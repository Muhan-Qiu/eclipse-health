"""报告 API 边界：无分析 409、未知格式/模板 422、历史、下载、删除。"""

from __future__ import annotations

from pathlib import Path

import pytest
from reports_helpers import create_record, create_record_with_analysis

from eclipse_health_backend.settings import get_settings


def _generate(client, record_id: str, **payload):
    body = {"format": "pdf", "template": "detailed", "redact": True}
    body.update(payload)
    return client.post(f"/api/v1/records/{record_id}/reports", json=body)


def test_requires_completed_analysis(client, default_member):
    record = create_record(client, default_member["id"])
    response = _generate(client, record["id"])
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "analysis_required"
    assert body["details"]["recordId"] == record["id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"format": "docx", "template": "detailed"},
        {"format": "pdf", "template": "fancy"},
    ],
)
def test_unknown_format_or_template_is_422(client, default_member, payload):
    record, _ = create_record_with_analysis(client, default_member["id"])
    response = _generate(client, record["id"], **payload)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_unknown_record_is_404(client):
    response = _generate(client, "rec_00000000-0000-7000-8000-000000000000")
    assert response.status_code == 404
    assert response.json()["code"] == "record_not_found"


def test_history_lists_reports_newest_first(client, default_member):
    record, _ = create_record_with_analysis(client, default_member["id"])
    first = _generate(client, record["id"], template="simple").json()
    second = _generate(client, record["id"], format="png", template="detailed").json()

    response = client.get(f"/api/v1/records/{record['id']}/reports")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["reportId"] for item in body["items"]] == [second["reportId"], first["reportId"]]
    assert body["items"][0]["format"] == "png"
    assert body["items"][1]["template"] == "simple"


def test_delete_removes_metadata_and_file(client, default_member, data_dir: Path):
    record, _ = create_record_with_analysis(client, default_member["id"])
    body = _generate(client, record["id"]).json()
    report_path = get_settings().reports_dir / f"{body['reportId']}.pdf"
    assert report_path.is_file()

    response = client.delete(f"/api/v1/reports/{body['reportId']}")
    assert response.status_code == 204
    assert not report_path.exists()

    assert client.get(f"/api/v1/reports/{body['reportId']}").status_code == 404
    assert client.get(f"/api/v1/reports/{body['reportId']}/download").status_code == 404
    history = client.get(f"/api/v1/records/{record['id']}/reports").json()
    assert history["total"] == 0

    # 重复删除返回 404，而不是静默成功。
    assert client.delete(f"/api/v1/reports/{body['reportId']}").status_code == 404


def test_reports_of_missing_record_is_404(client):
    response = client.get(
        "/api/v1/records/rec_00000000-0000-7000-8000-000000000000/reports"
    )
    assert response.status_code == 404


def test_redaction_flag_roundtrip(client, default_member):
    record, _ = create_record_with_analysis(client, default_member["id"])
    redacted = _generate(client, record["id"], redact=True).json()
    plain = _generate(client, record["id"], redact=False).json()
    assert redacted["redacted"] is True
    assert plain["redacted"] is False
    assert redacted["reportId"] != plain["reportId"]
