"""个性化记忆 GET/PUT、长度上限、开关与损坏回退。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from eclipse_health_backend.memory.storage import memory_context

BASE = "/api/v1/memory"


def test_empty_first_run(client: TestClient) -> None:
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == {"content": "", "enabled": False, "updatedAt": None}


def test_put_and_get_roundtrip(client: TestClient) -> None:
    response = client.put(BASE, json={"content": "喜欢晨跑\n对花粉过敏", "enabled": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"] == "喜欢晨跑\n对花粉过敏"
    assert body["enabled"] is True
    assert body["updatedAt"]

    fetched = client.get(BASE).json()
    assert fetched["content"] == body["content"]
    assert fetched["enabled"] is True
    assert fetched["updatedAt"] == body["updatedAt"]


def test_empty_content_allowed(client: TestClient) -> None:
    response = client.put(BASE, json={"content": "", "enabled": True})
    assert response.status_code == 200
    assert response.json()["content"] == ""
    assert memory_context() == ""


def test_length_limit(client: TestClient) -> None:
    too_long = client.put(BASE, json={"content": "x" * 20_001, "enabled": True})
    assert too_long.status_code == 422
    assert too_long.json()["code"] == "validation_error"

    at_limit = client.put(BASE, json={"content": "x" * 20_000, "enabled": True})
    assert at_limit.status_code == 200


def test_memory_context_respects_enabled(client: TestClient) -> None:
    client.put(BASE, json={"content": "每天 23:00 睡觉", "enabled": False})
    assert memory_context() == ""

    client.put(BASE, json={"content": "每天 23:00 睡觉", "enabled": True})
    assert memory_context() == "每天 23:00 睡觉"


def test_corrupt_file_falls_back(client: TestClient, data_dir: Path) -> None:
    (data_dir / "memory.json").write_text("{not json", encoding="utf-8")
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == {"content": "", "enabled": False, "updatedAt": None}
    assert memory_context() == ""


def test_invalid_shape_falls_back(client: TestClient, data_dir: Path) -> None:
    (data_dir / "memory.json").write_text(
        json.dumps({"content": 1, "enabled": "yes"}), encoding="utf-8"
    )
    assert client.get(BASE).json() == {
        "content": "",
        "enabled": False,
        "updatedAt": None,
    }


def test_overwrite_updates_timestamp(client: TestClient) -> None:
    first = client.put(BASE, json={"content": "a", "enabled": True}).json()
    second = client.put(BASE, json={"content": "b", "enabled": False}).json()
    assert second["content"] == "b"
    assert second["enabled"] is False
    assert second["updatedAt"] >= first["updatedAt"]
