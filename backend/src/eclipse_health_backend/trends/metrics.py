"""核心测量码白名单与展示元数据（Schema §7 固定集合）。

趋势只接受核心码：模块自定义码（``io.github.owner.metric``）的语义与单位
由模块自己定义，核心无法保证可比性，因此不在首版趋势白名单里。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import InvalidInputError


@dataclass(frozen=True)
class MetricMeta:
    code: str
    label: str
    unit: str
    ucum: str


METRIC_CATALOG: dict[str, MetricMeta] = {
    meta.code: meta
    for meta in (
        MetricMeta("heart_rate_mean", "平均心率", "bpm", "/min"),
        MetricMeta("heart_rate_min", "最小心率", "bpm", "/min"),
        MetricMeta("heart_rate_max", "最大心率", "bpm", "/min"),
        MetricMeta("rr_mean", "平均 RR 间期", "ms", "ms"),
        MetricMeta("sdnn", "SDNN", "ms", "ms"),
        MetricMeta("rmssd", "RMSSD", "ms", "ms"),
        MetricMeta("pnn50", "pNN50", "%", "%"),
        MetricMeta("qrs_duration", "QRS 时限", "ms", "ms"),
        MetricMeta("pr_interval", "PR 间期", "ms", "ms"),
        MetricMeta("qt_interval", "QT 间期", "ms", "ms"),
        MetricMeta("qtc", "QTc", "ms", "ms"),
        MetricMeta("n_ratio", "正常心搏比例", "%", "%"),
        MetricMeta("svb_ratio", "室上性异位比例", "%", "%"),
        MetricMeta("veb_ratio", "室性异位比例", "%", "%"),
        MetricMeta("f_ratio", "融合搏动比例", "%", "%"),
    )
}

DEFAULT_METRICS: tuple[str, ...] = ("heart_rate_mean", "rmssd")


def parse_metrics(raw: str | None) -> list[str]:
    """把 ``metrics=a,b`` 解析为去重后的码列表；未知码返回 422 ``unknown_metric``。"""
    if raw is None or not raw.strip():
        return list(DEFAULT_METRICS)
    codes: list[str] = []
    for chunk in raw.split(","):
        code = chunk.strip()
        if code and code not in codes:
            codes.append(code)
    unknown = [code for code in codes if code not in METRIC_CATALOG]
    if unknown:
        raise InvalidInputError(
            f"unknown trend metric: {', '.join(unknown)}",
            code="unknown_metric",
            details={"unknown": unknown, "supported": list(METRIC_CATALOG)},
        )
    if not codes:
        return list(DEFAULT_METRICS)
    return codes


__all__ = ["DEFAULT_METRICS", "METRIC_CATALOG", "MetricMeta", "parse_metrics"]
