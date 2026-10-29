"""Ollama 实测（可选）：默认跳过，设置 ``EH_TEST_OLLAMA=1`` 且本机已跑 Ollama 时执行。"""

from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.slow
def test_ollama_reachable() -> None:
    if os.environ.get("EH_TEST_OLLAMA") != "1":
        pytest.skip("set EH_TEST_OLLAMA=1 to run against http://127.0.0.1:11434")
    try:
        response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"ollama not running: {type(exc).__name__}")
    assert response.status_code == 200
