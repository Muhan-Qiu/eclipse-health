"""测量值：心率、HRV 时域指标、逐搏类别比例。

结构见 ``docs/DATA_SCHEMA_V1.md`` §7。B1 不做波形 delineation，
QRS/PR/QT/QTc 以 ``value=None`` 返回，并在 warnings 里说明。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from .types import SCHEMA_MEASUREMENT

RATIO_CODES = {
    "N": ("n_ratio", "正常心搏比例"),
    "SVEB": ("svb_ratio", "室上性异位比例"),
    "VEB": ("veb_ratio", "室性异位比例"),
    "F": ("f_ratio", "融合搏动比例"),
}

DELINEATION_CODES = (
    ("qrs_duration", "QRS 时限"),
    ("pr_interval", "PR 间期"),
    ("qt_interval", "QT 间期"),
    ("qtc", "QTc"),
)


def _measurement(
    *,
    code: str,
    label: str,
    value: float | None,
    unit: str,
    ucum: str,
    method: str,
    analysis_id: str,
    record_id: str,
    duration_sec: float,
    id_factory: Callable[[str], str],
    confidence: float | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_MEASUREMENT,
        "id": id_factory("msr"),
        "recordId": record_id,
        "analysisId": analysis_id,
        "code": code,
        "label": label,
        "value": value,
        "unit": unit,
        "ucum": ucum,
        "range": {"startSec": 0.0, "endSec": round(duration_sec, 3)},
        "confidence": confidence,
        "method": method,
        "warnings": list(warnings or []),
    }


def _finite(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not np.isfinite(value):
        return None
    return round(value, digits)


def compute_measurements(
    *,
    r_positions: np.ndarray,
    fs: float,
    class_counts: dict[str, int],
    n_beats: int,
    duration_sec: float,
    quality_score: float,
    record_id: str,
    analysis_id: str,
    id_factory: Callable[[str], str],
) -> list[dict[str, Any]]:
    r_positions = np.asarray(r_positions, dtype=np.float64).ravel()
    rr_ms = np.diff(r_positions) / fs * 1000.0
    common = {
        "analysis_id": analysis_id,
        "record_id": record_id,
        "duration_sec": duration_sec,
        "id_factory": id_factory,
        "confidence": quality_score,
    }

    def add(code: str, label: str, value, unit: str, ucum: str, method: str):
        return _measurement(
            code=code,
            label=label,
            value=_finite(value),
            unit=unit,
            ucum=ucum,
            method=method,
            **common,
        )

    out: list[dict[str, Any]] = []
    if len(rr_ms) >= 1:
        mean_rr = float(np.mean(rr_ms))
        out.append(
            add(
                "heart_rate_mean",
                "平均心率",
                60000.0 / mean_rr if mean_rr > 0 else None,
                "bpm",
                "/min",
                "rr-intervals",
            )
        )
        out.append(
            add(
                "heart_rate_min",
                "最小心率",
                60000.0 / float(np.max(rr_ms)),
                "bpm",
                "/min",
                "rr-intervals",
            )
        )
        out.append(
            add(
                "heart_rate_max",
                "最大心率",
                60000.0 / float(np.min(rr_ms)),
                "bpm",
                "/min",
                "rr-intervals",
            )
        )
        out.append(
            add("rr_mean", "平均 RR 间期", mean_rr, "ms", "ms", "rr-intervals")
        )
    else:
        for code, label in (
            ("heart_rate_mean", "平均心率"),
            ("heart_rate_min", "最小心率"),
            ("heart_rate_max", "最大心率"),
            ("rr_mean", "平均 RR 间期"),
        ):
            out.append(
                add(code, label, None, "bpm" if "heart" in code else "ms",
                    "/min" if "heart" in code else "ms", "rr-intervals")
            )

    if len(rr_ms) >= 2:
        out.append(
            add(
                "sdnn",
                "SDNN",
                float(np.std(rr_ms, ddof=1)),
                "ms",
                "ms",
                "rr-intervals",
            )
        )
        diff = np.diff(rr_ms)
        out.append(
            add(
                "rmssd",
                "RMSSD",
                float(np.sqrt(np.mean(diff**2))),
                "ms",
                "ms",
                "rr-intervals",
            )
        )
        out.append(
            add(
                "pnn50",
                "pNN50",
                float(np.mean(np.abs(diff) > 50.0) * 100.0),
                "%",
                "%",
                "rr-intervals",
            )
        )
    else:
        for code, label in (("sdnn", "SDNN"), ("rmssd", "RMSSD"), ("pnn50", "pNN50")):
            out.append(
                add(code, label, None, "ms" if code != "pnn50" else "%",
                    "ms" if code != "pnn50" else "%", "rr-intervals")
            )

    delineation_warning = [
        {
            "code": "delineation_not_implemented",
            "message": "B1 未实现波形 delineation，该项暂不可用",
        }
    ]
    for code, label in DELINEATION_CODES:
        out.append(
            _measurement(
                code=code,
                label=label,
                value=None,
                unit="ms",
                ucum="ms",
                method="unavailable",
                warnings=delineation_warning,
                **common,
            )
        )

    total = max(int(n_beats), 1)
    for class_name, (code, label) in RATIO_CODES.items():
        count = int(class_counts.get(class_name, 0))
        out.append(
            add(code, label, count / total * 100.0, "%", "%", "cardia-2.0")
        )
    return out
