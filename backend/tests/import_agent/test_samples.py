"""端到端样例：CSV / HTML / PDF 跑通预览与提交。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from import_agent_helpers import (
    CSV_PULSE,
    CSV_SCRIPT,
    HTML_REPORT,
    HTML_SCRIPT,
    PDF_SCRIPT,
    ScriptedParseAdapter,
    build_pdf,
    commit,
    list_records,
    record_types,
    stream_run,
    upload_session,
)

from eclipse_health_backend.import_agent import store
from eclipse_health_backend.import_agent.tools import ToolBox

MOCK_ID = "llm_import_mock"


def _use_script(monkeypatch, code: str) -> None:
    monkeypatch.setattr(
        "eclipse_health_backend.import_agent.api.make_adapter",
        lambda _provider, _key: ScriptedParseAdapter(code),
    )


def _run_and_commit(client, monkeypatch, session_id: str, code: str) -> dict:
    _use_script(monkeypatch, code)
    status, events = stream_run(client, session_id, {"providerId": MOCK_ID})
    assert status == 200
    names = [name for name, _data in events]
    assert "preview" in names, names
    assert names[-1] == "done", names
    previews = [data for name, data in events if name == "preview"]
    assert previews and previews[-1]["total"] > 0
    response = commit(client, session_id)
    assert response.status_code == 200, response.text
    return response.json()


def test_csv_sample_end_to_end(client: TestClient, mock_provider, monkeypatch) -> None:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    result = _run_and_commit(client, monkeypatch, session["sessionId"], CSV_SCRIPT)
    assert result["created"] == 2
    assert result["counts"] == {"heart-rate": 2}

    items = list_records(client, "org.eclipsehealth.health.heart-rate")
    assert len(items) == 2
    assert items[0]["payload"]["kind"] == "heart-rate"
    assert items[0]["payload"]["evidence"]["file"] == "pulse.csv"
    assert items[0]["metadata"]["importSource"] == "import-agent"
    assert items[0]["provenance"]["adapterVersion"] == "import-agent/1.0.0"

    again = commit(client, session["sessionId"])
    assert again.status_code == 200
    body = again.json()
    assert body["duplicateCommit"] is True
    assert body["created"] == 2  # 首次结果原样返回，不再写库
    assert body["skipped"] == 0
    assert len(list_records(client, "org.eclipsehealth.health.heart-rate")) == 2

    # 提交后 input/work/output 已删除，meta 保留到 TTL。
    workspace = store.session_path(session["sessionId"])
    assert not (workspace / store.INPUT_DIR).exists()
    assert not (workspace / store.OUTPUT_DIR).exists()
    assert (workspace / store.META_FILE).is_file()


def test_html_sample_end_to_end(client: TestClient, mock_provider, monkeypatch) -> None:
    session = upload_session(client, {"report.html": HTML_REPORT})
    result = _run_and_commit(client, monkeypatch, session["sessionId"], HTML_SCRIPT)
    assert result["created"] == 2
    assert result["counts"] == {"heart-rate": 1, "blood-pressure": 1}

    bp = list_records(client, "org.eclipsehealth.health.blood-pressure")
    assert len(bp) == 1
    assert bp[0]["payload"]["value"] == {"systolic": 120.0, "diastolic": 80.0}
    assert bp[0]["unit"] == "mm[Hg]"


def test_pdf_sample_only_numeric_records(client: TestClient, mock_provider, monkeypatch) -> None:
    pdf = build_pdf(["Heart Rate: 72 bpm", "Blood Pressure: 120/80 mmHg"])
    session = upload_session(client, {"report.pdf": pdf})
    result = _run_and_commit(client, monkeypatch, session["sessionId"], PDF_SCRIPT)
    assert result["created"] == 2
    counts = record_types(client)
    assert counts.get("org.eclipsehealth.health.heart-rate") == 1
    assert counts.get("org.eclipsehealth.health.blood-pressure") == 1
    assert "org.eclipsehealth.ecg" not in counts


def test_pdf_ecg_proposal_is_rejected(client: TestClient, providers_file) -> None:
    pdf = build_pdf(["ECG report only"])
    session = upload_session(client, {"report.pdf": pdf})
    workspace, meta = store.load_session(session["sessionId"])
    box = ToolBox(session["sessionId"], meta)
    outcome = box.execute(
        "propose_records",
        {
            "records": [
                {
                    "kind": "ecg",
                    "value": {"samplingRate": 500, "lead": "II"},
                    "unit": "mV",
                    "startAt": "2026-10-30T10:00:00+08:00",
                    "source": {"kind": "app", "app": "PDF Report"},
                    "evidence": {"file": "report.pdf", "page": 1, "snippet": "ECG report only"},
                    "confidence": 0.5,
                }
            ]
        },
    )
    assert outcome.ok is True
    assert outcome.result["accepted"] == 0
    assert outcome.result["rejected"] == 1
    assert outcome.result["issues"][0]["code"] == "ecg_waveform_required"
    assert not store.load_proposals(workspace)


def test_illegal_record_and_unproposed_commit(client: TestClient, providers_file) -> None:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    workspace, meta = store.load_session(session["sessionId"])
    box = ToolBox(session["sessionId"], meta)

    rejected = box.execute(
        "propose_records",
        {
            "records": [
                {
                    "kind": "heart-rate",
                    "value": 72,
                    "unit": "bpm",
                    "startAt": "2026-10-30T08:00:00+08:00",
                    "source": {"kind": "app"},
                    "evidence": {"file": "pulse.csv"},
                    "confidence": 0.9,
                }
            ]
        },
    )
    assert rejected.result["rejected"] == 1
    assert rejected.result["issues"][0]["code"] == "evidence_incomplete"

    accepted = box.execute(
        "propose_records",
        {
            "records": [
                {
                    "kind": "heart-rate",
                    "value": 72,
                    "unit": "bpm",
                    "startAt": "2026-10-30T08:00:00+08:00",
                    "source": {"kind": "app"},
                    "evidence": {"file": "pulse.csv", "line": 2},
                    "confidence": 0.9,
                }
            ]
        },
    )
    assert accepted.result["accepted"] == 1
    assert store.load_proposals(workspace)

    response = commit(client, session["sessionId"], {"records": ["prp_" + "0" * 32]})
    assert response.status_code == 422
    assert response.json()["code"] == "record_not_proposed"


def test_ecg_waveform_commit(client: TestClient, providers_file) -> None:
    session = upload_session(client, {"ecg.csv": "time,voltage\n0,0.1\n"})
    _workspace, meta = store.load_session(session["sessionId"])
    box = ToolBox(session["sessionId"], meta)

    rows = ["time,voltage"]
    for index in range(1000):
        rows.append(f"{index / 500:.6f},{0.1 * ((index % 50) - 25) / 25:.6f}")
    written = box.execute("write_output", {"path": "ecg.csv", "content": "\n".join(rows)})
    assert written.ok is True

    proposal = {
        "kind": "ecg",
        "value": {"lead": "II"},
        "unit": "mV",
        "startAt": "2026-10-30T11:00:00+08:00",
        "endAt": "2026-10-30T11:00:02+08:00",
        "source": {"kind": "device", "device": "Test Watch"},
        "evidence": {"file": "ecg.csv", "locator": "rows 2-1001"},
        "confidence": 0.99,
        "waveform": {"file": "ecg.csv", "format": "csv", "column": 1, "timeColumn": 0},
    }
    proposed = box.execute("propose_records", {"records": [proposal]})
    assert proposed.ok is True
    assert proposed.result["accepted"] == 1, proposed.result

    response = commit(client, session["sessionId"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["counts"] == {"ecg": 1}

    items = list_records(client, "org.eclipsehealth.ecg")
    assert len(items) == 1
    record = items[0]
    assert record["payload"]["waveform"]["file"] == "ecg.csv"
    signal = client.get(f"/api/v1/records/{record['id']}/signal")
    assert signal.status_code == 200
    assert int(signal.headers["X-Signal-Samples"]) == 1000
    assert abs(float(signal.headers["X-Signal-Fs"]) - 500.0) < 1e-6


def test_same_file_is_idempotent_across_sessions(client: TestClient, providers_file) -> None:
    record = {
        "kind": "steps",
        "value": 1234,
        "unit": "count",
        "startAt": "2026-10-29T00:00:00+08:00",
        "endAt": "2026-10-29T23:59:59+08:00",
        "source": {"kind": "app", "app": "Test"},
        "evidence": {"file": "steps.csv", "line": 2},
        "confidence": 0.9,
    }
    created = []
    for _ in range(2):
        session = upload_session(client, {"steps.csv": "date,steps\n2026-10-29,1234\n"})
        _workspace, meta = store.load_session(session["sessionId"])
        box = ToolBox(session["sessionId"], meta)
        assert box.execute("propose_records", {"records": [record]}).result["accepted"] == 1
        response = commit(client, session["sessionId"])
        assert response.status_code == 200, response.text
        created.append(response.json())
    assert created[0]["created"] == 1
    assert created[1]["created"] == 0
    assert created[1]["skipped"] == 1
    assert len(list_records(client, "org.eclipsehealth.health.steps")) == 1


def test_ecg_waveform_output_prefix_is_accepted(client: TestClient, providers_file) -> None:
    """Agent 常写 output/ecg.csv；waveform.file 是相对 output/ 的路径。"""
    session = upload_session(client, {"ecg.csv": "time,voltage\n"})
    _workspace, meta = store.load_session(session["sessionId"])
    box = ToolBox(session["sessionId"], meta)
    rows = ["time,voltage"] + [f"{i / 500:.6f},{0.1 * ((i % 50) - 25) / 25:.6f}" for i in range(500)]
    assert box.execute("write_output", {"path": "ecg.csv", "content": "\n".join(rows)}).ok
    proposal = {
        "kind": "ecg",
        "value": {"lead": "I"},
        "unit": "mV",
        "startAt": "2026-10-30T11:00:00+08:00",
        "source": {"kind": "device", "device": "Agent"},
        "evidence": {"file": "ecg.csv", "locator": "rows 2-501"},
        "confidence": 0.9,
        "waveform": {
            "file": "output/ecg.csv",
            "format": "csv",
            "column": "voltage",
            "timeColumn": "time",
            "samplingRate": 500,
            "lead": "I",
        },
    }
    proposed = box.execute("propose_records", {"records": [proposal]})
    assert proposed.result["accepted"] == 1, proposed.result

    body = commit(client, session["sessionId"]).json()
    assert body["created"] == 1
    assert body["failed"] == 0


def test_failed_ecg_commit_keeps_session_retryable(client: TestClient, providers_file) -> None:
    """提交有失败记录时不能删除 output/，也不能标记 committed。"""
    session = upload_session(client, {"ecg.csv": "time,voltage\n"})
    workspace, meta = store.load_session(session["sessionId"])
    box = ToolBox(session["sessionId"], meta)
    proposal = {
        "kind": "ecg",
        "value": {"lead": "I"},
        "unit": "mV",
        "startAt": "2026-10-30T11:00:00+08:00",
        "source": {"kind": "device", "device": "Agent"},
        "evidence": {"file": "ecg.csv", "locator": "rows 2-501"},
        "confidence": 0.9,
        "waveform": {"file": "later.csv", "format": "csv", "column": 1, "timeColumn": 0},
    }
    assert box.execute("propose_records", {"records": [proposal]}).result["accepted"] == 1

    first = commit(client, session["sessionId"]).json()
    assert first["created"] == 0
    assert first["failed"] == 1
    assert first["errors"][0]["code"] == "ecg_waveform_missing"
    meta_after = store.read_meta(workspace)
    assert meta_after["status"] == "ready"
    assert (workspace / store.OUTPUT_DIR).is_dir()

    rows = ["time,voltage"] + [f"{i / 500:.6f},{0.1 * ((i % 50) - 25) / 25:.6f}" for i in range(500)]
    assert box.execute("write_output", {"path": "later.csv", "content": "\n".join(rows)}).ok
    second = commit(client, session["sessionId"]).json()
    assert second["created"] == 1
    assert second["failed"] == 0
