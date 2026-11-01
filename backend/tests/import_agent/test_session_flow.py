"""会话生命周期、provider 选择与 Mock 运行。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from import_agent_helpers import API, CSV_PULSE, stream_run, upload_session

MOCK_ID = "llm_import_mock"


def _events(events):
    return [name for name, _data in events]


def test_create_get_list_and_delete(client: TestClient, providers_file) -> None:
    created = upload_session(client, {"a.csv": "x,y\n1,2\n", "b.json": "{}"})
    assert created["status"] == "created"
    assert created["fileCount"] == 2
    assert created["limits"]["network"] is False
    session_id = created["sessionId"]

    fetched = client.get(f"{API}/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["sessionId"] == session_id

    listed = client.get(f"{API}/sessions")
    assert listed.status_code == 200
    assert any(item["sessionId"] == session_id for item in listed.json()["items"])

    assert client.delete(f"{API}/sessions/{session_id}").status_code == 204
    assert client.get(f"{API}/sessions/{session_id}").status_code == 404


def test_upload_requires_a_file(client: TestClient, providers_file) -> None:
    response = client.post(f"{API}/sessions")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_upload_filename_is_sanitised(client: TestClient, providers_file) -> None:
    response = client.post(
        f"{API}/sessions",
        files={"files": ("../../evil.csv", CSV_PULSE.encode(), "text/csv")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["files"][0]["storedName"] == "evil.csv"


def test_run_without_provider_fails(client: TestClient, providers_file) -> None:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    response = client.post(f"{API}/sessions/{session['sessionId']}/run", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "provider_not_configured"


def test_run_with_unknown_provider(client: TestClient, mock_provider) -> None:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    response = client.post(
        f"{API}/sessions/{session['sessionId']}/run", json={"providerId": "llm_missing"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "provider_not_found"


def test_mock_provider_runs_full_tool_loop(client: TestClient, mock_provider) -> None:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    status, events = stream_run(client, session["sessionId"], {"providerId": MOCK_ID})
    assert status == 200
    names = _events(events)
    assert names[0] == "status"
    assert names[-1] == "done"
    calls = [data["name"] for name, data in events if name == "tool_call"]
    assert calls[:3] == ["list_files", "read_text_file", "finish"]
    done = events[-1][1]
    assert done["status"] == "ready"
    assert done["toolCalls"] == 3

    fetched = client.get(f"{API}/sessions/{session['sessionId']}").json()
    assert fetched["status"] == "ready"
    assert fetched["summary"]
    assert fetched["proposalCount"] == 0


def test_run_without_files_is_impossible(client: TestClient, mock_provider) -> None:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    assert client.get(f"{API}/sessions/{session['sessionId']}").json()["fileCount"] == 1
