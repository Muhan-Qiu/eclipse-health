"""基于公开区间的规则评分与建议（G2）。非诊断。"""

from __future__ import annotations

from .models import DISCLAIMER, ScoreCategory, ScoreReport, Suggestion
from .service import build_score_report, empty_report
from .suggestions import build_suggestions

__all__ = [
    "DISCLAIMER",
    "ScoreCategory",
    "ScoreReport",
    "Suggestion",
    "build_score_report",
    "build_suggestions",
    "empty_report",
]
