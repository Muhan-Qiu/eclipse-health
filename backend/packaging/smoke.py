"""对运行中的后端做一条端到端冒烟：健康检查 → 导入 MIT-BIH 100 → 分析 → 轮询。

只依赖 httpx 与 wfdb（venv 里都有），用于验证冻结 sidecar 的模型与模块可用：

    backend\\.venv\\Scripts\\python.exe backend\\packaging\\smoke.py --base http://127.0.0.1:8765

退出码：0 全部通过；1 有失败步骤。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = ROOT / "backend" / "resources" / "samples" / "100"


def _get(client: httpx.Client, path: str) -> dict:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def wait_engine(client: httpx.Client, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    status: dict = {}
    while time.monotonic() < deadline:
        status = _get(client, "/api/v1/engine")
        if status.get("status") == "ready":
            return status
        if status.get("status") == "error":
            raise SystemExit(f"engine error: {status.get('error')}")
        time.sleep(1.0)
    raise SystemExit(f"engine not ready in {timeout_s:.0f}s: {status.get('status')}")


def load_sample(sample: Path) -> tuple[np.ndarray, float, str]:
    record = wfdb.rdrecord(str(sample))
    names = [name.upper() for name in record.sig_name]
    lead_index = names.index("MLII") if "MLII" in names else 0
    samples = np.asarray(record.p_signal[:, lead_index], dtype=np.float32)
    samples = np.nan_to_num(samples, nan=0.0)
    return samples, float(record.fs), record.sig_name[lead_index]


def main() -> int:
    parser = argparse.ArgumentParser(description="eclipse health frozen sidecar smoke test")
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--engine-timeout", type=float, default=240.0)
    parser.add_argument("--analysis-timeout", type=float, default=180.0)
    args = parser.parse_args()

    started = time.perf_counter()
    with httpx.Client(base_url=args.base.rstrip("/"), timeout=60.0) as client:
        health = _get(client, "/api/v1/health")
        print(f"[ok] health version={health.get('version')} data={health.get('dataDir')}")

        engine = wait_engine(client, args.engine_timeout)
        print(
            f"[ok] engine ready in {time.perf_counter() - started:.1f}s "
            f"model={engine.get('modelId')} mode={engine.get('mode')}"
        )

        members = _get(client, "/api/v1/members")
        if not members:
            response = client.post("/api/v1/members", json={"name": "Smoke"})
            response.raise_for_status()
            members = [response.json()]
        member_id = members[0]["id"]

        samples, fs, lead = load_sample(args.sample)
        print(f"[..] sample {args.sample.name}: {samples.size} samples @ {fs} Hz ({lead})")
        payload = {
            "memberId": member_id,
            "recordType": "org.eclipsehealth.ecg",
            "capturedAt": "2026-10-29T10:00:00+08:00",
            "samplingRate": fs,
            "signal": {"lead": "MLII", "unit": "mV", "samples": samples.tolist()},
        }
        response = client.post("/api/v1/records", json=payload)
        response.raise_for_status()
        record = response.json()
        record_id = record["id"]
        print(f"[ok] record created {record_id}")

        accepted = client.post(f"/api/v1/records/{record_id}/analyses", json={})
        accepted.raise_for_status()
        analysis_id = accepted.json()["analysisId"]
        print(f"[ok] analysis accepted {analysis_id}")

        deadline = time.monotonic() + args.analysis_timeout
        result: dict = {}
        while time.monotonic() < deadline:
            result = _get(client, f"/api/v1/analyses/{analysis_id}")
            if result.get("status") in {"completed", "failed"}:
                break
            time.sleep(1.0)

        if result.get("status") != "completed":
            print(f"[FAIL] analysis status={result.get('status')} error={result.get('error')}")
            return 1
        beats = result.get("beatsTotal") or len(result.get("beats") or [])
        measurements = result.get("measurements") or []
        print(
            f"[ok] analysis completed: beats={beats} measurements={len(measurements)} "
            f"durationMs={result.get('durationMs')}"
        )
        print(f"[ok] total {time.perf_counter() - started:.1f}s")
        print(json.dumps({"recordId": record_id, "analysisId": analysis_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
