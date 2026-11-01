"""趋势查询：按测量码把历史记录整理成时间序列（INTERNAL_API_V1 §7、Schema §7）。"""

from __future__ import annotations

from .metrics import DEFAULT_METRICS, METRIC_CATALOG, parse_metrics
from .service import build_trends

__all__ = ["DEFAULT_METRICS", "METRIC_CATALOG", "build_trends", "parse_metrics"]
