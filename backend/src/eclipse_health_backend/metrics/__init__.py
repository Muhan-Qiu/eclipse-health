"""手动健康指标（I2）。

指标复用 ``records`` 存储：``recordType="org.eclipsehealth.metric"``，
``payload={"kind": ..., "values": ...}``，无信号、``moduleId=None``。
"""

from __future__ import annotations

from .models import METRIC_RECORD_TYPE, Metric, MetricKind

__all__ = ["METRIC_RECORD_TYPE", "Metric", "MetricKind"]
