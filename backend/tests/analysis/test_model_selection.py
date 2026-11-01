"""模型文件选择：简化图优先、原图回退、环境变量覆盖（不加载 ONNX）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from eclipse_health_backend.analysis import model as model_module
from eclipse_health_backend.analysis.model import (
    ORIGINAL_MODEL_FILE,
    SIMPLIFIED_MODEL_FILE,
    resolve_model_path,
)
from eclipse_health_backend.analysis.types import DEFAULT_MODEL_DIR


def _model_dir(tmp_path: Path, *, with_simplified: bool = False) -> Path:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / ORIGINAL_MODEL_FILE).write_bytes(b"original")
    if with_simplified:
        (model_dir / SIMPLIFIED_MODEL_FILE).write_bytes(b"simplified")
    return model_dir


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(model_module.MODEL_ENV, raising=False)
    monkeypatch.delenv(model_module.MODEL_PATH_ENV, raising=False)


def test_simplified_is_preferred_when_present(tmp_path: Path) -> None:
    model_dir = _model_dir(tmp_path, with_simplified=True)
    assert resolve_model_path(model_dir).name == SIMPLIFIED_MODEL_FILE


def test_original_is_used_when_simplified_missing(tmp_path: Path) -> None:
    model_dir = _model_dir(tmp_path)
    assert resolve_model_path(model_dir).name == ORIGINAL_MODEL_FILE


def test_original_env_forces_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_dir = _model_dir(tmp_path, with_simplified=True)
    monkeypatch.setenv(model_module.MODEL_ENV, "original")
    assert resolve_model_path(model_dir).name == ORIGINAL_MODEL_FILE


def test_sim_env_still_falls_back_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = _model_dir(tmp_path)
    monkeypatch.setenv(model_module.MODEL_ENV, "sim")
    assert resolve_model_path(model_dir).name == ORIGINAL_MODEL_FILE


def test_explicit_path_env_is_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = _model_dir(tmp_path, with_simplified=True)
    custom = tmp_path / "module" / "weights.onnx"
    custom.parent.mkdir()
    custom.write_bytes(b"module-weights")
    monkeypatch.setenv(model_module.MODEL_PATH_ENV, str(custom))
    assert resolve_model_path(model_dir) == custom


def test_missing_explicit_path_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = _model_dir(tmp_path, with_simplified=True)
    monkeypatch.setenv(model_module.MODEL_PATH_ENV, str(tmp_path / "missing.onnx"))
    assert resolve_model_path(model_dir).name == SIMPLIFIED_MODEL_FILE


def test_model_path_argument_beats_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = _model_dir(tmp_path, with_simplified=True)
    monkeypatch.setenv(model_module.MODEL_ENV, "original")
    custom = tmp_path / "explicit.onnx"
    custom.write_bytes(b"explicit")
    assert resolve_model_path(model_dir, custom) == custom


def test_unknown_env_value_behaves_like_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = _model_dir(tmp_path, with_simplified=True)
    monkeypatch.setenv(model_module.MODEL_ENV, "Simpified")  # 拼写错误
    assert resolve_model_path(model_dir).name == SIMPLIFIED_MODEL_FILE


def test_repo_ships_both_weights() -> None:
    assert (DEFAULT_MODEL_DIR / ORIGINAL_MODEL_FILE).is_file()
    simplified = DEFAULT_MODEL_DIR / SIMPLIFIED_MODEL_FILE
    assert simplified.is_file()
    assert hashlib.sha256(simplified.read_bytes()).hexdigest() == (
        "f59128614d185076926f9943f514fa94774cd99319a6a6cf14686bd08237bf53"
    )
