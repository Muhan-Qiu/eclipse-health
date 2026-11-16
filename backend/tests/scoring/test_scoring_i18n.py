"""G2 · 评分/建议的 ``lang`` 参数：默认中文，``lang=en`` 时不返回 CJK 文案。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from scoring_helpers import add_ecg_analysis, add_health_record, measurement

SCORES = "/api/v1/scores"
SUGGESTIONS = "/api/v1/suggestions"

# 汉字 + CJK 标点/全角符号；英文文案不应命中任何一段。
CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")
ALL_MISSING_ZH = ["心脏", "睡眠", "体重", "活动", "血压"]
ALL_MISSING_EN = ["Heart", "Sleep", "Weight", "Activity", "Blood pressure"]


def _days_ago(days: int, hour: int = 8) -> datetime:
    moment = datetime.now(UTC) - timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def _sleep_night(member_id: str, captured_at: datetime) -> None:
    """一晚 8 小时：深睡 2h + REM 1.5h + 浅睡 4.5h。"""
    for stage, seconds in (
        ("asleep-deep", 7200),
        ("asleep-rem", 5400),
        ("asleep-core", 16200),
    ):
        add_health_record(
            member_id,
            "org.eclipsehealth.health.sleep",
            captured_at,
            {"value": stage},
            duration_sec=seconds,
        )


def _seed_all_categories(member_id: str) -> None:
    add_health_record(
        member_id,
        "org.eclipsehealth.health.heart-rate",
        _days_ago(1),
        {"value": 62, "unit": "count/min", "resting": True},
    )
    add_ecg_analysis(
        member_id,
        _days_ago(1, hour=9),
        [
            measurement("heart_rate_mean", 68, "bpm"),
            measurement("rmssd", 42),
            measurement("svb_ratio", 1.0, "%"),
            measurement("veb_ratio", 0.5, "%"),
            measurement("f_ratio", 0.0, "%"),
        ],
        quality={"score": 0.9, "level": "good"},
    )
    _sleep_night(member_id, _days_ago(1, hour=23))
    for index in range(7):
        add_health_record(
            member_id,
            "org.eclipsehealth.health.steps",
            _days_ago(index + 1),
            {"value": 9000, "unit": "count"},
        )
    add_health_record(
        member_id,
        "org.eclipsehealth.health.blood-pressure",
        _days_ago(1),
        {"value": {"systolic": 118, "diastolic": 76}, "unit": "mm[Hg]"},
    )


def _assert_no_cjk(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    match = CJK.search(text)
    assert match is None, f"unexpected CJK text: {text}"


def test_default_lang_is_chinese(api_client: TestClient) -> None:
    default = api_client.get(SCORES).json()
    explicit = api_client.get(SCORES, params={"lang": "zh"}).json()
    assert default["missing"] == ALL_MISSING_ZH
    assert default["disclaimer"] == "基于公开区间规则的参考评分，不是医学诊断"
    for key in ("overall", "grade", "categories", "missing", "disclaimer"):
        assert default[key] == explicit[key]
    assert api_client.get(SUGGESTIONS).json()["items"][0]["id"] == "import-health-data"


def test_english_empty_report_and_suggestion(api_client: TestClient) -> None:
    body = api_client.get(SCORES, params={"lang": "en"}).json()
    _assert_no_cjk(body)
    assert body["overall"] is None
    assert body["categories"] == []
    assert body["missing"] == ALL_MISSING_EN
    assert "not a medical diagnosis" in body["disclaimer"]

    suggestions = api_client.get(SUGGESTIONS, params={"lang": "en"}).json()["items"]
    _assert_no_cjk(suggestions)
    assert [item["id"] for item in suggestions] == ["import-health-data"]
    assert suggestions[0]["prompt"]


def test_english_seeded_report_and_suggestions(
    api_client: TestClient, default_member: dict
) -> None:
    member_id = default_member["id"]
    assert (
        api_client.patch(
            f"/api/v1/members/{member_id}",
            json={"heightCm": 170, "weightKg": 65},
        ).status_code
        == 200
    )
    _seed_all_categories(member_id)

    body = api_client.get(SCORES, params={"lang": "en"}).json()
    _assert_no_cjk(body)
    assert body["missing"] == []
    labels = {item["id"]: item["label"] for item in body["categories"]}
    assert labels == {
        "heart": "Heart",
        "sleep": "Sleep",
        "weight": "Weight",
        "activity": "Activity",
        "blood_pressure": "Blood pressure",
    }

    heart = next(item for item in body["categories"] if item["id"] == "heart")
    factors = " | ".join(heart["factors"])
    assert "Resting heart rate" in factors
    assert "HRV (RMSSD)" in factors
    assert "Abnormal beat ratio" in factors
    assert "Recent ECG signal quality" in factors
    sleep = next(item for item in body["categories"] if item["id"] == "sleep")
    assert any("Average sleep" in factor for factor in sleep["factors"])
    weight = next(item for item in body["categories"] if item["id"] == "weight")
    assert any(factor.startswith("BMI ") for factor in weight["factors"])
    activity = next(item for item in body["categories"] if item["id"] == "activity")
    assert any("Daily average" in factor for factor in activity["factors"])

    suggestions = api_client.get(SUGGESTIONS, params={"lang": "en"}).json()["items"]
    _assert_no_cjk(suggestions)
    assert suggestions
    assert all(item["text"] and item["prompt"] for item in suggestions)


def test_english_category_subitem_missing(
    api_client: TestClient, default_member: dict
) -> None:
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.heart-rate",
        _days_ago(1),
        {"value": 62, "unit": "count/min"},
    )

    category = api_client.get(SCORES, params={"lang": "en"}).json()["categories"][0]
    _assert_no_cjk(category)
    assert category["label"] == "Heart"
    assert category["missing"] == [
        "No usable HRV (RMSSD) analysis result",
        "No ECG beat classification result",
        "No signal quality data",
    ]
