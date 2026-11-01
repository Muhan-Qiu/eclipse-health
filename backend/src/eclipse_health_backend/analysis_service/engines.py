"""分析引擎注册表（C7 / A3）。

引擎目录是前端与助手的唯一事实源：引擎 ID、所属模块、模型标识与可用性
都由这里给出，API 层不再写死引擎列表。

引擎来源：

- 内置 Cardia（``cardia``），不变；
- 已安装且启用的 ``analysis-model`` 模块贡献的本地 ONNX 模型，
  引擎 ID 为 ``<moduleId>:<modelId>``，与内置 ID 天然不冲突。

模块引擎只读取模块目录里的文件，不启动 worker、不联网。Cardia 模块本身
仍走内置路径，不在这里重复登记。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bridge import (
    CARDIA_ENGINE,
    CARDIA_MODEL_ID,
    CARDIA_MODEL_VERSION,
    CARDIA_MODULE_ID,
    CARDIA_SOURCE_DIR,
)

logger = logging.getLogger(__name__)

_CARDIA_NAME = "Cardia 2.0"
_CARDIA_MODEL_RELATIVE = "models/cardia_k4_best_sim.onnx"

_VERIFY_LOCK = threading.Lock()
_VERIFY_CACHE: dict[tuple[str, int, int, str], bool] = {}
_VERIFY_CACHE_LIMIT = 256


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


@dataclass(frozen=True)
class ModuleModelSpec:
    """模块引擎的执行参数（仅核心内部使用，不进入 API 形状）。"""

    engine_id: str
    module_id: str
    module_version: str
    module_dir: Path
    model_id: str
    model_name: str
    model: dict[str, Any]
    model_path: Path
    model_relative_path: str
    model_sha256: str


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


# ---------------------------------------------------------------------- 模块扫描
def _module_manager() -> Any:
    """延迟导入，避免 API 层导入分析服务时连带初始化模块内核。"""
    from ..modules.api import get_manager

    return get_manager()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_matches(path: Path, expected: str) -> bool:
    """按 (路径, mtime, 大小, 期望值) 缓存校验结果，避免每次目录请求重算大模型。"""
    try:
        stat = path.stat()
    except OSError:
        return False
    key = (str(path), stat.st_mtime_ns, stat.st_size, expected)
    with _VERIFY_LOCK:
        cached = _VERIFY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        actual = _sha256_file(path)
    except OSError:
        return False
    matched = actual == expected
    with _VERIFY_LOCK:
        if len(_VERIFY_CACHE) >= _VERIFY_CACHE_LIMIT:
            _VERIFY_CACHE.clear()
        _VERIFY_CACHE[key] = matched
    return matched


def _verify_files(
    module_dir: Path, model: dict[str, Any]
) -> tuple[str | None, str | None, Path | None, str | None]:
    """校验 ``files[]``；返回 ``(reason, onnxRel, onnxPath, onnxSha)``。"""
    files = model.get("files")
    if not isinstance(files, list) or not files:
        return "模块未声明模型文件", None, None, None
    root = module_dir.resolve()
    onnx: tuple[str, Path, str] | None = None
    for entry in files:
        if not isinstance(entry, dict):
            return "模型文件清单格式非法", None, None, None
        relative = str(entry.get("path") or "").replace("\\", "/")
        expected = str(entry.get("sha256") or "").strip().lower()
        if not relative or len(expected) != 64:
            return "模型文件清单缺少 path/sha256", None, None, None
        target = (module_dir / relative).resolve()
        if root not in target.parents:
            return f"模型文件路径越界：{relative[-120:]}", None, None, None
        if not target.is_file():
            return f"模型文件缺失：{relative[-120:]}", None, None, None
        if not _sha256_matches(target, expected):
            return f"模型文件校验失败：{relative[-120:]}", None, None, None
        if onnx is None and relative.lower().endswith(".onnx"):
            onnx = (relative, target, expected)
    if onnx is None:
        return "模型清单中没有 .onnx 文件", None, None, None
    return None, onnx[0], onnx[1], onnx[2]


def _read_manifest(module_dir: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads((module_dir / "module.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _module_entries() -> list[tuple[EngineDescriptor, ModuleModelSpec | None]]:
    try:
        manager = _module_manager()
        modules = manager.list_modules()
        modules_root = Path(manager.modules_root)
    except Exception:
        logger.debug("module engine scan skipped", exc_info=True)
        return []

    entries: list[tuple[EngineDescriptor, ModuleModelSpec | None]] = []
    for summary in modules:
        module_id = str(summary.get("id") or "")
        if not module_id or module_id == CARDIA_MODULE_ID:
            continue
        if summary.get("type") != "analysis-model" or not summary.get("enabled"):
            continue
        version = str(summary.get("version") or "")
        module_dir = modules_root / module_id / version
        manifest = _read_manifest(module_dir)
        if manifest is None:
            continue
        contributes = manifest.get("contributes") or {}
        models = contributes.get("models") if isinstance(contributes, dict) else None
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict) or model.get("format") != "onnx":
                continue
            model_id = str(model.get("id") or "")
            if not model_id:
                continue
            engine_id = f"{module_id}:{model_id}"
            reason, relative, path, sha = _verify_files(module_dir, model)
            descriptor = EngineDescriptor(
                id=engine_id,
                name=str(model.get("name") or model_id),
                module_id=module_id,
                model_id=model_id,
                model_version=version,
                available=reason is None,
                reason=reason,
            )
            spec = None
            if reason is None and relative and path and sha:
                spec = ModuleModelSpec(
                    engine_id=engine_id,
                    module_id=module_id,
                    module_version=version,
                    module_dir=module_dir,
                    model_id=model_id,
                    model_name=descriptor.name,
                    model=model,
                    model_path=path,
                    model_relative_path=relative,
                    model_sha256=sha,
                )
            entries.append((descriptor, spec))
    return entries


def _module_specs() -> dict[str, ModuleModelSpec]:
    entries = _module_entries()
    return {descriptor.id: spec for descriptor, spec in entries if spec is not None}


# ---------------------------------------------------------------------- 公开接口
def list_engines() -> list[EngineDescriptor]:
    """返回当前安装包注册的全部引擎（含不可用的，便于 UI 提示原因）。"""
    return [_cardia_descriptor(), *[descriptor for descriptor, _ in _module_entries()]]


def get_engine(engine_id: str) -> EngineDescriptor | None:
    for descriptor in list_engines():
        if descriptor.id == engine_id:
            return descriptor
    return None


def get_module_model_spec(engine_id: str) -> ModuleModelSpec | None:
    """模块引擎的执行参数；内置或不可用引擎返回 None。"""
    if engine_id == CARDIA_ENGINE:
        return None
    return _module_specs().get(engine_id)


__all__ = [
    "EngineDescriptor",
    "ModuleModelSpec",
    "get_engine",
    "get_module_model_spec",
    "list_engines",
]
