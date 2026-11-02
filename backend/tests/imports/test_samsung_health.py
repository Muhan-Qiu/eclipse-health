"""Samsung Health 导出目录 / ZIP：解析、计数、提交。"""

from __future__ import annotations

import io
import zipfile

from import_helpers import API, commit, upload_preview

STEPS = """﻿com.samsung.shealth.tracker.pedometer_step_count,6305106,2
duration,version_code,com.samsung.health.step_count.start_time,com.samsung.health.step_count.time_offset,com.samsung.health.step_count.count
1,4,2026-10-19 04:10:00.000,UTC+0800,10
1,4,2026-10-19 04:11:00.000,UTC+0800,86
1,4,2026-10-20 08:00:00.000,UTC+0800,1200
"""

HEART_RATE = """﻿com.samsung.shealth.tracker.heart_rate,6305106,3
com.samsung.health.heart_rate.start_time,com.samsung.health.heart_rate.time_offset,com.samsung.health.heart_rate.min,com.samsung.health.heart_rate.max,com.samsung.health.heart_rate.heart_rate,com.samsung.health.heart_rate.datauuid
2026-10-19 03:00:00.000,UTC+0800,54,99,86,abc
2026-10-19 04:00:00.000,UTC+0800,78,145,103,def
"""

WEIGHT = """﻿com.samsung.health.weight,6305106,1
start_time,time_offset,weight,datauuid
2026-10-25 10:30:51.769,UTC+0800,60.7,ghi
"""

SLEEP = """﻿com.samsung.shealth.sleep,6305106,12
sleep_duration,sleep_score,efficiency,com.samsung.health.sleep.start_time,com.samsung.health.sleep.time_offset,com.samsung.health.sleep.end_time,com.samsung.health.sleep.datauuid
75,55,91.0,2026-10-23 04:23:00.000,UTC+0800,2026-10-23 05:38:00.000,sleep-uuid
"""


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(f"samsunghealth_123_20261101221958/{name}", text.encode("utf-8"))
    return buffer.getvalue()


def test_samsung_zip_preview_and_commit(client, default_member: dict) -> None:
    payload = _zip(
        {
            "com.samsung.shealth.tracker.pedometer_step_count.20261101221958.csv": STEPS,
            "com.samsung.shealth.tracker.heart_rate.20261101221958.csv": HEART_RATE,
            "com.samsung.health.weight.20261101221958.csv": WEIGHT,
            "com.samsung.shealth.sleep.20261101221958.csv": SLEEP,
        }
    )
    response = upload_preview(client, "samsung.zip", payload)
    assert response.status_code == 200, response.text
    preview = response.json()

    assert preview["format"] == "samsung-health"
    assert preview["adapterId"] == "org.eclipsehealth.samsung-health"
    # 两天步数、两条心率、一条体重、一条睡眠。
    assert preview["recordCounts"] == {
        "steps": 2,
        "heartRate": 2,
        "sleep": 1,
        "bodyMass": 1,
    }
    assert preview["totalRecords"] == 6

    result = commit(client, preview["importId"], default_member["id"])
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["created"] == 6
    assert body["failed"] == 0

    steps = client.get(
        f"{API}/records", params={"recordType": "org.eclipsehealth.health.steps"}
    ).json()["items"]
    assert len(steps) == 2
    assert sorted(item["payload"]["value"] for item in steps) == [96, 1200]
