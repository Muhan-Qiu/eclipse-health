"""领域模型（Pydantic v2），对应 Schema §3–§5。

限制来自 `docs/DATA_SCHEMA_V1.md` §12；未知字段一律拒绝（additionalProperties: false）。
存储层看到的 ``schema`` 字段在 Python 里叫 ``schema_ref``，避免与 BaseModel 内置属性冲突，
序列化时按别名输出为 ``schema``。
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .common import json_size_bytes
from .ids import id_pattern_regex

MAX_TAGS = 32
MAX_TAG_LENGTH = 32
MAX_NOTES = 4000
MAX_METADATA_BYTES = 16 * 1024
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_LEADS = 16
MAX_SIGNALS = 16

MEMBER_SCHEMA = "org.eclipsehealth.member/1"
RECORD_SCHEMA = "org.eclipsehealth.record/1"
SIGNAL_SCHEMA = "org.eclipsehealth.signal/1"

TAG_PATTERN = r"^.{1,32}$"
LEAD_PATTERN = r"^[A-Za-z][A-Za-z0-9+\-]{0,15}$"
# 核心域名 org.eclipsehealth.* 或社区 io.github.owner.name
NAMESPACE_PATTERN = (
    r"^(?:org\.eclipsehealth|io\.github)\.[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
UCUM_PATTERN = r"^[A-Za-z0-9\[\]/%.*'^{}+_-]+$"
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-/]{0,63}$")
try:  # 系统是否有可用的 tzdata；没有时只能做格式校验
    ZoneInfo("UTC")
    TZDATA_AVAILABLE = True
except Exception:  # noqa: BLE001
    TZDATA_AVAILABLE = False

Tag = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TAG_LENGTH)
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Notes = Annotated[str, StringConstraints(max_length=MAX_NOTES)]
JsonObject = dict[str, Any]

NamespaceId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
LeadName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)]
UnitCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


def _validate_timezone(value: str) -> str:
    if not TIMEZONE_PATTERN.match(value):
        raise ValueError("timezone must be an IANA name such as Asia/Shanghai or UTC")
    if TZDATA_AVAILABLE:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
    return value


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["wearable", "device", "manual", "file", "import", "unknown"] = "unknown"
    manufacturer: ShortText | None = None
    device: ShortText | None = None
    app: ShortText | None = None
    appVersion: ShortText | None = None


class QualityWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    severity: Literal["info", "warning", "error"] = "warning"
    startSec: float | None = Field(default=None, ge=0)
    endSec: float | None = Field(default=None, ge=0)
    message: str = Field(default="", max_length=500)


class QualitySegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startSec: float = Field(ge=0)
    endSec: float = Field(ge=0)
    quality: float = Field(ge=0, le=1)


class Quality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float | None = Field(default=None, ge=0, le=1)
    level: Literal["good", "fair", "poor"] | None = None
    warnings: list[QualityWarning] = Field(default_factory=list, max_length=200)
    segments: list[QualitySegment] = Field(default_factory=list, max_length=2000)


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fileNameHash: str | None = Field(default=None, max_length=128)
    fileHash: str | None = Field(default=None, max_length=128)
    adapterVersion: str | None = Field(default=None, max_length=64)


class Member(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_ref: Literal[MEMBER_SCHEMA] = Field(default=MEMBER_SCHEMA, alias="schema")
    id: str = Field(pattern=id_pattern_regex("member"))
    displayName: DisplayName
    birthYear: int | None = Field(default=None, ge=1900, le=2100)
    sex: Literal["female", "male", "other", "unknown"] = "unknown"
    heightCm: float | None = Field(default=None, ge=30, le=300)
    weightKg: float | None = Field(default=None, ge=2, le=500)
    conditions: list[ShortText] = Field(default_factory=list, max_length=32)
    medications: list[ShortText] = Field(default_factory=list, max_length=32)
    notes: Notes = ""
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class SignalStorage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["file"] = "file"
    relativePath: str = Field(min_length=1, max_length=256)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byteOrder: Literal["little"] = "little"


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_ref: Literal[SIGNAL_SCHEMA] = Field(default=SIGNAL_SCHEMA, alias="schema")
    id: str = Field(pattern=id_pattern_regex("signal"))
    recordId: str = Field(pattern=id_pattern_regex("record"))
    lead: LeadName = Field(pattern=LEAD_PATTERN)
    fs: float = Field(gt=0, le=1_000_000)
    unit: UnitCode = Field(default="mV", pattern=UCUM_PATTERN)
    dtype: Literal["float32"] = "float32"
    shape: list[int] = Field(min_length=1, max_length=2)
    startSample: int = Field(default=0, ge=0)
    storage: SignalStorage
    createdAt: AwareDatetime

    @field_validator("shape")
    @classmethod
    def _check_shape(cls, value: list[int]) -> list[int]:
        if any(item < 0 for item in value):
            raise ValueError("shape entries must be non-negative")
        if value[0] < 1:
            raise ValueError("shape[0] must be >= 1")
        return value

    @property
    def n_samples(self) -> int:
        n = 1
        for item in self.shape:
            n *= item
        return n


class RecordFields(BaseModel):
    """HealthRecord 的可写字段（不含服务端生成的 id/时间戳）。"""

    model_config = ConfigDict(extra="forbid")

    memberId: str = Field(pattern=id_pattern_regex("member"))
    recordType: NamespaceId = Field(pattern=NAMESPACE_PATTERN)
    moduleId: NamespaceId | None = Field(default=None, pattern=NAMESPACE_PATTERN)
    capturedAt: AwareDatetime
    timezone: str = "UTC"
    source: SourceInfo = Field(default_factory=SourceInfo)
    samplingRate: float | None = Field(default=None, gt=0, le=1_000_000)
    leads: list[LeadName] = Field(default_factory=list, max_length=MAX_LEADS)
    durationSec: float | None = Field(default=None, ge=0)
    unit: UnitCode = Field(default="mV", pattern=UCUM_PATTERN)
    signalIds: list[str] = Field(default_factory=list, max_length=MAX_SIGNALS)
    quality: Quality | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_TAGS)
    notes: Notes = ""
    favorite: bool = False
    metadata: JsonObject = Field(default_factory=dict)
    payload: JsonObject = Field(default_factory=dict)
    provenance: Provenance | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

    @field_validator("leads")
    @classmethod
    def _check_leads(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("leads must be unique")
        return value

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("tags must be unique")
        return value

    @field_validator("signalIds")
    @classmethod
    def _check_signal_ids(cls, value: list[str]) -> list[str]:
        pattern = re.compile(id_pattern_regex("signal"))
        if any(not pattern.match(item) for item in value):
            raise ValueError("signalIds must use the sig_<uuidv7> form")
        return value

    @field_validator("metadata")
    @classmethod
    def _check_metadata(cls, value: JsonObject) -> JsonObject:
        if json_size_bytes(value) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata exceeds {MAX_METADATA_BYTES} bytes")
        return value

    @field_validator("payload")
    @classmethod
    def _check_payload(cls, value: JsonObject) -> JsonObject:
        if json_size_bytes(value) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        return value


class HealthRecord(RecordFields):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_ref: Literal[RECORD_SCHEMA] = Field(default=RECORD_SCHEMA, alias="schema")
    id: str = Field(pattern=id_pattern_regex("record"))
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    deletedAt: AwareDatetime | None = None


class SignalInput(BaseModel):
    """POST /records 内联的信号写入参数：``samples`` 与 ``fileRef`` 二选一。"""

    model_config = ConfigDict(extra="forbid")

    lead: LeadName = Field(pattern=LEAD_PATTERN)
    fs: float | None = Field(default=None, gt=0, le=1_000_000)
    unit: UnitCode | None = Field(default=None, pattern=UCUM_PATTERN)
    samples: list[float] | None = None
    fileRef: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _exactly_one_source(self) -> SignalInput:
        if (self.samples is None) == (self.fileRef is None):
            raise ValueError("provide exactly one of samples or fileRef")
        return self


class RecordCreate(RecordFields):
    signal: SignalInput | None = None


class RecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recordType: NamespaceId | None = Field(default=None, pattern=NAMESPACE_PATTERN)
    moduleId: NamespaceId | None = Field(default=None, pattern=NAMESPACE_PATTERN)
    capturedAt: AwareDatetime | None = None
    timezone: str | None = None
    source: SourceInfo | None = None
    samplingRate: float | None = Field(default=None, gt=0, le=1_000_000)
    leads: list[LeadName] | None = Field(default=None, max_length=MAX_LEADS)
    durationSec: float | None = Field(default=None, ge=0)
    unit: UnitCode | None = Field(default=None, pattern=UCUM_PATTERN)
    quality: Quality | None = None
    tags: list[Tag] | None = Field(default=None, max_length=MAX_TAGS)
    notes: Notes | None = None
    favorite: bool | None = None
    metadata: JsonObject | None = None
    payload: JsonObject | None = None
    provenance: Provenance | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        return None if value is None else _validate_timezone(value)

    @field_validator("leads")
    @classmethod
    def _check_leads(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("leads must be unique")
        return value

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("tags must be unique")
        return value

    @field_validator("metadata")
    @classmethod
    def _check_metadata(cls, value: JsonObject | None) -> JsonObject | None:
        if value is not None and json_size_bytes(value) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata exceeds {MAX_METADATA_BYTES} bytes")
        return value

    @field_validator("payload")
    @classmethod
    def _check_payload(cls, value: JsonObject | None) -> JsonObject | None:
        if value is not None and json_size_bytes(value) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        return value


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: DisplayName
    birthYear: int | None = Field(default=None, ge=1900, le=2100)
    sex: Literal["female", "male", "other", "unknown"] = "unknown"
    heightCm: float | None = Field(default=None, ge=30, le=300)
    weightKg: float | None = Field(default=None, ge=2, le=500)
    conditions: list[ShortText] = Field(default_factory=list, max_length=32)
    medications: list[ShortText] = Field(default_factory=list, max_length=32)
    notes: Notes = ""


class MemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: DisplayName | None = None
    birthYear: int | None = Field(default=None, ge=1900, le=2100)
    sex: Literal["female", "male", "other", "unknown"] | None = None
    heightCm: float | None = Field(default=None, ge=30, le=300)
    weightKg: float | None = Field(default=None, ge=2, le=500)
    conditions: list[ShortText] | None = Field(default=None, max_length=32)
    medications: list[ShortText] | None = Field(default=None, max_length=32)
    notes: Notes | None = None


__all__ = [
    "HealthRecord",
    "Member",
    "MemberCreate",
    "MemberUpdate",
    "Provenance",
    "Quality",
    "QualitySegment",
    "QualityWarning",
    "RecordCreate",
    "RecordFields",
    "RecordUpdate",
    "Signal",
    "SignalInput",
    "SignalStorage",
    "SourceInfo",
]
