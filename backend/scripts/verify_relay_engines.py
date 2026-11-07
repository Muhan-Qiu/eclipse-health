"""用本机已安装的 relay-ecg 权重验证通用 ONNX 逐搏管线（V4.2）。

默认读取 ``%LOCALAPPDATA%/eclipse-health/modules/org.eclipsehealth.relay-ecg``
下已安装的 7 个模型；``--signal`` 指向核心保存的 float32 波形文件。

示例：

    backend\\.venv\\Scripts\\python.exe scripts\\verify_relay_engines.py ^
        --signal "%LOCALAPPDATA%\\eclipse-health\\signals\\sig_xxx.f32" --fs 500
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

import numpy as np

from eclipse_health_backend.analysis_service.engines import (
    ModuleModelSpec,
)
from eclipse_health_backend.analysis_service.onnx_engine import (
    OnnxEngineError,
    OnnxEngineRunner,
)

MODULE_ID = "org.eclipsehealth.relay-ecg"


def _default_module_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "eclipse-health" / "modules" / MODULE_ID / "0.1.0"
        if candidate.is_dir():
            return candidate
    return BACKEND_ROOT.parent / "modules" / "official" / "relay-ecg"


def _load_samples(path: Path) -> np.ndarray:
    blob = path.read_bytes()
    if len(blob) % 4 != 0:
        raise SystemExit(f"{path} 不是 float32 数组")
    return np.frombuffer(blob, dtype="<f4").astype(np.float32)


def _spec(module_dir: Path, model: dict) -> ModuleModelSpec:
    relative = str(model["files"][0]["path"])
    model_path = module_dir / relative
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    declared = str(model["files"][0].get("sha256") or "")
    if declared and digest != declared:
        raise SystemExit(f"{relative} sha256 与 manifest 不一致")
    return ModuleModelSpec(
        engine_id=f"{MODULE_ID}:{model['id']}",
        module_id=MODULE_ID,
        module_version="0.1.0",
        module_dir=module_dir,
        model_id=str(model["id"]),
        model_name=str(model.get("name") or model["id"]),
        model=model,
        model_path=model_path,
        model_relative_path=relative,
        model_sha256=digest,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify relay-ecg ONNX engines on a raw float32 signal")
    parser.add_argument("--signal", type=Path, required=True, help="核心保存的 .f32 波形")
    parser.add_argument("--fs", type=float, default=500.0, help="采样率（默认 500）")
    parser.add_argument("--lead", default="I", help="导联名（默认 I）")
    parser.add_argument("--module-dir", type=Path, default=None)
    parser.add_argument("--models", nargs="*", default=None, help="只跑指定模型 id")
    args = parser.parse_args()

    module_dir = args.module_dir or _default_module_dir()
    manifest = json.loads((module_dir / "module.json").read_text(encoding="utf-8"))
    models = {item["id"]: item for item in manifest["contributes"]["models"]}
    wanted = args.models or list(models)

    samples = _load_samples(args.signal)
    print(f"signal: {samples.size} samples, {samples.size / args.fs:.1f}s @{args.fs:g}Hz", flush=True)
    print(f"module: {module_dir}", flush=True)

    failures = 0
    for model_id in wanted:
        model = models.get(model_id)
        if model is None:
            print(f"ERR {model_id:12s} 未知模型", flush=True)
            failures += 1
            continue
        started = time.perf_counter()
        try:
            result = OnnxEngineRunner(_spec(module_dir, model)).analyze(
                record_id="rec_verify",
                analysis_id=f"ana_{model_id}",
                samples=samples,
                fs=args.fs,
                lead=args.lead,
            )
        except OnnxEngineError as exc:
            failures += 1
            print(
                f"ERR {model_id:12s} {time.perf_counter() - started:7.2f}s "
                f"[{exc.code}] {exc.message}",
                flush=True,
            )
            continue
        params = result["parameters"]
        print(
            f"OK  {model_id:12s} {time.perf_counter() - started:7.2f}s  "
            f"scored={params.get('beatsScored')} dropped={params.get('beatsDropped')} "
            f"seq={params.get('sequences')}  {result['summary']}",
            flush=True,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
