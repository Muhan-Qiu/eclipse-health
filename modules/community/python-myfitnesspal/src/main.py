"""MyFitnessPal data-source 模块：stdio JSON-RPC 2.0，每行一条 JSON。

上游 ``myfitnesspal`` 只在 ``fetch`` 中懒加载；凭据仅驻留内存，不写日志、不落盘。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapter import (
    DISCLAIMER,
    MEALS,
    AdapterError,
    items_for,
    normalize_diary,
    require_date,
    summarize_records,
)

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.coddingtonbear.myfitnesspal")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
DEPENDENCY = "myfitnesspal"
CAPABILITIES = [
    "initialize",
    "warmup",
    "health",
    "fetch",
    "import",
    "stats",
    "diary.list",
    "deactivate",
]


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def _configure_streams() -> None:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


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


def _dependency_available() -> bool:
    try:
        return importlib.util.find_spec(DEPENDENCY) is not None
    except (ImportError, ValueError):
        return False


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "dependency": {"name": DEPENDENCY, "available": _dependency_available()},
        "note": DISCLAIMER,
    }


def _require_dependency() -> None:
    if not _dependency_available():
        raise RpcError(
            -32000,
            f"缺少依赖 {DEPENDENCY}；请让核心为模块 venv 安装 dependencies",
            {"code": "MODULE_DEPENDENCY_MISSING"},
        )


def _require_text(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RpcError(-32602, f"params.{key} 缺失", {"code": "INVALID_INPUT"})
    return value.strip()


def _day_entries(day: Any) -> dict[str, list[dict[str, Any]]]:
    """把上游 Day 对象转成纯 dict；字段缺失时跳过而不是编造数值。"""
    meals: dict[str, list[dict[str, Any]]] = {}
    for meal_name in MEALS:
        items: list[dict[str, Any]] = []
        try:
            meal = day.get_meal(meal_name)
        except Exception:  # noqa: BLE001 - 上游对缺餐次抛异常
            meals[meal_name] = items
            continue
        for entry in list(getattr(meal, "entries", []) or []):
            totals = getattr(entry, "totals", None)
            totals = totals if isinstance(totals, dict) else {}
            items.append(
                {
                    "name": str(getattr(entry, "name", "") or ""),
                    "calories": totals.get("calories"),
                    "proteinG": totals.get("protein"),
                    "carbsG": totals.get("carbohydrate"),
                    "fatG": totals.get("fat"),
                }
            )
        meals[meal_name] = items
    return meals


def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    _require_dependency()
    username = _require_text(params, "username")
    password = params.get("password")
    password = password if isinstance(password, str) and password else None
    try:
        day_text = require_date(params.get("date"))
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    target = date.fromisoformat(day_text)
    try:
        import myfitnesspal

        client = (
            myfitnesspal.Client(username, password=password)
            if password
            else myfitnesspal.Client(username)
        )
        day = client.get_date(target.year, target.month, target.day)
        payload = {"date": day_text, "meals": _day_entries(day)}
    except Exception as exc:  # 抓取失败要可读，且绝不能回显凭据
        raise RpcError(
            -32000,
            f"MyFitnessPal 抓取失败：{type(exc).__name__}（登录或页面结构可能已变化）",
            {"code": "UPSTREAM_ERROR"},
        ) from exc
    records = normalize_diary(payload)
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def _import(params: dict[str, Any]) -> dict[str, Any]:
    payload = params.get("payload")
    if not isinstance(payload, dict):
        raise RpcError(-32602, "params.payload 必须是对象", {"code": "INVALID_INPUT"})
    try:
        records = normalize_diary(payload)
    except AdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    return {"records": records, "count": len(records), "note": DISCLAIMER}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "MyFitnessPal Diary Import",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": CAPABILITIES,
            "health": health_payload(),
        }
    if method in {"warmup", "health"}:
        return health_payload()
    if method == "fetch":
        return _fetch(params)
    if method == "import":
        return _import(params)
    if method == "stats":
        try:
            return summarize_records(params.get("records", []))
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    if method == "diary.list":
        try:
            return items_for(params.get("records", []))
        except AdapterError as exc:
            raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    if method in {"activate", "deactivate"}:
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {str(method)[:64]}", {"code": "METHOD_NOT_FOUND"})


def _dispatch_and_reply(message: dict[str, Any]) -> bool:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    try:
        _result(request_id, handle(str(method), params))
        return method != "deactivate"
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}",
                                    {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
    _configure_streams()
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
