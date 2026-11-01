"""SCP-ECG：真实 EN 1064 段结构、真实样本、合成变体与坏段报错。"""

from __future__ import annotations

import numpy as np
import pytest
from format_builders import build_scp_ecg
from import_helpers import BACKEND_ROOT, commit, read_signal, upload_preview

LEAD_I = [100, -100, 200, -200, 300, -300, 150, -150]
LEAD_II = [40, 50, 60, 70, 80, 90, 100, 110]
REAL_SAMPLE = BACKEND_ROOT / "tests" / "fixtures" / "imports" / "scp-ecg" / "example.scp"
HEALFORCE_SAMPLE = (
    BACKEND_ROOT / "tests" / "fixtures" / "imports" / "scp-ecg" / "healforce-62.scp"
)


def _preview(client, payload: bytes, **form) -> dict:
    response = upload_preview(client, "ecg.scp", payload, **form)
    assert response.status_code == 200, response.text
    return response.json()


def test_synthetic_preview_commit_and_lead_names(client, default_member: dict) -> None:
    payload = build_scp_ecg([(1, LEAD_I), (2, LEAD_II)], interval_us=2000)
    preview = _preview(client, payload)

    assert preview["format"] == "scp-ecg"
    assert preview["adapterId"] == "org.eclipsehealth.scp-ecg"
    assert preview["samplingRate"] == 500.0
    assert preview["leads"] == ["I", "II"]
    assert preview["durationSec"] == pytest.approx(8 / 500)
    assert preview["requires"] == {"samplingRate": False, "lead": False, "unit": False}

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["leads"] == ["I", "II"]
    assert record["metadata"]["verification"] == "verified"
    assert record["metadata"]["amplitudeMultiplierNv"] == 1000
    assert record["metadata"]["encoding"] == 0
    assert record["metadata"]["sourceUnit"] == "nV"

    np.testing.assert_allclose(
        read_signal(client, record["id"], "I"),
        np.asarray(LEAD_I) * 0.001,
        atol=1e-7,
    )
    np.testing.assert_allclose(
        read_signal(client, record["id"], "II"),
        np.asarray(LEAD_II) * 0.001,
        atol=1e-7,
    )


def test_first_difference_encoding(client, default_member: dict) -> None:
    differences = [10, 10, -5, 4, -20, 3, 0, 8]
    payload = build_scp_ecg([(1, differences)], encoding=1, interval_us=2000)
    preview = _preview(client, payload)
    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["metadata"]["encoding"] == 1
    expected = np.cumsum(differences) * 0.001
    np.testing.assert_allclose(read_signal(client, record["id"], "I"), expected, atol=1e-7)


def test_second_difference_encoding(client, default_member: dict) -> None:
    encoded = [5, 8, 1, 1]  # 还原为 [5, 8, 12, 17]
    payload = build_scp_ecg([(1, encoded)], encoding=2, interval_us=2000)
    preview = _preview(client, payload)
    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    np.testing.assert_allclose(
        read_signal(client, record["id"], "I"),
        np.asarray([5, 8, 12, 17]) * 0.001,
        atol=1e-7,
    )


def test_real_public_sample_is_verified(client, default_member: dict) -> None:
    payload = REAL_SAMPLE.read_bytes()
    preview = _preview(client, payload)
    assert preview["samplingRate"] == 500.0
    assert preview["durationSec"] == pytest.approx(10.0)
    assert len(preview["leads"]) == 12
    assert preview["leads"][:3] == ["I", "II", "V1"]
    assert preview["preview"]["nSamples"] == 5000

    response = commit(client, preview["importId"], default_member["id"])
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert len(record["leads"]) == 12
    assert record["metadata"]["huffman"] is True
    assert record["metadata"]["encoding"] == 2
    assert record["metadata"]["verification"] == "verified"
    samples = read_signal(client, record["id"], "I")
    assert samples.size == 5000
    assert np.isfinite(samples).all()
    assert float(np.max(np.abs(samples))) < 10.0


def test_custom_huffman_is_explicitly_unsupported(client) -> None:
    payload = build_scp_ecg([(1, LEAD_I)], custom_huffman=True)
    response = upload_preview(client, "custom.scp", payload)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "unsupported_section"
    assert error["details"]["section"] == 2


def test_missing_lead_section_is_unsupported(client) -> None:
    payload = build_scp_ecg([(1, LEAD_I)], include_lead_section=False)
    response = upload_preview(client, "nolead.scp", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_section"
    assert response.json()["details"]["section"] == 3


def test_missing_data_section_is_unsupported(client) -> None:
    payload = build_scp_ecg([(1, LEAD_I)], include_data_section=False)
    response = upload_preview(client, "nodata.scp", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_section"
    assert response.json()["details"]["section"] == 6


def test_missing_pointer_section_is_invalid(client) -> None:
    payload = build_scp_ecg([(1, LEAD_I)], include_pointer=False)
    response = upload_preview(client, "nop.scp", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_file"


def test_truncated_section_is_invalid(client) -> None:
    payload = build_scp_ecg([(1, LEAD_I)])
    response = upload_preview(client, "cut.scp", payload[:-3])
    assert response.status_code == 422
    assert response.json()["code"] in {"invalid_file", "unsupported_section"}


def test_unknown_lead_id_needs_confirmation(client) -> None:
    payload = build_scp_ecg([(200, LEAD_I)])
    preview = _preview(client, payload)
    assert preview["leads"] == ["L200"]
    assert preview["requires"]["lead"] is True
    assert any(item["code"] == "lead_unknown" for item in preview["warnings"])


def test_non_simultaneous_leads_are_unsupported(client) -> None:
    payload = build_scp_ecg([(1, LEAD_I), (2, LEAD_II)], flags=0)
    response = upload_preview(client, "nonsim.scp", payload)
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_section"
    assert response.json()["details"]["section"] == 3


def test_fixture_path_is_small() -> None:
    # 防止有人把大样本塞进仓库。
    assert REAL_SAMPLE.is_file()
    assert REAL_SAMPLE.stat().st_size < 64 * 1024


def test_healforce_variant_is_explicitly_unsupported(client) -> None:
    """Healforce Prince 180D 不是合规 SCP-ECG，必须报错而不是按标准解码。"""
    if not HEALFORCE_SAMPLE.exists():
        pytest.skip("B4-02 fixture not delivered")
    response = upload_preview(client, "healforce-62.scp", HEALFORCE_SAMPLE.read_bytes())
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_section"
