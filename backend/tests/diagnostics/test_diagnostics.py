"""诊断包：内容、版本信息、PHI 排除、用户名脱敏。"""

from __future__ import annotations

import getpass
import io
import json
import zipfile
from pathlib import Path

from diagnostics_helpers import create_record

from eclipse_health_backend.settings import get_settings

PHI_NOTE = "PHI_NOTE_SECRET_987"
PHI_PAYLOAD = {"secret": "PHI_PAYLOAD_123"}


def _bundle(client) -> zipfile.ZipFile:
    response = client.get("/api/v1/diagnostics/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_bundle_contains_versions_and_schema(client):
    archive = _bundle(client)
    assert sorted(archive.namelist()) == ["diagnostics.json", "logs.txt", "system.txt"]
    payload = json.loads(archive.read("diagnostics.json"))
    assert payload["app"]["name"] == "eclipse health"
    assert payload["runtime"]["python"]
    assert payload["database"]["schemaVersion"] == "0001_core"
    assert payload["engine"]["onnxruntime"] is None or isinstance(
        payload["engine"]["onnxruntime"], str
    )
    assert payload["settings"]["telemetryEnabled"] is False
    assert payload["logs"]["truncated"] is False
    system = archive.read("system.txt").decode("utf-8")
    assert "cpuCount" in system


def test_bundle_excludes_phi(client, default_member):
    create_record(
        client,
        default_member["id"],
        notes=PHI_NOTE,
        payload=PHI_PAYLOAD,
    )
    archive = _bundle(client)
    combined = "\n".join(
        archive.read(name).decode("utf-8", errors="replace")
        for name in archive.namelist()
    )
    assert PHI_NOTE not in combined
    assert "PHI_PAYLOAD_123" not in combined
    assert default_member["displayName"] not in combined
    assert "waveform" not in combined.lower()
    # 数据量可以出现，但不能出现具体记录 ID 或成员 ID。
    assert default_member["id"] not in combined


def test_bundle_redacts_username_in_logs(client):
    settings = get_settings()
    logs_dir = settings.data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    username = getpass.getuser()
    home = str(Path.home())
    (logs_dir / "redaction-test.log").write_text(
        f"trace at {home}\\Documents\\secret.txt and C:\\Users\\{username}\\notes.txt\n",
        encoding="utf-8",
    )
    archive = _bundle(client)
    text = archive.read("logs.txt").decode("utf-8")
    assert "<user>" in text
    assert username not in text
    assert home not in text
    assert "secret.txt" in text  # 文件名保留，只脱敏用户名


def test_bundle_works_with_empty_data(client):
    archive = _bundle(client)
    payload = json.loads(archive.read("diagnostics.json"))
    assert payload["storage"]["counts"]["records"] == 0
    assert archive.read("logs.txt")


def test_diagnostics_download_filename(client):
    response = client.get("/api/v1/diagnostics/bundle")
    assert response.headers["content-disposition"] == (
        'attachment; filename="eclipse-health-diagnostics.zip"'
    )
