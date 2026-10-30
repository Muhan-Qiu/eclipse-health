"""手动指标的请求/响应模型与单位、范围定义。

范围分两层：超出「硬边界」直接 422（明显是输入错误）；落在硬边界内但
临床异常的值只返回 ``warnings``，不拒绝写入（B4-07 契约）。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..domain.models import Notes, Tag

METRIC_RECORD_TYPE = "org.eclipsehealth.metric"

# 血压用 mmHg；其余按常见家用设备单位。
UNIT_BY_KIND: dict[str, str] = {
    "blood_pressure": "mmHg",
    "weight": "kg",
    "spo2": "%",
    "glucose": "mmol/L",
}


class MetricKind(StrEnum):
    blood_pressure = "blood_pressure"
    weight = "weight"
    spo2 = "spo2"
    glucose = "glucose"


class BloodPressureValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    systolic: int = Field(ge=50, le=300)
    diastolic: int = Field(ge=20, le=200)


class WeightValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight: float = Field(ge=2, le=500)


class Spo2Values(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spo2: float = Field(ge=50, le=100)


class GlucoseValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    glucose: float = Field(ge=0.5, le=50)


VALUE_MODELS: dict[MetricKind, type[BaseModel]] = {
    MetricKind.blood_pressure: BloodPressureValues,
    MetricKind.weight: WeightValues,
    MetricKind.spo2: Spo2Values,
    MetricKind.glucose: GlucoseValues,
}


class MetricWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str


class MetricCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MetricKind
    measuredAt: AwareDatetime
    values: dict[str, float]
    notes: Notes = ""
    tags: list[Tag] = Field(default_factory=list, max_length=32)
    timezone: str = "UTC"
    memberId: str | None = None


class MetricUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measuredAt: AwareDatetime | None = None
    values: dict[str, float] | None = None
    notes: Notes | None = None
    tags: list[Tag] | None = Field(default=None, max_length=32)
    timezone: str | None = None


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    memberId: str
    kind: MetricKind
    measuredAt: AwareDatetime
    timezone: str
    values: dict[str, float]
    unit: str
    notes: str
    tags: list[str]
    warnings: list[MetricWarning] = Field(default_factory=list)
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class MetricPage(BaseModel):
    items: list[Metric]
    total: int
    limit: int
    offset: int


def normalize_values(kind: MetricKind, raw: dict[str, float]) -> dict[str, float]:
    """按 kind 校验并归一化 values；形状/硬边界不符时抛 ``ValueError``。"""
    model = VALUE_MODELS[kind]
    parsed = model.model_validate(raw)
    return parsed.model_dump()


# 临床提示阈值（只警告）：(code, 判断函数, message)
def compute_warnings(kind: MetricKind, values: dict[str, float]) -> list[MetricWarning]:
    warnings: list[MetricWarning] = []

    def add(code: str, severity: Literal["info", "warning", "error"], message: str) -> None:
        warnings.append(MetricWarning(code=code, severity=severity, message=message))

    if kind is MetricKind.blood_pressure:
        systolic = int(values["systolic"])
        diastolic = int(values["diastolic"])
        if systolic >= 140:
            add("systolic_high", "warning", "Systolic pressure is high.")
        elif systolic <= 90:
            add("systolic_low", "warning", "Systolic pressure is low.")
        if diastolic >= 90:
            add("diastolic_high", "warning", "Diastolic pressure is high.")
        elif diastolic <= 60:
            add("diastolic_low", "warning", "Diastolic pressure is low.")
        if systolic <= diastolic:
            add(
                "systolic_not_above_diastolic",
                "error",
                "Systolic pressure should be higher than diastolic pressure.",
            )
    elif kind is MetricKind.weight:
        weight = values["weight"]
        if weight < 30:
            add("weight_low", "warning", "Weight is unusually low.")
        elif weight > 200:
            add("weight_high", "warning", "Weight is unusually high.")
    elif kind is MetricKind.spo2:
        spo2 = values["spo2"]
        if spo2 < 90:
            add("spo2_critical", "error", "Blood oxygen is very low.")
        elif spo2 < 95:
            add("spo2_low", "warning", "Blood oxygen is below the normal range.")
    elif kind is MetricKind.glucose:
        glucose = values["glucose"]
        if glucose > 16.7:
            add("glucose_critical_high", "error", "Blood glucose is very high.")
        elif glucose > 7.8:
            add("glucose_high", "warning", "Blood glucose is high.")
        elif glucose < 3.9:
            add("glucose_low", "warning", "Blood glucose is low.")

    return warnings


__all__ = [
    "METRIC_RECORD_TYPE",
    "UNIT_BY_KIND",
    "BloodPressureValues",
    "GlucoseValues",
    "Metric",
    "MetricCreate",
    "MetricKind",
    "MetricPage",
    "MetricUpdate",
    "MetricWarning",
    "Spo2Values",
    "WeightValues",
    "compute_warnings",
    "normalize_values",
]
