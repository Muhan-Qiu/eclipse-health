"""G2 · 规则评分、缺失项、总分与建议排序。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from conftest import (
    add_ecg_analysis,
    add_health_record,
    measurement,
)

SCORES = "/api/v1/scores"
SUGGESTIONS = "/api/v1/suggestions"
DISCLAIMER = "基于公开区间规则的参考评分，不是医学诊断"
ALL_MISSING = ["心脏", "睡眠", "体重", "活动", "血压"]


def _days_ago(days: int, hour: int = 8) -> datetime:
    moment = datetime.now(UTC) - timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def _sleep_night(member_id: str, captured_at: datetime) -> None:
    """一晚 8 小时：深睡 2h + REM 1.5h + 浅睡 4.5h。"""
    add_health_record(
        member_id,
        "org.eclipsehealth.health.sleep",
        captured_at,
        {"value": "asleep-deep"},
        duration_sec=7200,
    )
    add_health_record(
        member_id,
        "org.eclipsehealth.health.sleep",
        captured_at,
        {"value": "asleep-rem"},
        duration_sec=5400,
    )
    add_health_record(
        member_id,
        "org.eclipsehealth.health.sleep",
        captured_at,
        {"value": "asleep-core"},
        duration_sec=16200,
    )


def test_empty_report_and_suggestion(api_client: TestClient) -> None:
    report = api_client.get(SCORES)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["overall"] is None
    assert body["grade"] == "unknown"
    assert body["categories"] == []
    assert body["missing"] == ALL_MISSING
    assert body["disclaimer"] == DISCLAIMER
    assert body["memberId"]
    assert body["windowDays"] == 30

    suggestions = api_client.get(SUGGESTIONS).json()["items"]
    assert [item["id"] for item in suggestions] == ["import-health-data"]
    assert suggestions[0]["severity"] == "info"
    assert suggestions[0]["category"] == "general"
    assert suggestions[0]["prompt"]


def test_unknown_member_returns_empty_not_500(api_client: TestClient) -> None:
    report = api_client.get(SCORES, params={"memberId": "mem_missing"})
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["overall"] is None
    assert body["categories"] == []
    assert body["missing"] == ALL_MISSING

    suggestions = api_client.get(SUGGESTIONS, params={"memberId": "mem_missing"})
    assert suggestions.status_code == 200
    assert suggestions.json()["items"][0]["id"] == "import-health-data"


def test_only_heart_rate(api_client: TestClient, default_member: dict) -> None:
    for index, value in enumerate((60, 62, 64, 66, 68)):
        add_health_record(
            default_member["id"],
            "org.eclipsehealth.health.heart-rate",
            _days_ago(index + 1),
            {"value": value, "unit": "count/min"},
        )

    body = api_client.get(SCORES).json()
    assert body["overall"] == 100
    assert body["grade"] == "excellent"
    assert [item["id"] for item in body["categories"]] == ["heart"]
    assert body["categories"][0]["score"] == 100
    assert "静息心率" in body["categories"][0]["factors"][0]
    assert body["categories"][0]["missing"] == [
        "缺少可用的 HRV（RMSSD）分析结果",
        "缺少心电图搏动分类结果",
        "缺少信号质量数据",
    ]
    assert body["missing"] == ["睡眠", "体重", "活动", "血压"]


def test_heart_uses_ecg_submetrics(api_client: TestClient, default_member: dict) -> None:
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.heart-rate",
        _days_ago(1),
        {"value": 62, "unit": "count/min"},
    )
    add_ecg_analysis(
        default_member["id"],
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

    category = api_client.get(SCORES).json()["categories"][0]
    assert category["id"] == "heart"
    assert category["score"] == 93
    assert category["evidenceCount"] == 4
    assert category["missing"] == []
    assert any("RMSSD" in factor for factor in category["factors"])
    assert any("异常搏动占比 1.5%" in factor for factor in category["factors"])
    assert any("信号质量 0.90" in factor for factor in category["factors"])


def test_sleep_and_weight(api_client: TestClient, default_member: dict) -> None:
    assert (
        api_client.patch(
            f"/api/v1/members/{default_member['id']}",
            json={"heightCm": 170, "weightKg": 65},
        ).status_code
        == 200
    )
    _sleep_night(default_member["id"], _days_ago(1, hour=23))
    _sleep_night(default_member["id"], _days_ago(2, hour=23))

    body = api_client.get(SCORES).json()
    assert [item["id"] for item in body["categories"]] == ["sleep", "weight"]
    sleep, weight = body["categories"]
    assert sleep["score"] == 100
    assert any("平均睡眠 8.0 h" in factor for factor in sleep["factors"])
    assert any("深睡/REM 占比 44%" in factor for factor in sleep["factors"])
    assert weight["score"] == 100
    assert any("BMI 22.5" in factor for factor in weight["factors"])
    assert body["overall"] == 100
    assert body["missing"] == ["心脏", "活动", "血压"]
    assert body["disclaimer"] == DISCLAIMER


def test_high_blood_pressure_and_low_steps(
    api_client: TestClient, default_member: dict
) -> None:
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.blood-pressure",
        _days_ago(1),
        {"value": {"systolic": 145, "diastolic": 92}, "unit": "mm[Hg]"},
    )
    for index in range(7):
        add_health_record(
            default_member["id"],
            "org.eclipsehealth.health.steps",
            _days_ago(index + 1),
            {"value": 3000, "unit": "count"},
        )

    body = api_client.get(SCORES).json()
    categories = {item["id"]: item for item in body["categories"]}
    assert categories["activity"]["score"] == 38
    assert categories["blood_pressure"]["score"] == 45
    assert body["overall"] == 42
    assert body["grade"] == "attention"
    assert any("日均 3000 步" in factor for factor in categories["activity"]["factors"])
    assert any("145/92 mmHg" in factor for factor in categories["blood_pressure"]["factors"])

    items = api_client.get(SUGGESTIONS).json()["items"]
    assert items[0]["id"] == "improve-activity"
    assert items[0]["severity"] == "attention"
    assert len(items) <= 3
    assert {item["severity"] for item in items[1:]} == {"info"}


def test_overall_averages_only_available(
    api_client: TestClient, default_member: dict
) -> None:
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.heart-rate",
        _days_ago(1),
        {"value": 62, "unit": "count/min"},
    )
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.blood-pressure",
        _days_ago(1),
        {"value": {"systolic": 118, "diastolic": 76}, "unit": "mm[Hg]"},
    )

    body = api_client.get(SCORES).json()
    assert body["overall"] == 100
    assert len(body["categories"]) == 2
    assert body["missing"] == ["睡眠", "体重", "活动"]


def test_suggestion_targets_lowest_category(
    api_client: TestClient, default_member: dict
) -> None:
    member_id = default_member["id"]
    api_client.patch(
        f"/api/v1/members/{member_id}", json={"heightCm": 160, "weightKg": 100}
    )
    add_health_record(
        member_id,
        "org.eclipsehealth.health.heart-rate",
        _days_ago(1),
        {"value": 70, "unit": "count/min"},
    )
    _sleep_night(member_id, _days_ago(1, hour=23))
    for index in range(7):
        add_health_record(
            member_id,
            "org.eclipsehealth.health.steps",
            _days_ago(index + 1),
            {"value": 1000, "unit": "count"},
        )
    add_health_record(
        member_id,
        "org.eclipsehealth.health.blood-pressure",
        _days_ago(1),
        {"value": {"systolic": 160, "diastolic": 100}, "unit": "mm[Hg]"},
    )

    items = api_client.get(SUGGESTIONS).json()["items"]
    assert [item["id"] for item in items] == ["improve-activity"]
    assert items[0]["severity"] == "attention"
    assert items[0]["category"] == "activity"


def test_invalid_payload_is_ignored(api_client: TestClient, default_member: dict) -> None:
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.heart-rate",
        _days_ago(1),
        {"value": "not-a-number"},
    )
    add_health_record(
        default_member["id"],
        "org.eclipsehealth.health.blood-pressure",
        _days_ago(1),
        {"value": {"systolic": 120}},
    )

    body = api_client.get(SCORES).json()
    assert body["overall"] is None
    assert body["categories"] == []
    assert body["missing"] == ALL_MISSING
