"""GPX Track 模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：``initialize`` / ``warmup`` / ``health`` / ``summary`` / ``importFile`` /
``exportGpx`` / ``latestSummary`` / ``deactivate``。

有 gpxpy 时优先用它做语法校验与扩展解析；缺失时回退到 adapter 的 stdlib 解析器
（仅支持未压缩 GPX），保证模块在核心 venv 中也能导入普通轨迹。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.tkrajina.gpxpy")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
MAX_POINTS = 100_000
MAX_INLINE_BYTES = 3_500_000
_HR_EXTENSION_RE = re.compile(r"<(?:[A-Za-z0-9_]+:)?(?:hr|heartrate)>(\d{1,3})<", re.IGNORECASE)


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
_LAST_SUMMARY: dict[str, Any] | None = None


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


def _require_path(params: dict[str, Any]) -> Path:
    raw = params.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.path 必须是文件路径", {"code": "INVALID_INPUT"})
    path = Path(raw)
    if not path.is_file():
        raise RpcError(-32602, "文件不存在或不可读", {"code": "INVALID_INPUT"})
    return path


def _extension_heart_rate(extensions: Any) -> int | None:
    for extension in extensions or []:
        match = _HR_EXTENSION_RE.search(str(extension))
        if match:
            value = int(match.group(1))
            if 20 <= value <= 300:
                return value
    return None


def _points_from_gpxpy(gpx: Any) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append(
                    {
                        "lat": point.latitude,
                        "lon": point.longitude,
                        "ele": point.elevation,
                        "time": point.time.isoformat() if point.time else None,
                        "heartRate": _extension_heart_rate(getattr(point, "extensions", None)),
                    }
                )
    return points


def _read_points(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise RpcError(-32602, "GPX 文件无法按 UTF-8 读取", {"code": "INVALID_INPUT"}) from exc
    try:
        import gpxpy
    except ModuleNotFoundError:
        return adapter.parse_gpx_xml(text), "stdlib"
    try:
        parsed = gpxpy.parse(text)
        points = _points_from_gpxpy(parsed)
    except Exception as exc:
        raise RpcError(-32602, "GPX 解析失败", {"code": "INVALID_INPUT"}) from exc
    if not points:
        raise RpcError(-32602, "GPX 中没有有效轨迹点", {"code": "INVALID_INPUT"})
    return points, "gpxpy"


def _import(params: dict[str, Any], *, include_points: bool) -> dict[str, Any]:
    global _LAST_SUMMARY
    path = _require_path(params)
    try:
        points, parser = _read_points(path)
        summary = adapter.summarize_points(points)
    except ValueError as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    _LAST_SUMMARY = summary
    result: dict[str, Any] = {
        "summary": summary,
        "record": adapter.session_payload(summary),
        "parser": parser,
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    if include_points:
        result["points"] = points[:MAX_POINTS]
        result["truncated"] = len(points) > MAX_POINTS
    return result


def _export(params: dict[str, Any]) -> dict[str, Any]:
    points = params.get("points")
    if not isinstance(points, list) or not points:
        raise RpcError(-32602, "params.points 必须是非空数组", {"code": "INVALID_INPUT"})
    if len(points) > MAX_POINTS:
        raise RpcError(-32602, f"params.points 最多 {MAX_POINTS} 个", {"code": "INVALID_INPUT"})
    name = params.get("name") if isinstance(params.get("name"), str) else "eclipse health export"
    try:
        text = adapter.to_gpx(points, name)
    except ValueError as exc:
        raise RpcError(-32602, str(exc), {"code": "INVALID_INPUT"}) from exc
    blob = text.encode("utf-8")
    result: dict[str, Any] = {
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
    output_path = params.get("outputPath")
    if isinstance(output_path, str) and output_path.strip():
        path = Path(output_path)
        if path.suffix.lower() != ".gpx" or not path.parent.is_dir():
            raise RpcError(-32602, "outputPath 必须是已存在目录下的 .gpx 文件", {"code": "INVALID_INPUT"})
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RpcError(-32000, "GPX 写入失败", {"code": "MODULE_ERROR"}) from exc
        result["path"] = str(path)
        return result
    if len(blob) > MAX_INLINE_BYTES:
        raise RpcError(-32602, "GPX 超过 3.5MB，请提供 outputPath", {"code": "INVALID_INPUT"})
    result["gpx"] = text
    return result


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "GPX Track",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "warmup", "health", "summary", "importFile", "exportGpx", "latestSummary", "deactivate"],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "warmup":
        return {"ok": True, "warm": True, "dependency": "gpxpy"}
    if method == "health":
        return {
            "ok": True,
            "warm": True,
            "gpxpyAvailable": importlib.util.find_spec("gpxpy") is not None,
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "summary":
        return _import(params, include_points=False)
    if method == "importFile":
        return _import(params, include_points=True)
    if method == "exportGpx":
        return _export(params)
    if method == "latestSummary":
        if _LAST_SUMMARY is None:
            return {"available": False, "distanceKm": 0, "nonDiagnostic": NON_DIAGNOSTIC}
        return {"available": True, **_LAST_SUMMARY}
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
