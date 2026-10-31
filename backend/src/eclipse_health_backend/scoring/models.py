"""规则评分的对外模型（G2）。

评分只描述「公开健康建议区间」上的位置，不包含任何诊断结论。
字段使用 camelCase，与现有 API 的 ``memberId`` / ``capturedAt`` 保持一致。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CategoryId = Literal["heart", "sleep", "weight", "activity", "blood_pressure"]
SuggestionCategory = Literal[
    "heart",
    "sleep",
    "weight",
    "activity",
    "blood_pressure",
    "general",
]
Grade = Literal["excellent", "good", "fair", "attention", "unknown"]
Severity = Literal["info", "attention"]

DISCLAIMER = "基于公开区间规则的参考评分，不是医学诊断"
WINDOW_DAYS = 30


class ScoreCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: CategoryId
    label: str
    score: int | None = Field(default=None, ge=0, le=100)
    grade: Grade = "unknown"
    factors: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    evidenceCount: int = Field(default=0, ge=0)


class ScoreReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: int | None = Field(default=None, ge=0, le=100)
    grade: Grade = "unknown"
    categories: list[ScoreCategory] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    generatedAt: AwareDatetime
    memberId: str | None = None
    windowDays: int = WINDOW_DAYS


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    category: SuggestionCategory
    severity: Severity = "info"
    prompt: str


class SuggestionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Suggestion] = Field(default_factory=list)


def grade_for(score: int | None) -> Grade:
    """85/70/55 三档分界；无数据统一为 unknown。"""
    if score is None:
        return "unknown"
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "attention"


__all__ = [
    "DISCLAIMER",
    "WINDOW_DAYS",
    "CategoryId",
    "Grade",
    "ScoreCategory",
    "ScoreReport",
    "Severity",
    "Suggestion",
    "SuggestionCategory",
    "SuggestionList",
    "grade_for",
]
