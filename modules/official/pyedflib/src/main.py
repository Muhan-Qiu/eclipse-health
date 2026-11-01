"""pyedflib 适配模块（stdio JSON-RPC 2.0，每行一条 JSON）。

方法：initialize / warmup / health / export.edf / export.csv / import.edf / deactivate。

pyedflib 装在模块独立 venv（B 类），未就绪时返回 ``upstream_unavailable``；
只写调用方给出的 ``outputDir``。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "io.github.holgern.pyedflib")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "1.0")
SAMPLE_RETURN_LIMIT = 50_000
DISCLAIMER = "非医疗器械，不用于诊断。"


def _load_adapter() -> Any:
    name = "eh_adapter_" + MODULE_ID.replace(".", "_").replace("-", "_")
    path = Path(__file__).resolve().with_name("adapter.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter.py unavailable")
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


def _require_pyedflib() -> Any:
    if importlib.util.find_spec("pyedflib") is None:
        raise RpcError(-32000, "未安装 pyedflib；模块依赖未就绪", {"code": "upstream_unavailable"})
    import pyedflib

    return pyedflib


def _output_dir(params: dict[str, Any]) -> Path:
    raw = params.get("outputDir")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.outputDir 必须是非空路径", {"code": "INVALID_INPUT"})
    path = Path(raw)
    if not path.is_dir():
        raise RpcError(-32602, "params.outputDir 不是已存在目录", {"code": "INVALID_INPUT"})
    return path


def _plan(params: dict[str, Any]) -> dict[str, Any]:
    try:
        return adapter.build_edf_plan(params)
    except adapter.EdfAdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc


def _export_edf(params: dict[str, Any]) -> dict[str, Any]:
    plan = _plan(params)
    output_dir = _output_dir(params)
    pyedflib = _require_pyedflib()
    import numpy as np

    target = output_dir / f"{plan['recordName']}.edf"
    writer = pyedflib.EdfWriter(str(target), len(plan["labels"]), file_type=pyedflib.FILETYPE_EDFPLUS)
    try:
        headers = [
            {
                "label": label,
                "dimension": unit,
                "sample_frequency": plan["fs"],
                "physical_min": plan["physicalMin"],
                "physical_max": plan["physicalMax"],
                "digital_min": plan["digitalMin"],
                "digital_max": plan["digitalMax"],
                "transducer": "",
                "prefilter": "",
            }
            for label, unit in zip(plan["labels"], plan["units"], strict=True)
        ]
        writer.setSignalHeaders(headers)
        writer.setStartdatetime(_dt.datetime.fromisoformat(plan["startDate"]))
        for channel in plan["channels"]:
            writer.writePhysicalSamples(np.asarray(channel, dtype=np.float64))
    finally:
        writer.close()
    blob = target.read_bytes()
    return {
        "path": str(target),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "fs": plan["fs"],
        "nSamples": len(plan["channels"][0]),
        "channels": len(plan["labels"]),
        "disclaimer": DISCLAIMER,
    }


def _export_csv(params: dict[str, Any]) -> dict[str, Any]:
    plan = _plan(params)
    output_dir = _output_dir(params)
    text = adapter.to_csv_text(plan["labels"], plan["channels"], plan["fs"])
    target = output_dir / f"{plan['recordName']}.csv"
    target.write_text(text, encoding="utf-8")
    blob = text.encode("utf-8")
    return {
        "path": str(target),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "rows": len(plan["channels"][0]),
        "disclaimer": DISCLAIMER,
    }


def _import_edf(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise RpcError(-32602, "params.path 必须是非空路径", {"code": "INVALID_INPUT"})
    target = Path(raw)
    if not target.is_file():
        raise RpcError(-32602, "params.path 不是可读文件", {"code": "INVALID_INPUT"})
    pyedflib = _require_pyedflib()
    try:
        reader = pyedflib.EdfReader(str(target))
        try:
            labels = [reader.getLabel(index) for index in range(reader.signals_in_file)]
            fs = reader.getSampleFrequency(0) if reader.signals_in_file else 0
            n_samples = int(reader.getNSamples()[0]) if reader.signals_in_file else 0
            summary = adapter.summarize_import(labels, fs, n_samples)
            result: dict[str, Any] = {"record": summary, "disclaimer": DISCLAIMER}
            if params.get("includeSamples") is True:
                limit = min(n_samples, SAMPLE_RETURN_LIMIT)
                result["samples"] = [
                    reader.readSignal(index)[:limit].tolist() for index in range(reader.signals_in_file)
                ]
                result["samplesTruncated"] = n_samples > limit
        finally:
            reader.close()
    except RpcError:
        raise
    except adapter.EdfAdapterError as exc:
        raise RpcError(-32602, exc.message, {"code": exc.code}) from exc
    except Exception as exc:
        raise RpcError(-32000, f"pyedflib 读取失败：{type(exc).__name__}", {"code": "upstream_failed"}) from exc
    return result


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "upstreamAvailable": importlib.util.find_spec("pyedflib") is not None,
        "disclaimer": DISCLAIMER,
    }


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        requested = str(params.get("apiVersion") or API_VERSION)
        if not requested.startswith("1."):
            raise RpcError(-32004, "unsupported apiVersion", {"code": "INCOMPATIBLE_API"})
        return {
            "name": "pyedflib EDF/BDF",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "capabilities": [
                "initialize",
                "warmup",
                "health",
                "export.edf",
                "export.csv",
                "import.edf",
                "deactivate",
            ],
            "health": health_payload(),
        }
    if method == "warmup":
        return health_payload()
    if method == "health":
        return health_payload()
    if method == "export.edf":
        return _export_edf(params)
    if method == "export.csv":
        return _export_csv(params)
    if method == "import.edf":
        return _import_edf(params)
    if method in {"activate"}:
        return {"ok": True}
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
        _result(request_id, handle(str(method), params))
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
