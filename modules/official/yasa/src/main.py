"""YASA 睡眠分期模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``analyze`` / ``stats`` / ``sleep.efficiency`` / ``deactivate``。

- ``analyze`` 接受已分期序列 ``stages``（离线计算效率），或内联 PSG ``signals`` + ``sf`` 调用 YASA；
- 大 PSG 建议由核心先裁成 30 秒 epoch 特征，数组单次 ≤ 20 万点，避免超 1MB 单行；
- 所有输出带「非医疗器械，不用于诊断」。
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any

from adapter import (
    NON_DIAGNOSTIC,
    AdapterError,
    parse_stages,
    sleep_efficiency,
    stage_rows,
    widget_stats,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.raphaelvallat.yasa")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
MAX_SAMPLES = 20_000_000


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, error: RpcError) -> None:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": error.code, "message": error.message},
    }
    if error.data:
        payload["error"]["data"] = error.data
    _write(payload)


def _channel(signals: dict[str, Any], name: str) -> Any:
    value = signals.get(name)
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise AdapterError("invalid_input", f"signals.{name} 必须是数组")
    if len(value) > MAX_SAMPLES:
        raise AdapterError("invalid_input", f"signals.{name} 超过 {MAX_SAMPLES} 点上限")
    for index, sample in enumerate(value[:10]):
        if isinstance(sample, bool) or not isinstance(sample, (int, float)):
            raise AdapterError("invalid_input", f"signals.{name}[{index}] 不是数值")
    return value


def _analyze(params: dict[str, Any]) -> dict[str, Any]:
    if params.get("stages") is not None:
        return sleep_efficiency(params.get("stages"), float(params.get("epochSeconds", 30)))

    signals = params.get("signals")
    if not isinstance(signals, dict):
        raise AdapterError("invalid_input", "需要 params.stages 或 params.signals")
    try:
        sf = float(params.get("sf") or 0)
    except (TypeError, ValueError):
        sf = 0.0
    if not math.isfinite(sf) or sf <= 0:
        raise AdapterError("invalid_input", "params.sf 缺失或非法")
    eeg = _channel(signals, "eeg")
    if eeg is None:
        raise AdapterError("invalid_input", "signals.eeg 缺失")
    eog = _channel(signals, "eog")
    emg = _channel(signals, "emg")

    try:
        import yasa
    except ImportError:
        return {"error": {"code": "dependency_missing", "message": "模块 venv 中缺少 yasa"}}

    try:
        model = yasa.SleepStaging(eeg=eeg, eog=eog, emg=emg, sf=sf)
        hypnogram = [str(item) for item in model.predict()]
        result = sleep_efficiency(hypnogram, float(params.get("epochSeconds", 30)))
        return {
            "source": "yasa",
            "hypnogram": hypnogram,
            "metrics": result,
            "stageRows": stage_rows(result["stageCounts"], result["epochSeconds"]),
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    except AdapterError:
        raise
    except Exception as exc:  # noqa: BLE001 - 上游库异常转业务错误
        return {"error": {"code": "analysis_failed", "message": f"{type(exc).__name__}: {exc}"[:300]}}


def _health() -> dict[str, Any]:
    version = None
    try:
        import yasa

        version = getattr(yasa, "__version__", None)
    except ImportError:
        pass
    return {"ok": True, "library": "yasa", "version": version, "nonDiagnostic": NON_DIAGNOSTIC}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, f"unsupported apiVersion {requested[:32]}", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "YASA · 睡眠分期",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "analyze", "stats", "sleep.efficiency", "deactivate"],
            "health": _health(),
        }
    if method == "warmup":
        return _health()
    if method == "health":
        return _health()
    if method == "analyze":
        return _analyze(params)
    if method == "stats":
        return widget_stats(params.get("stages"), float(params.get("epochSeconds", 30)))
    if method == "sleep.efficiency":
        return sleep_efficiency(parse_stages(params.get("stages")), float(params.get("epochSeconds", 30)))
    if method == "deactivate":
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        result = handle(str(method), params)
        _result(request_id, result)
        return method != "deactivate"
    except AdapterError as error:
        _error(request_id, RpcError(-32602, error.message, {"code": "INVALID_INPUT", "reason": error.code}))
        return True
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _error(None, RpcError(-32700, "parse error"))
            continue
        if not isinstance(message, dict) or "method" not in message or "id" not in message:
            continue
        if not _dispatch_and_reply(message):
            return 0
    return 0


def create_module() -> dict[str, Any]:
    return {"handle": handle}


if __name__ == "__main__":
    sys.exit(main())
