"""Open Food Facts 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``lookup`` / ``mapProduct`` /
``latestProduct`` / ``deactivate``。``lookup`` 同时作为页面表单与 LLM 工具
``food.lookup`` 的 RPC 入口；只访问 world.openfoodfacts.org。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.openfoodfacts.openfoodfacts")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
USER_AGENT = "eclipse-health/0.1 (eclipse health module; +https://github.com/openfoodfacts/openfoodfacts-python)"
_LAST_PRODUCT: dict[str, Any] | None = None


def _load_adapter() -> Any:
    spec = importlib.util.spec_from_file_location(
        f"{MODULE_ID}.adapter", Path(__file__).with_name("adapter.py")
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("adapter.py 缺失")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_adapter()


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


def _fetch_product(barcode: str) -> dict[str, Any] | None:
    try:
        import openfoodfacts
    except ModuleNotFoundError as exc:
        raise RpcError(
            -32000,
            "openfoodfacts 未安装；请先完成模块依赖安装",
            {"code": "DEPENDENCY_MISSING"},
        ) from exc
    try:
        product = None
        api_class = getattr(openfoodfacts, "API", None)
        if api_class is not None:
            client = getattr(api_class(user_agent=USER_AGENT), "product", None)
            if client is not None and hasattr(client, "get"):
                product = client.get(barcode)
        if product is None:
            legacy = getattr(openfoodfacts, "products", None)
            if legacy is not None and hasattr(legacy, "get_product"):
                product = legacy.get_product(barcode)
    except Exception as exc:
        raise RpcError(
            -32000,
            f"Open Food Facts 查询失败：{type(exc).__name__}",
            {"code": "MODULE_ERROR"},
        ) from exc
    if isinstance(product, dict) and isinstance(product.get("product"), dict):
        status = product.get("status")
        product = product["product"] if status not in (0, "0", "failure") else None
    if not isinstance(product, dict) or not product:
        return None
    if not (product.get("product_name") or product.get("product_name_zh") or product.get("code")):
        return None
    return product


def _lookup(params: dict[str, Any]) -> dict[str, Any]:
    global _LAST_PRODUCT
    try:
        barcode = adapter.normalize_barcode(params.get("barcode"))
    except (TypeError, ValueError) as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    product = _fetch_product(barcode)
    result = adapter.lookup_result(barcode, product, found=product is not None)
    _LAST_PRODUCT = result["product"]
    return result


def _map_product(params: dict[str, Any]) -> dict[str, Any]:
    result = _lookup(params)
    if not result["found"] or result["product"] is None:
        return {"found": False, "record": None, "nonDiagnostic": NON_DIAGNOSTIC}
    consumed = params.get("consumedGrams", 100)
    try:
        record = adapter.to_record(result["product"], consumed)
    except (TypeError, ValueError) as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    return {"found": True, "record": record, "nonDiagnostic": NON_DIAGNOSTIC}


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "Open Food Facts",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "lookup", "mapProduct", "latestProduct", "deactivate"],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "warmup":
        return {"ok": True, "warm": True, "dependency": "openfoodfacts"}
    if method == "health":
        return {
            "ok": True,
            "warm": True,
            "openfoodfactsAvailable": importlib.util.find_spec("openfoodfacts") is not None,
            "requiresNetwork": True,
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "lookup":
        return _lookup(params)
    if method == "mapProduct":
        return _map_product(params)
    if method == "latestProduct":
        if _LAST_PRODUCT is None:
            return {"available": False, "per100g": {"energyKcal": 0}, "nonDiagnostic": NON_DIAGNOSTIC}
        return {"available": True, **_LAST_PRODUCT}
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
        result = handle(str(method), params)
        _result(request_id, result)
        return method != "deactivate"
    except RpcError as error:
        _error(request_id, error)
        return True
    except Exception as exc:  # noqa: BLE001 - 模块边界必须兜底
        _error(request_id, RpcError(-32603, f"internal error: {type(exc).__name__}", {"code": "MODULE_ERROR"}))
        return True


def main() -> int:
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
