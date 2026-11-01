"""GPX Track 模块：manifest、stdlib GPX 解析/导出与 worker 主路径。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "official" / "gpxpy"

GPX_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
  <trk><trkseg>
    <trkpt lat="39.9000" lon="116.4000"><ele>10</ele>
      <time>2026-01-01T10:00:00Z</time>
      <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>120</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions>
    </trkpt>
    <trkpt lat="39.9010" lon="116.4010"><ele>15</ele>
      <time>2026-01-01T10:01:00Z</time>
      <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>130</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions>
    </trkpt>
  </trkseg></trk>
</gpx>
"""


def _load(name: str) -> ModuleType:
    path = MODULE_DIR / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"official_gpxpy_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adapter() -> ModuleType:
    return _load("adapter")


@pytest.fixture(scope="module")
def worker() -> ModuleType:
    return _load("main")


def test_manifest_matches_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["id"] == "io.github.tkrajina.gpxpy"
    assert manifest["dependencies"] == ["gpxpy>=1.6,<2"]


def test_parse_gpx_xml(adapter: ModuleType) -> None:
    points = adapter.parse_gpx_xml(GPX_TEXT)
    assert len(points) == 2
    assert points[0]["heartRate"] == 120
    assert points[1]["ele"] == 15
    assert points[0]["time"].startswith("2026-01-01")


def test_parse_gpx_rejects_invalid_xml(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.parse_gpx_xml("<gpx><trk>")
    with pytest.raises(ValueError):
        adapter.parse_gpx_xml("")


def test_summarize_points(adapter: ModuleType) -> None:
    summary = adapter.summarize_points(adapter.parse_gpx_xml(GPX_TEXT))
    assert summary["samples"] == 2
    assert summary["durationSeconds"] == 60
    assert 0.1 < summary["distanceKm"] < 0.2
    assert summary["elevationGainM"] == 5.0
    assert summary["avgHeartRate"] == 125.0
    assert summary["maxHeartRate"] == 130
    assert "非医疗器械" in summary["nonDiagnostic"]


def test_summarize_empty_is_error(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.summarize_points([])


def test_to_gpx_roundtrip(adapter: ModuleType) -> None:
    text = adapter.to_gpx(
        [{"lat": 39.9, "lon": 116.4, "ele": 10, "time": "2026-01-01T10:00:00Z", "heartRate": 120}]
    )
    points = adapter.parse_gpx_xml(text)
    assert points[0]["heartRate"] == 120
    assert points[0]["lat"] == 39.9


def test_to_gpx_rejects_missing_coordinates(adapter: ModuleType) -> None:
    with pytest.raises(ValueError):
        adapter.to_gpx([{"lat": 39.9}])


def test_worker_summary_and_missing_path(worker: ModuleType, tmp_path: Path) -> None:
    assert worker.handle("initialize", {})["moduleId"] == "io.github.tkrajina.gpxpy"
    gpx_file = tmp_path / "track.gpx"
    gpx_file.write_text(GPX_TEXT, encoding="utf-8")
    result = worker.handle("summary", {"path": str(gpx_file)})
    assert result["summary"]["samples"] == 2
    assert result["record"]["source"] == "gpx"
    with pytest.raises(worker.RpcError) as info:
        worker.handle("summary", {"path": str(tmp_path / "missing.gpx")})
    assert info.value.data["code"] == "INVALID_INPUT"
