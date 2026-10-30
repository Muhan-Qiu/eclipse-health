"""A1：内置 MIT-BIH 示例导入。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eclipse_health_backend.analysis_service import set_analysis_service

API = "/api/v1"


class _FakeService:
    def __init__(self, *, fail: bool = False, analysis_id: str = "ana_sample") -> None:
        self.fail = fail
        self.analysis_id = analysis_id

    def submit(self, **kwargs):
        if self.fail:
            raise RuntimeError("engine exploded")
        return ({"analysisId": self.analysis_id, "recordId": kwargs["record_id"]}, False)


@pytest.fixture()
def restore_service():
    yield
    set_analysis_service(None)


def test_sample_import_creates_real_record(client: TestClient) -> None:
    response = client.post(f"{API}/imports/samples/mitdb-100", json={})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recordId"].startswith("rec_")
    assert body["analysisId"] is None

    record = client.get(f"{API}/records/{body['recordId']}").json()
    assert record["metadata"]["sampleId"] == "mitdb-100"
    assert record["metadata"]["isSample"] is True
    assert record["source"]["kind"] == "import"
    assert record["leads"]
    assert record["signalIds"]
    assert record["samplingRate"] == 360.0
    assert not record.get("provenance", {}).get("fileNameHash")

    signals = client.get(f"{API}/records/{record['id']}/signals").json()
    assert len(signals) == len(record["leads"])
    raw = client.get(f"{API}/records/{record['id']}/signal", params={"lead": signals[0]["lead"]})
    assert raw.status_code == 200
    assert len(raw.content) == signals[0]["shape"][0] * 4


def test_unknown_sample_is_404(client: TestClient) -> None:
    response = client.post(f"{API}/imports/samples/mitdb-999", json={})
    assert response.status_code == 404
    assert response.json()["code"] == "sample_not_found"


def test_repeat_import_creates_two_records(client: TestClient) -> None:
    first = client.post(f"{API}/imports/samples/mitdb-200", json={}).json()
    second = client.post(f"{API}/imports/samples/mitdb-200", json={}).json()
    assert first["recordId"] != second["recordId"]
    page = client.get(f"{API}/records", params={"recordType": "org.eclipsehealth.ecg"}).json()
    sample_ids = [item["id"] for item in page["items"] if item["metadata"].get("isSample")]
    assert set(sample_ids) == {first["recordId"], second["recordId"]}


def test_start_analysis_returns_analysis_id(
    client: TestClient, restore_service
) -> None:
    set_analysis_service(_FakeService(analysis_id="ana_ok"))
    response = client.post(
        f"{API}/imports/samples/mitdb-208", json={"startAnalysis": True}
    )
    assert response.status_code == 201, response.text
    assert response.json()["analysisId"] == "ana_ok"


def test_start_analysis_failure_does_not_block_record(
    client: TestClient, restore_service
) -> None:
    set_analysis_service(_FakeService(fail=True))
    response = client.post(
        f"{API}/imports/samples/mitdb-208", json={"startAnalysis": True}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["analysisId"] is None
    assert client.get(f"{API}/records/{body['recordId']}").status_code == 200
