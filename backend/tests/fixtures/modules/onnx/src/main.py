"""Test fixture module entry. The ONNX engine path never starts this worker."""

from __future__ import annotations

from typing import Any


def create_module() -> Any:
    return {"health": lambda: {"warm": True}}
