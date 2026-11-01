"""Registry smoke test: Stage F routers must be reachable from the real app."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_stage_f_routes_are_mounted(client: TestClient) -> None:
    for path in (
        "/api/v1/scores",
        "/api/v1/suggestions",
        "/api/v1/exercises",
        "/api/v1/memory",
        "/api/v1/coach/context",
        "/api/v1/ohs/settings",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"
