"""合成 Apple 健康导出（export.xml + electrocardiograms/*.csv）。

不是真实用户导出；字段按 Apple 官方导出文档与社区样本布局合成，仅用于解析测试。
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

START = "2026-10-28 10:00:00 +0800"
ECG_START = "2026-10-28 10:05:00 +0800"


def record(
    type_: str,
    *,
    value: str,
    unit: str = "",
    start: str = START,
    end: str | None = None,
    source: str = "Apple Watch",
    uuid: str | None = None,
) -> str:
    attrs = [
        f'type="{type_}"',
        f'sourceName="{escape(source)}"',
        'sourceVersion="11.0"',
        f'unit="{escape(unit)}"',
        f'creationDate="{start}"',
        f'startDate="{start}"',
        f'endDate="{end or start}"',
        f'value="{escape(value)}"',
    ]
    if uuid:
        attrs.append(f'uuid="{uuid}"')
    return f"<Record {' '.join(attrs)} />"


def correlation(
    *,
    start: str = START,
    end: str | None = None,
    systolic: str = "120",
    diastolic: str = "80",
    unit: str = "mmHg",
) -> str:
    return (
        f'<Correlation type="HKCorrelationTypeIdentifierBloodPressure" '
        f'sourceName="Apple Watch" startDate="{start}" endDate="{end or start}">'
        f'<Record type="HKQuantityTypeIdentifierBloodPressureSystolic" '
        f'sourceName="Apple Watch" unit="{unit}" startDate="{start}" '
        f'endDate="{end or start}" value="{systolic}" />'
        f'<Record type="HKQuantityTypeIdentifierBloodPressureDiastolic" '
        f'sourceName="Apple Watch" unit="{unit}" startDate="{start}" '
        f'endDate="{end or start}" value="{diastolic}" />'
        "</Correlation>"
    )


def export_xml(*, include_sleep: bool = True, include_ignored: bool = True) -> str:
    body = [
        f"<HealthData locale=\"en_US\"><ExportDate value=\"{START}\" />",
        record("HKQuantityTypeIdentifierStepCount", value="1000", unit="count"),
        record("HKQuantityTypeIdentifierStepCount", value="1500", unit="count"),
        record("HKQuantityTypeIdentifierHeartRate", value="72", unit="count/min"),
        record("HKQuantityTypeIdentifierHeartRate", value="75", unit="count/min"),
        record("HKQuantityTypeIdentifierBodyMass", value="70.5", unit="kg"),
        correlation(),
        record(
            "HKDataTypeIdentifierElectrocardiogram",
            value="",
            start=ECG_START,
            source="Apple Watch",
        ),
    ]
    if include_sleep:
        body.append(
            record(
                "HKCategoryTypeIdentifierSleepAnalysis",
                value="HKCategoryValueSleepAnalysisAsleepCore",
                start="2026-10-27 23:00:00 +0800",
                end="2026-10-28 01:00:00 +0800",
            )
        )
    if include_ignored:
        body.append(
            record(
                "HKQuantityTypeIdentifierActiveEnergyBurned",
                value="320",
                unit="kcal",
            )
        )
    body.append("</HealthData>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "".join(body)


def ecg_csv(*, fs: float = 512.0, seconds: float = 2.0, recorded_at: str | None = None) -> str:
    lines: list[str] = []
    if recorded_at:
        lines.append(f'Date: {recorded_at}, "Classification: Sinus Rhythm"')
    lines.append("time,voltage")
    count = int(fs * seconds)
    for index in range(count):
        seconds_value = index / fs
        volts = (index % 64 - 32) / 100000.0  # -0.00032..0.00031 V
        lines.append(f"{seconds_value:.9f},{volts:.9f}")
    return "\n".join(lines) + "\n"


def apple_zip(
    *,
    xml: str | None = None,
    ecg_files: dict[str, str] | None = None,
    prefix: str = "apple_health_export/",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if xml is not None:
            archive.writestr(f"{prefix}export.xml", xml)
        for name, content in (ecg_files or {}).items():
            archive.writestr(f"{prefix}electrocardiograms/{name}", content)
    return buffer.getvalue()


__all__ = ["ECG_START", "START", "apple_zip", "correlation", "ecg_csv", "export_xml", "record"]
