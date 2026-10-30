"""分析引擎注册表（C7）。

引擎目录是前端与助手的唯一事实源：引擎 ID、所属模块、模型标识与可用性
都由这里给出，API 层不再写死引擎列表。当前只注册内置的 Cardia；后续
ONNX 加载器接入时在这里追加即可，调用方无需改动。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bridge import (
    CARDIA_ENGINE,
    CARDIA_MODEL_ID,
    CARDIA_MODEL_VERSION,
    CARDIA_MODULE_ID,
    CARDIA_SOURCE_DIR,
)

_CARDIA_NAME = "Cardia 2.0"
_CARDIA_MODEL_RELATIVE = "models/cardia_k4_best_sim.onnx"


@dataclass(frozen=True)
class EngineDescriptor:
    """一个可被选中的分析引擎。``reason`` 仅在不可用时给出用户可读原因。"""

    id: str
    name: str
    module_id: str
    model_id: str
    model_version: str
    available: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "moduleId": self.module_id,
            "modelId": self.model_id,
            "modelVersion": self.model_version,
            "available": self.available,
            "reason": self.reason,
        }


def _cardia_descriptor() -> EngineDescriptor:
    # 可用性只看本机内置模型是否齐全；运行时就绪状态仍由 GET /engine 单独给出。
    if not (CARDIA_SOURCE_DIR / "module.json").is_file():
        reason = "缺少内置 Cardia 模块清单"
        available = False
    elif not (CARDIA_SOURCE_DIR / _CARDIA_MODEL_RELATIVE).is_file():
        reason = "缺少 Cardia ONNX 模型文件"
        available = False
    else:
        reason = None
        available = True
    return EngineDescriptor(
        id=CARDIA_ENGINE,
        name=_CARDIA_NAME,
        module_id=CARDIA_MODULE_ID,
        model_id=CARDIA_MODEL_ID,
        model_version=CARDIA_MODEL_VERSION,
        available=available,
        reason=reason,
    )


def list_engines() -> list[EngineDescriptor]:
    """返回当前安装包注册的全部引擎（含不可用的，便于 UI 提示原因）。"""
    return [_cardia_descriptor()]


def get_engine(engine_id: str) -> EngineDescriptor | None:
    for descriptor in list_engines():
        if descriptor.id == engine_id:
            return descriptor
    return None


__all__ = ["EngineDescriptor", "get_engine", "list_engines"]
