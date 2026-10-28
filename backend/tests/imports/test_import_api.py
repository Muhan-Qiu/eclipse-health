"""导入 API 的安全与生命周期：格式占位、ZIP 防护、TTL、工作区隔离。"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

import pytest
from import_helpers import (
    API,
    commit,
    csv_text,
    path_preview,
    sha256_tag,
    upload_preview,
    zip_samples,
)

from eclipse_health_backend.importers import limits, store
from eclipse_health_backend.importers.errors import ImportNotFoundError
from eclipse_health_backend.importers.registry import build_default_registry

VALUES = [float(value) for value in range(50)]
CSV = csv_text(VALUES, header="time,MLII", time_step=0.002)


def _zip_with(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _write_meta(data_dir, import_id: str, created_at: str) -> None:
    path = data_dir / "imports" / import_id / store.META_FILE
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["createdAt"] = created_at
    path.write_text(json.dumps(meta), encoding="utf-8")


def test_unknown_format_is_unsupported(client, data_dir) -> None:
    root = data_dir / "imports"
    before = {path.name for path in root.iterdir()} if root.exists() else set()
    response = upload_preview(client, "raw.bin", b"\x00\x01\x02" * 100)
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_format"
    # 失败的预览不留下新工作区。
    assert {path.name for path in root.iterdir()} == before


@pytest.mark.parametrize("fmt", ["samsung", "huawei", "apple", "scp-ecg"])
def test_vendor_placeholders_are_explicitly_unsupported(client, fmt: str) -> None:
    response = upload_preview(client, "ecg.csv", CSV, hintFormat=fmt)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "unsupported_format"
    assert error["details"]["supported"] is False
    assert error["details"]["format"] == fmt


def test_vendor_placeholders_registered_but_unsupported() -> None:
    registry = build_default_registry()
    for fmt in ("samsung", "huawei", "apple", "scp-ecg"):
        adapter = registry.find(fmt)
        assert adapter is not None
        assert adapter.supported is False


def test_unknown_hint_is_rejected(client) -> None:
    response = upload_preview(client, "ecg.csv", CSV, hintFormat="nope")
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_format"


def test_wrong_hint_falls_back_to_content(client) -> None:
    response = upload_preview(client, "ecg.csv", CSV, hintFormat="wfdb")
    assert response.status_code == 200, response.text
    assert response.json()["format"] == "csv"


def test_file_and_path_are_mutually_exclusive(client, samples_dir) -> None:
    response = client.post(
        f"{API}/imports/preview",
        files={"file": ("ecg.csv", CSV.encode("utf-8"), "text/csv")},
        data={"path": str(samples_dir / "100.hea")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_relative_path_is_rejected(client) -> None:
    response = path_preview(client, "resources/samples/100.hea")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_path"


def test_missing_path_is_rejected(client, tmp_path) -> None:
    response = path_preview(client, tmp_path / "nope.csv")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_path"


def test_zip_traversal_entry_is_rejected(client) -> None:
    archive = _zip_with({"../evil.csv": b"1,2\n3,4\n"})
    response = upload_preview(client, "evil.zip", archive)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "zip_traversal"
    assert error["details"]["entry"] == "../evil.csv"


def test_zip_entry_name_backslash_guard() -> None:
    """Python 的 zipfile 读入时会把 ``\\`` 归一成 ``/``；这里直接验证兜底守卫。"""

    class FakeInfo:
        filename = "folder\\evil.csv"
        external_attr = 0
        flag_bits = 0

    from eclipse_health_backend.importers.errors import InvalidImportFileError
    from eclipse_health_backend.importers.store import _entry_name

    with pytest.raises(InvalidImportFileError) as excinfo:
        _entry_name(FakeInfo())
    assert excinfo.value.code == "zip_unsafe"


def test_zip_file_count_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(limits, "ZIP_MAX_FILES", 1)
    archive = _zip_with({"a.csv": CSV.encode("utf-8"), "b.csv": CSV.encode("utf-8")})
    response = upload_preview(client, "many.zip", archive)
    assert response.status_code == 422
    assert response.json()["code"] == "archive_too_large"


def test_zip_total_size_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(limits, "ZIP_MAX_TOTAL_BYTES", 1024)
    archive = zip_samples("100")
    response = upload_preview(client, "100.zip", archive)
    assert response.status_code == 422
    assert response.json()["code"] == "archive_too_large"


def test_upload_size_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(limits, "MAX_UPLOAD_BYTES", 256)
    response = upload_preview(client, "big.csv", CSV)
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


def test_path_size_limit(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(limits, "MAX_UPLOAD_BYTES", 256)
    target = tmp_path / "big.csv"
    target.write_text(CSV, encoding="utf-8")
    response = path_preview(client, target)
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


def test_upload_filename_cannot_escape_workspace(client, data_dir) -> None:
    response = upload_preview(client, "../../escape.csv", CSV)
    assert response.status_code == 200, response.text
    assert response.json()["fileNameHash"] == sha256_tag(b"escape.csv")
    assert not (data_dir / "escape.csv").exists()
    assert not (data_dir.parent / "escape.csv").exists()


def test_empty_upload_is_rejected(client) -> None:
    response = upload_preview(client, "empty.csv", b"")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_delete_discards_workspace(client, data_dir) -> None:
    preview = upload_preview(client, "del.csv", CSV).json()
    workspace = data_dir / "imports" / preview["importId"]
    assert workspace.is_dir()

    assert client.delete(f"{API}/imports/{preview['importId']}").status_code == 204
    assert not workspace.exists()
    assert client.delete(f"{API}/imports/{preview['importId']}").status_code == 204


def test_ttl_cleanup_removes_expired_workspace(client, data_dir, default_member: dict) -> None:
    preview = upload_preview(client, "ttl.csv", CSV).json()
    import_id = preview["importId"]
    _write_meta(data_dir, import_id, "2020-01-01T00:00:00+00:00")

    removed = store.cleanup_expired(now=datetime(2030, 1, 1, tzinfo=UTC))
    assert import_id in removed
    assert not (data_dir / "imports" / import_id).exists()

    response = commit(client, import_id, default_member["id"])
    assert response.status_code == 404


def test_expired_workspace_access_reports_import_expired(
    client, data_dir, default_member: dict
) -> None:
    preview = upload_preview(client, "old.csv", CSV).json()
    import_id = preview["importId"]
    _write_meta(data_dir, import_id, "2020-01-01T00:00:00+00:00")

    with pytest.raises(ImportNotFoundError) as excinfo:
        store.load_workspace(import_id)
    assert excinfo.value.code == "import_expired"

    response = commit(client, import_id, default_member["id"])
    assert response.status_code == 404


def test_workspaces_are_isolated(client, data_dir, default_member: dict) -> None:
    first = upload_preview(client, "first.csv", CSV).json()
    second = upload_preview(
        client, "second.csv", csv_text(VALUES, header="time,ECG", time_step=0.002)
    ).json()

    assert first["importId"] != second["importId"]
    assert (data_dir / "imports" / first["importId"]).is_dir()
    assert (data_dir / "imports" / second["importId"]).is_dir()

    response = commit(client, first["importId"], default_member["id"], unit="mV")
    assert response.status_code == 201, response.text
    assert not (data_dir / "imports" / first["importId"]).exists()
    assert (data_dir / "imports" / second["importId"]).is_dir()

    response = commit(client, second["importId"], default_member["id"], unit="mV")
    assert response.status_code == 201, response.text


def test_multiple_wfdb_records_in_zip_is_ambiguous(client) -> None:
    from import_helpers import SAMPLES_DIR

    bundle_bytes = io.BytesIO()
    with zipfile.ZipFile(bundle_bytes, "w") as bundle:
        for record in ("100", "200"):
            for suffix in (".hea", ".dat", ".atr"):
                source = SAMPLES_DIR / f"{record}{suffix}"
                if source.exists():
                    bundle.write(source, f"{record}{suffix}")

    response = upload_preview(client, "multi.zip", bundle_bytes.getvalue())
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "invalid_file"
    assert len(error["details"]["candidates"]) == 2


def test_committed_record_signal_metadata(client, default_member: dict) -> None:
    preview = upload_preview(client, "meta.csv", CSV).json()
    record = commit(client, preview["importId"], default_member["id"], unit="mV").json()[
        "record"
    ]

    signals = client.get(f"{API}/records/{record['id']}/signals").json()
    assert len(signals) == 1
    assert signals[0]["lead"] == "MLII"
    assert signals[0]["fs"] == 500.0
    assert signals[0]["unit"] == "mV"
    assert signals[0]["shape"] == [50]
