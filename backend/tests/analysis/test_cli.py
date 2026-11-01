"""CLI：WFDB / CSV、输出 JSON、非法输入退出码。"""

from __future__ import annotations

import json

from eclipse_health_backend.analysis.cli import main


def test_cli_wfdb(tmp_path, samples_dir, analysis_100) -> None:
    out = tmp_path / "analysis-100.json"
    code = main(
        [
            "--record",
            str(samples_dir / "100"),
            "--format",
            "wfdb",
            "--out",
            str(out),
            "--record-id",
            "rec_cli",
        ]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["recordId"] == "rec_cli"
    assert data["schema"] == "org.eclipsehealth.analysis/1"
    assert data["parameters"]["nBeatsClassified"] == 2271


def test_cli_csv_500hz(tmp_path, synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=500, duration=80)
    source = tmp_path / "watch.csv"
    lines = ["time,ecg"] + [
        f"{index / 500:.6f},{value:.6f}" for index, value in enumerate(signal)
    ]
    source.write_text("\n".join(lines), encoding="utf-8")

    out = tmp_path / "analysis-watch.json"
    code = main(
        [
            "--csv",
            str(source),
            "--fs",
            "500",
            "--lead",
            "I",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["parameters"]["originalFs"] == 500.0
    assert data["parameters"]["resampled"] is True
    assert data["parameters"]["rpeakSource"] == "detected"
    assert data["parameters"]["nBeatsClassified"] >= 64


def test_cli_missing_file(tmp_path) -> None:
    code = main(["--csv", str(tmp_path / "missing.csv"), "--fs", "500"])
    assert code == 2


def test_cli_csv_without_fs(tmp_path, synthetic_ecg) -> None:
    signal, _ = synthetic_ecg(fs=500, duration=10)
    source = tmp_path / "no_fs.csv"
    source.write_text("\n".join(f"{v:.6f}" for v in signal), encoding="utf-8")
    assert main(["--csv", str(source)]) == 2
