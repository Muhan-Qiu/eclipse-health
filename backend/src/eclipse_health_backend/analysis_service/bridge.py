"""Cardia ``analysis-model`` 模块的宿主侧桥接。

职责：确保模块已安装、触发后台预热并轮询就绪、发起 ``analyze`` RPC、
把结果文件（大 JSON）读回。分析业务错误（心搏不足、信号非法）由模块以
``{"error": {"code", "message"}}`` 结果返回，传输层错误仍走 JSON-RPC error。
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..modules import package as module_package
from ..modules.errors import ModuleError
from ..settings import BACKEND_ROOT

logger = logging.getLogger(__name__)

CARDIA_MODULE_ID = "org.eclipsehealth.cardia"
CARDIA_MODEL_ID = "cardia-2.0"
CARDIA_MODEL_VERSION = "2.0.0"
CARDIA_ENGINE = "cardia"

if getattr(sys, "frozen", False):
    # 冻结后 BACKEND_ROOT 位于 _internal，随包源码在 _MEIPASS/modules/official/cardia。
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    CARDIA_SOURCE_DIR = _BUNDLE_ROOT / "modules" / "official" / "cardia"
else:
    CARDIA_SOURCE_DIR = BACKEND_ROOT.parent / "modules" / "official" / "cardia"

WARMUP_POLL_S = 2.0
DEFAULT_WARM_TIMEOUT_S = 900.0

ManagerFactory = Callable[[], Any]


class CardiaBridge:
    """模块管理器之上的薄封装；管理器由 ``modules.api.get_manager`` 提供。"""

    def __init__(
        self,
        manager_factory: ManagerFactory,
        *,
        auto_install: bool = True,
        warm_timeout_s: float = DEFAULT_WARM_TIMEOUT_S,
        poll_interval_s: float = WARMUP_POLL_S,
    ) -> None:
        self._manager_factory = manager_factory
        self.auto_install = auto_install
        self.warm_timeout_s = warm_timeout_s
        self.poll_interval_s = poll_interval_s
        self.installed_here = False

    @property
    def manager(self) -> Any:
        return self._manager_factory()

    # ------------------------------------------------------------------ 安装
    def ensure_installed(self) -> dict[str, Any]:
        manager = self.manager
        try:
            return manager.get_module(CARDIA_MODULE_ID)
        except ModuleError as exc:
            if exc.code != "MODULE_NOT_FOUND":
                raise
        if not self.auto_install:
            raise ModuleError(
                "MODULE_NOT_FOUND", "Cardia 模块未安装（EH_CARDIA_AUTO_INSTALL=0）"
            )
        summary = self.install_from_source()
        self.installed_here = True
        return summary

    def install_from_source(self) -> dict[str, Any]:
        """从仓库内 ``modules/official/cardia`` 打包安装；开发期免手工装包。"""
        manifest_path = CARDIA_SOURCE_DIR / "module.json"
        if not manifest_path.is_file():
            raise ModuleError(
                "MODULE_NOT_FOUND", "缺少内置 Cardia 模块目录，无法自动安装"
            )
        with tempfile.TemporaryDirectory(prefix="eh-cardia-pack-") as temp_dir:
            staging = Path(temp_dir) / "cardia"
            shutil.copytree(
                CARDIA_SOURCE_DIR,
                staging,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
            # 运行时从源码目录直接打包：以源码为准重新生成校验和，
            # 发布包仍由 scripts/pack_cardia.py 产出（commit 的 checksums.json）。
            module_package.write_checksums(staging)
            archive = Path(temp_dir) / "cardia.ehmod"
            module_package.pack_directory(staging, archive)
            logger.info("installing bundled cardia module from %s", CARDIA_SOURCE_DIR)
            return self.manager.install(archive, enable=True)

    # ------------------------------------------------------------------ 预热
    def warmup(self) -> float:
        """触发模块内后台预热并轮询；返回本次预热耗时（秒）。"""
        self.ensure_installed()
        manager = self.manager
        manager.call(CARDIA_MODULE_ID, "warmup", {})
        deadline = time.monotonic() + self.warm_timeout_s
        while time.monotonic() < deadline:
            health = manager.call(CARDIA_MODULE_ID, "health", {})
            if not isinstance(health, dict):
                raise ModuleError("MODULE_ERROR", "Cardia 模块健康检查返回非法结构")
            if health.get("error"):
                raise ModuleError("MODEL_LOAD_FAILED", str(health["error"])[:200])
            if health.get("warm"):
                seconds = health.get("warmupSeconds")
                return float(seconds) if isinstance(seconds, (int, float)) else 0.0
            time.sleep(self.poll_interval_s)
        raise ModuleError("MODULE_TIMEOUT", "Cardia 模块预热超时")

    def health(self) -> dict[str, Any]:
        result = self.manager.call(CARDIA_MODULE_ID, "health", {})
        return result if isinstance(result, dict) else {}

    def model_card(self) -> dict[str, Any]:
        """manifest 中 ``contributes.models[0]`` 的摘要，供 ``GET /engine`` 使用。"""
        try:
            module = self.manager.get_module(CARDIA_MODULE_ID)
        except ModuleError:
            return {}
        return {
            "moduleId": module.get("id"),
            "name": module.get("name"),
            "version": module.get("version"),
        }

    # ------------------------------------------------------------------ 分析
    def analyze(self, request: dict[str, Any]) -> dict[str, Any]:
        result = self.manager.call(CARDIA_MODULE_ID, "analyze", request)
        if not isinstance(result, dict):
            raise ModuleError("MODULE_ERROR", "Cardia 模块返回了非对象结果")
        reference = result.get("resultRef")
        if isinstance(reference, dict):
            return _read_result_file(reference)
        return result


def _read_result_file(reference: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(reference.get("path") or ""))
    expected = str(reference.get("sha256") or "")
    try:
        blob = path.read_bytes()
    except OSError as exc:
        raise ModuleError("MODULE_ERROR", "分析结果文件不可读") from exc
    actual = hashlib.sha256(blob).hexdigest()
    if expected and actual != expected:
        raise ModuleError("MODULE_ERROR", "分析结果文件校验失败")
    try:
        payload = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModuleError("MODULE_ERROR", "分析结果文件不是合法 JSON") from exc
    finally:
        path.unlink(missing_ok=True)
    if not isinstance(payload, dict):
        raise ModuleError("MODULE_ERROR", "分析结果文件顶层不是对象")
    return payload


__all__ = [
    "CARDIA_ENGINE",
    "CARDIA_MODEL_ID",
    "CARDIA_MODEL_VERSION",
    "CARDIA_MODULE_ID",
    "CARDIA_SOURCE_DIR",
    "CardiaBridge",
]
