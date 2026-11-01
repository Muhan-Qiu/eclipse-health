from __future__ import annotations

from pathlib import Path


def test_health_reports_ready_state(client, data_dir: Path) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["version"]
    assert body["migrations"] == ["0001_core"]
    assert body["databasePath"] == str(data_dir / "eclipse_health.sqlite3")
    assert Path(body["databasePath"]).exists()
    assert body["startedAt"] and body["now"]


def test_openapi_is_served(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/members" in paths
    assert "/api/v1/records" in paths
    assert "/api/v1/records/{record_id}/signal" in paths


def test_unknown_route_returns_404(client) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
