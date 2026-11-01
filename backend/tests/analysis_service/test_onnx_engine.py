"""A3 · 通用 ONNX 分析引擎：模块引擎目录、可用性、执行与 API 落库。

fixture 模块只贡献 onnxruntime 自带的 ``mul_1.onnx``（输入 [3,2] → 输出 [3,2]），
不依赖任何真实第三方模型；Cardia 仍由内置路径负责。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from analysis_service_helpers import create_ecg_record, make_sine, wait_for_analysis
from fastapi.testclient import TestClient

from eclipse_health_backend.analysis_service import CARDIA_ENGINE
from eclipse_health_backend.analysis_service.engines import (
    get_engine,
    get_module_model_spec,
    list_engines,
)
from eclipse_health_backend.analysis_service.onnx_engine import (
    OnnxEngineError,
    OnnxEngineRunner,
)

MODULE_ID = "io.github.example.onnx-lab"
MODEL_ID = "tiny-mul"
ENGINE_ID = f"{MODULE_ID}:{MODEL_ID}"
MODEL_SHA = "71f431c4e9321ec6fbeb158d02ed240459a7dcc98673fa79a4f439ce42efaf10"


def _spec():
    spec = get_module_model_spec(ENGINE_ID)
    assert spec is not None
    return spec


def _module_dir(manager: Any) -> Any:
    version = manager.get_module(MODULE_ID)["version"]
    return manager.modules_root / MODULE_ID / version


# ---------------------------------------------------------------------- 目录
def test_catalog_lists_module_engine_next_to_cardia(onnx_engines: Any) -> None:
    descriptors = list_engines()
    ids = [item.id for item in descriptors]
    assert ids[0] == CARDIA_ENGINE
    assert ENGINE_ID in ids
    engine = get_engine(ENGINE_ID)
    assert engine is not None
    assert engine.module_id == MODULE_ID
    assert engine.model_id == MODEL_ID
    assert engine.model_version == "0.1.0"
    assert engine.available is True
    assert engine.reason is None


def test_cardia_module_is_not_duplicated_as_engine(
    module_manager: Any,
    cardia_package: Any,
    onnx_package: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cardia 模块即使已安装，也只由内置 ``cardia`` 表示。"""
    import eclipse_health_backend.analysis_service.engines as engines_module

    module_manager.install(cardia_package, enable=True)
    module_manager.install(onnx_package, enable=True)
    monkeypatch.setattr(engines_module, "_module_manager", lambda: module_manager)
    assert [item.id for item in list_engines()] == [CARDIA_ENGINE, ENGINE_ID]


def test_disabled_module_disappears_from_catalog(onnx_engines: Any) -> None:
    onnx_engines.disable(MODULE_ID)
    assert ENGINE_ID not in [item.id for item in list_engines()]
    assert get_engine(ENGINE_ID) is None


def test_missing_model_file_marks_engine_unavailable(onnx_engines: Any) -> None:
    (_module_dir(onnx_engines) / "models" / "mul_1.onnx").unlink()
    engine = get_engine(ENGINE_ID)
    assert engine is not None
    assert engine.available is False
    assert engine.reason and "缺失" in engine.reason


def test_checksum_mismatch_marks_engine_unavailable(onnx_engines: Any) -> None:
    target = _module_dir(onnx_engines) / "models" / "mul_1.onnx"
    target.write_bytes(b"tampered-model")
    engine = get_engine(ENGINE_ID)
    assert engine is not None
    assert engine.available is False
    assert engine.reason and "校验失败" in engine.reason


# ---------------------------------------------------------------------- 执行器
def test_runner_maps_classification_result(onnx_engines: Any) -> None:
    spec = _spec()
    result = OnnxEngineRunner(spec).analyze(
        record_id="rec_test",
        analysis_id="ana_test",
        samples=make_sine(n=64),
        fs=360.0,
        lead="MLII",
    )
    assert result["engine"] == ENGINE_ID
    assert result["moduleId"] == MODULE_ID
    assert result["modelId"] == MODEL_ID
    assert result["modelVersion"] == "0.1.0"
    assert result["task"] == "classification"
    assert result["status"] == "completed"
    assert result["beats"] == []
    assert "非逐搏诊断" in result["summary"]
    codes = {item["code"] for item in result["measurements"]}
    assert codes == {
        f"{MODULE_ID}.class_probability.A",
        f"{MODULE_ID}.class_probability.B",
    }
    total = sum(float(item["value"]) for item in result["measurements"])
    assert abs(total - 100.0) < 1e-6
    warning_codes = {item["code"] for item in result["warnings"]}
    assert {"non_diagnostic_model", "third_party_model"} <= warning_codes
    provenance = result["provenance"]
    assert provenance["modelSha256"] == MODEL_SHA
    assert provenance["modelFile"] == "models/mul_1.onnx"
    assert provenance["preprocess"]["normalize"] == "zscore"
    assert provenance["windows"] == 32


def test_runner_aggregation_is_deterministic(onnx_engines: Any) -> None:
    spec = _spec()
    samples = make_sine(n=64)
    runner = OnnxEngineRunner(spec)
    first = runner.analyze(
        record_id="rec_test", analysis_id="ana_test", samples=samples, fs=360.0, lead="MLII"
    )
    second = runner.analyze(
        record_id="rec_test", analysis_id="ana_test", samples=samples, fs=360.0, lead="MLII"
    )
    assert [m["value"] for m in first["measurements"]] == [
        m["value"] for m in second["measurements"]
    ]


def test_runner_shape_mismatch_is_engine_error(onnx_engines: Any) -> None:
    spec = _spec()
    model = dict(spec.model)
    model["input"] = {**model["input"], "windowSamples": 3}
    model["preprocess"] = {**model["preprocess"], "windowSamples": 3, "strideSamples": 3}
    broken = replace(spec, model=model)
    with pytest.raises(OnnxEngineError) as caught:
        OnnxEngineRunner(broken).analyze(
            record_id="rec_test",
            analysis_id="ana_test",
            samples=make_sine(n=64),
            fs=360.0,
            lead="MLII",
        )
    assert caught.value.code == "engine_error"
    assert "不匹配" in caught.value.message


def test_runner_rejects_unsupported_output_type(onnx_engines: Any) -> None:
    spec = _spec()
    model = dict(spec.model)
    model["output"] = {"type": "segmentation"}
    with pytest.raises(OnnxEngineError) as caught:
        OnnxEngineRunner(replace(spec, model=model)).analyze(
            record_id="rec_test",
            analysis_id="ana_test",
            samples=make_sine(n=64),
            fs=360.0,
            lead="MLII",
        )
    assert caught.value.code == "engine_error"
    assert "segmentation" in caught.value.message


def test_runner_short_signal_respects_tail_mode(onnx_engines: Any) -> None:
    runner = OnnxEngineRunner(_spec())
    short = np.asarray([0.2], dtype=np.float32)
    padded = runner.analyze(
        record_id="rec_test",
        analysis_id="ana_test",
        samples=short,
        fs=360.0,
        lead="MLII",
        tail_mode="pad",
    )
    assert padded["provenance"]["windows"] == 1
    assert "tail_padded" in {item["code"] for item in padded["warnings"]}

    with pytest.raises(OnnxEngineError) as caught:
        runner.analyze(
            record_id="rec_test",
            analysis_id="ana_test",
            samples=short,
            fs=360.0,
            lead="MLII",
            tail_mode="drop",
        )
    assert caught.value.code == "engine_error"


# ---------------------------------------------------------------------- API
def test_api_runs_module_engine_and_persists_result(
    client: TestClient, default_member: dict, onnx_engines: Any
) -> None:
    catalog = client.get("/api/v1/analyses/engines").json()["items"]
    item = next(entry for entry in catalog if entry["id"] == ENGINE_ID)
    assert item["available"] is True

    record = create_ecg_record(client, default_member["id"], make_sine(n=600))
    response = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"engine": ENGINE_ID}
    )
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["engine"] == ENGINE_ID

    detail = wait_for_analysis(client, accepted["analysisId"], timeout=60.0)
    assert detail["status"] == "completed", detail.get("error")
    assert detail["engine"] == ENGINE_ID
    assert detail["moduleId"] == MODULE_ID
    assert detail["modelId"] == MODEL_ID
    assert detail["modelVersion"] == "0.1.0"
    assert detail["beatsTotal"] == 0
    assert detail["beats"] == []
    assert len(detail["measurements"]) == 2
    assert detail["provenance"]["modelSha256"] == MODEL_SHA
    assert "non_diagnostic_model" in {w["code"] for w in detail["warnings"]}


def test_api_unknown_module_engine_is_rejected(
    client: TestClient, default_member: dict, onnx_engines: Any
) -> None:
    record = create_ecg_record(client, default_member["id"], make_sine(n=600))
    response = client.post(
        f"/api/v1/records/{record['id']}/analyses",
        json={"engine": f"{MODULE_ID}:not-a-model"},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "unknown_engine"
    assert ENGINE_ID in body["details"]["supported"]


def test_api_unavailable_module_engine_fails_with_reason(
    client: TestClient, default_member: dict, onnx_engines: Any
) -> None:
    (_module_dir(onnx_engines) / "models" / "mul_1.onnx").unlink()
    record = create_ecg_record(client, default_member["id"], make_sine(n=600))
    response = client.post(
        f"/api/v1/records/{record['id']}/analyses", json={"engine": ENGINE_ID}
    )
    assert response.status_code == 202, response.text
    detail = wait_for_analysis(client, response.json()["analysisId"], timeout=30.0)
    assert detail["status"] == "failed"
    assert detail["error"]["code"] == "engine_unavailable"
    assert "缺失" in detail["error"]["message"]
