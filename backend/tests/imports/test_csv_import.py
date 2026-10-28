"""CSV 适配器：分隔符、表头、时间列、编码、校正与错误定位。"""

from __future__ import annotations

import numpy as np
import pytest
from import_helpers import (
    API,
    commit,
    csv_text,
    read_signal,
    sha256_tag,
    upload_preview,
)

VALUES = [round(float(value), 6) for value in np.sin(np.arange(500) / 10.0)]


def _preview(client, name: str, text: str, **form) -> dict:
    response = upload_preview(client, name, text, **form)
    assert response.status_code == 200, response.text
    return response.json()


def test_semicolon_with_ms_time_and_unit(client, default_member: dict) -> None:
    text = csv_text(VALUES, header="time_ms;MLII(mV)", separator=";", time_step=2.0)
    preview = _preview(client, "ecg.csv", text)

    assert preview["format"] == "csv"
    assert preview["adapterId"] == "org.eclipsehealth.csv"
    assert preview["samplingRate"] == 500.0
    assert preview["leads"] == ["MLII"]
    assert preview["durationSec"] == pytest.approx(1.0)
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}
    assert preview["preview"]["nSamples"] == 500
    assert preview["preview"]["samples"][0] == pytest.approx(VALUES[0], abs=1e-9)

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["leads"] == ["MLII"]
    assert record["samplingRate"] == 500.0
    assert record["durationSec"] == pytest.approx(1.0)
    assert record["metadata"]["sourceUnit"] == "mV"
    assert record["metadata"]["hasAnnotations"] is False

    samples = read_signal(client, record["id"], "MLII")
    np.testing.assert_allclose(samples, VALUES, rtol=0, atol=1e-6)


def test_common_lead_header_is_confident(client) -> None:
    preview = _preview(client, "ii.csv", csv_text(VALUES, header="time,II", time_step=0.002))
    assert preview["leads"] == ["II"]
    assert preview["requires"]["lead"] is False


def test_time_seconds_tab_requires_unit(client, default_member: dict) -> None:
    rows = ["time\tECG"] + [f"{index * 0.004:.6f}\t{value}" for index, value in enumerate(VALUES)]
    preview = _preview(client, "tab.tsv", "\n".join(rows) + "\n")

    assert preview["samplingRate"] == 250.0
    assert preview["leads"] == ["ECG"]
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": True}

    missing = commit(client, preview["importId"], default_member["id"])
    assert missing.status_code == 422
    assert missing.json()["code"] == "unit_required"

    response = commit(client, preview["importId"], default_member["id"], unit="mV")
    assert response.status_code == 201, response.text
    assert response.json()["record"]["samplingRate"] == 250.0


def test_no_header_needs_full_correction(client, default_member: dict) -> None:
    preview = _preview(client, "raw.csv", csv_text(VALUES))
    assert preview["leads"] == []
    assert preview["samplingRate"] is None
    assert preview["requires"] == {"samplingRate": True, "lead": True, "unit": True}

    body = commit(client, preview["importId"], default_member["id"])
    assert body.status_code == 422
    assert body.json()["code"] == "sampling_rate_required"

    body = commit(client, preview["importId"], default_member["id"], samplingRate=500)
    assert body.json()["code"] == "lead_required"

    body = commit(
        client,
        preview["importId"],
        default_member["id"],
        samplingRate=500,
        lead="II",
    )
    assert body.json()["code"] == "unit_required"

    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        samplingRate=500,
        lead="II",
        unit="mV",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["leads"] == ["II"]
    np.testing.assert_allclose(read_signal(client, record["id"], "II"), VALUES, atol=1e-6)


def test_gbk_chinese_header_and_bom(client, default_member: dict) -> None:
    gbk_rows = ["时间,心电"] + [
        f"{index * 0.002:.6f},{value}" for index, value in enumerate(VALUES)
    ]
    data = ("\n".join(gbk_rows) + "\n").encode("gbk")
    response = upload_preview(client, "gbk.csv", data)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["samplingRate"] == 500.0
    assert preview["leads"] == ["ECG"]
    assert any(item["code"] == "fallback_encoding" for item in preview["warnings"])

    bom_rows = ["TIME,ECG"] + [f"{index * 0.002:.6f},{value}" for index, value in enumerate(VALUES)]
    bom = b"\xef\xbb\xbf" + ("\n".join(bom_rows) + "\n").encode("utf-8")
    preview_bom = upload_preview(client, "bom.csv", bom)
    assert preview_bom.status_code == 200, preview_bom.text
    assert preview_bom.json()["leads"] == ["ECG"]


def test_bad_cell_reports_row_and_column(client) -> None:
    text = "ecg\n0.1\nnot-a-number\n0.3\n"
    response = upload_preview(client, "bad.csv", text)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "invalid_file"
    assert error["details"] == {"row": 3, "column": 1, "value": "not-a-number"}


def test_inconsistent_columns(client) -> None:
    text = "time,ecg\n0,0.1\n0.002,0.2,9.9\n"
    response = upload_preview(client, "ragged.csv", text)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "invalid_file"
    assert error["details"]["row"] == 3
    assert error["details"]["expectedColumns"] == 2


def test_index_column_and_voltage(client, default_member: dict) -> None:
    rows = ["index,voltage"] + [f"{index},{value}" for index, value in enumerate(VALUES)]
    preview = _preview(client, "index.csv", "\n".join(rows) + "\n")
    assert preview["samplingRate"] is None
    assert preview["leads"] == ["ECG"]
    assert preview["requires"] == {"samplingRate": True, "lead": False, "unit": True}

    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        samplingRate=500,
        unit="mV",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["samplingRate"] == 500.0
    assert record["durationSec"] == pytest.approx(1.0)
    np.testing.assert_allclose(read_signal(client, record["id"], "ECG"), VALUES, atol=1e-6)


def test_unit_correction_uv_to_mv(client, default_member: dict) -> None:
    microvolts = [round(value * 1000.0, 3) for value in VALUES]
    preview = _preview(client, "uv.csv", csv_text(microvolts, header="ecg"))
    assert preview["requires"]["unit"] is True

    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        samplingRate=500,
        unit="uV",
        lead="II",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["sourceUnit"] == "uV"
    np.testing.assert_allclose(read_signal(client, record["id"], "II"), VALUES, atol=1e-6)


def test_polarity_inversion(client, default_member: dict) -> None:
    text = csv_text(VALUES, header="time,MLII", time_step=0.002)
    preview = _preview(client, "polarity.csv", text)
    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        unit="mV",
        polarity="inverted",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["polarity"] == "inverted"
    np.testing.assert_allclose(
        read_signal(client, record["id"], "MLII"), -np.asarray(VALUES), atol=1e-6
    )


def test_lead_rename_and_column_override(client, default_member: dict) -> None:
    values = list(range(100))
    rows = ["t,a,b"]
    rows += [f"{index * 0.01:.3f},{index},{values[index] / 100.0}" for index in range(100)]
    preview = _preview(client, "columns.csv", "\n".join(rows) + "\n")
    assert preview["samplingRate"] == 100.0
    assert preview["requires"]["lead"] is True

    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        leadColumn="2",
        timeColumn="0",
        lead="V2",
        unit="mV",
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["leads"] == ["V2"]
    expected = [value / 100.0 for value in values]
    np.testing.assert_allclose(read_signal(client, record["id"], "V2"), expected, atol=1e-6)


def test_preview_samples_capped(client) -> None:
    values = list(np.sin(np.arange(3000) / 10.0))
    preview = _preview(client, "long.csv", csv_text(values))
    assert preview["preview"]["nSamples"] == 3000
    assert len(preview["preview"]["samples"]) == 2000


def test_hashes_reflect_file_and_name(client) -> None:
    text = csv_text(VALUES, header="time,MLII", time_step=0.002)
    data = text.encode("utf-8")
    preview = _preview(client, "named.csv", data)
    assert preview["fileHash"] == sha256_tag(data)
    assert preview["fileNameHash"] == sha256_tag(b"named.csv")


def test_unknown_unit_parameter_is_rejected(client, default_member: dict) -> None:
    preview = _preview(client, "unit.csv", csv_text(VALUES, header="time,MLII", time_step=0.002))
    response = commit(
        client,
        preview["importId"],
        default_member["id"],
        unit="banana",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_parameter"


def test_member_must_exist(client) -> None:
    preview = _preview(client, "m.csv", csv_text(VALUES, header="time,MLII", time_step=0.002))
    response = commit(client, preview["importId"], "mem_00000000-0000-7000-8000-000000000000")
    assert response.status_code == 404
    assert response.json()["code"] == "member_not_found"


def test_commit_unknown_import_is_404(client, default_member: dict) -> None:
    response = commit(
        client,
        "imp_00000000-0000-7000-8000-000000000000",
        default_member["id"],
    )
    assert response.status_code == 404


def test_header_unit_is_applied_without_parameter(client, default_member: dict) -> None:
    microvolts = [round(value * 1000.0, 3) for value in VALUES]
    text = csv_text(microvolts, header="time,II(uV)", time_step=0.002)
    preview = _preview(client, "uv_header.csv", text)
    assert preview["leads"] == ["II"]
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["sourceUnit"] == "uV"
    np.testing.assert_allclose(read_signal(client, record["id"], "II"), VALUES, atol=1e-6)


def test_csv_parsed_result_feeds_ecg_signal(tmp_path) -> None:
    from eclipse_health_backend.importers.base import ImportSource, ParseParameters
    from eclipse_health_backend.importers.csv_adapter import CsvImportAdapter

    path = tmp_path / "ecg.csv"
    path.write_text(csv_text(VALUES, header="time,MLII", time_step=0.002), encoding="utf-8")
    adapter = CsvImportAdapter()
    source = ImportSource(kind="upload", path=path, workspace=tmp_path)
    parsed = adapter.parse(source, ParseParameters(unit="mV"))
    signal = parsed.to_ecg_signals()[0]

    assert signal.lead == "MLII"
    assert signal.fs == 500.0
    assert signal.samples.dtype == np.float32
    assert signal.n_samples == len(VALUES)
    np.testing.assert_allclose(signal.samples, VALUES, rtol=0, atol=1e-6)


def test_record_list_contains_imported(client, default_member: dict) -> None:
    preview = _preview(client, "list.csv", csv_text(VALUES, header="time,MLII", time_step=0.002))
    record = commit(client, preview["importId"], default_member["id"], unit="mV").json()[
        "record"
    ]
    page = client.get(f"{API}/records", params={"moduleId": "org.eclipsehealth.csv"}).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == record["id"]
