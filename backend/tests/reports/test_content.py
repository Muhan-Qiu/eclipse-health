"""内容模型的脱敏约束：脱敏时不含姓名/备注，未脱敏时包含。"""

from __future__ import annotations

import json

from reports_helpers import create_record_with_analysis

from eclipse_health_backend.db import analysis_repo
from eclipse_health_backend.db.base import session_scope
from eclipse_health_backend.db.repositories import get_record_row
from eclipse_health_backend.domain.ids import new_id
from eclipse_health_backend.reports.content import WATERMARK, build_report_content


def _content(record_id: str, analysis_id: str, *, redact: bool):
    with session_scope() as session:
        record_row = get_record_row(session, record_id)
        analysis_row = analysis_repo.get_analysis_row(session, analysis_id)
        assert record_row is not None and analysis_row is not None
        return build_report_content(
            session,
            record_row,
            analysis_row,
            template="detailed",
            redact=redact,
            report_id=new_id("report"),
        )


def test_redacted_content_has_no_name_or_notes(client, default_member):
    record, analysis_id = create_record_with_analysis(client, default_member["id"])
    content = _content(record["id"], analysis_id, redact=True)
    data = content.as_dict()

    assert content.redacted is True
    assert content.member_name == "匿名"
    assert content.notes is None
    assert content.watermark == WATERMARK
    serialized = json.dumps(data, ensure_ascii=False)
    assert "本人" not in serialized
    assert "晨起心悸" not in serialized
    # 原始文件名从不进入内容模型（记录层只存哈希）。
    assert "fileName" not in data
    assert "fileNameHash" not in serialized


def test_unredacted_content_includes_name_and_notes(client, default_member):
    record, analysis_id = create_record_with_analysis(client, default_member["id"])
    content = _content(record["id"], analysis_id, redact=False)

    assert content.redacted is False
    assert content.member_name == default_member["displayName"]
    assert content.notes is not None and "晨起心悸" in content.notes
    assert content.watermark is None


def test_content_metrics_and_class_ratios(client, default_member):
    record, analysis_id = create_record_with_analysis(client, default_member["id"])
    content = _content(record["id"], analysis_id, redact=True)

    assert content.metrics["heart_rate_mean"] == 72.4
    assert content.metrics["rmssd"] == 62.9
    assert content.class_counts == {"N": 12, "SVEB": 1, "VEB": 1, "F": 0}
    assert content.class_ratios["N"] == 85.71
    assert content.beats_total == 14
    assert content.waveform is not None
    assert content.waveform.duration_sec == 12.0
    assert len(content.waveform.rpeaks) >= 10
