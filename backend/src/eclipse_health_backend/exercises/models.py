"""运动记录的请求/响应模型。

可选字段保持 ``None``（未填写）与 ``0``/空字符串的区别；PATCH 用
``exclude_unset`` 合并，因此显式传 ``null`` 可以清空距离/强度/主观感受。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..domain.models import Notes

EXERCISE_RECORD_TYPE = "org.eclipsehealth.health.exercise"

Activity = Literal["walk", "run", "cycle", "swim", "strength", "yoga", "other"]
Intensity = Literal["low", "moderate", "vigorous"]
Subjective = Literal["轻松", "适中", "吃力"]
ExerciseSource = Literal["manual", "import"]

# 家用记录不应出现离谱距离；只为挡住明显输入错误。
MAX_DISTANCE_KM = 1000.0


class ExerciseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity: Activity
    durationSec: int = Field(gt=0, le=24 * 60 * 60)
    distanceKm: float | None = Field(default=None, ge=0, le=MAX_DISTANCE_KM)
    intensity: Intensity | None = None
    subjective: Subjective | None = None
    notes: Notes = ""
    startAt: AwareDatetime
    source: ExerciseSource = "manual"
    timezone: str = "UTC"
    memberId: str | None = None


class ExerciseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity: Activity | None = None
    durationSec: int | None = Field(default=None, gt=0, le=24 * 60 * 60)
    distanceKm: float | None = Field(default=None, ge=0, le=MAX_DISTANCE_KM)
    intensity: Intensity | None = None
    subjective: Subjective | None = None
    notes: Notes | None = None
    startAt: AwareDatetime | None = None
    source: ExerciseSource | None = None
    timezone: str | None = None


class Exercise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    memberId: str
    activity: Activity
    durationSec: int = Field(gt=0)
    distanceKm: float | None = None
    intensity: Intensity | None = None
    subjective: Subjective | None = None
    notes: str = ""
    startAt: AwareDatetime
    source: ExerciseSource = "manual"
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class ExercisePage(BaseModel):
    items: list[Exercise]
    total: int
    limit: int
    offset: int


__all__ = [
    "EXERCISE_RECORD_TYPE",
    "Activity",
    "Exercise",
    "ExerciseCreate",
    "ExercisePage",
    "ExerciseSource",
    "ExerciseUpdate",
    "Intensity",
    "Subjective",
]
