"""Open Food Facts 模块：manifest、条码/营养映射与 worker 参数路径。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "modules" / "community" / "openfoodfacts"

PRODUCT = {
    "code": "3017620422003",
    "product_name": "Nutella",
    "brands": "Ferrero",
    "nutriments": {
        "energy-kcal_100g": 539,
        "proteins_100g": 6.3,
        "carbohydrates_100g": 57.5,
        "fat_100g": 30.9,
        "sugars_100g": 56.3,
        "salt_100g": 0.107,
    },
    "nutriscore_grade": "E",
    "nova_group": 4,
}


def _load(name: str) -> ModuleType:
    path = MODULE_DIR / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"official_openfoodfacts_{name}", path)
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
    assert manifest["id"] == "io.github.openfoodfacts.openfoodfacts"
    assert manifest["dependencies"] == ["openfoodfacts>=1.0,<2"]
    assert manifest["allowedHosts"] == ["world.openfoodfacts.org"]


def test_barcode_validation(adapter: ModuleType) -> None:
    assert adapter.normalize_barcode("3017620422003") == "3017620422003"
    assert adapter.normalize_barcode(" 96385074 ") == "96385074"
    with pytest.raises(ValueError):
        adapter.normalize_barcode("1234567")
    with pytest.raises(ValueError):
        adapter.normalize_barcode("30176204ABC")
    with pytest.raises(TypeError):
        adapter.normalize_barcode(123)


def test_normalize_product(adapter: ModuleType) -> None:
    product = adapter.normalize_product(PRODUCT)
    assert product["name"] == "Nutella"
    assert product["barcode"] == "3017620422003"
    assert product["nutriscoreGrade"] == "e"
    assert product["novaGroup"] == 4
    assert product["per100g"]["energyKcal"] == 539
    assert product["per100g"]["proteinG"] == 6.3


def test_normalize_product_energy_fallback(adapter: ModuleType) -> None:
    product = adapter.normalize_product({"product_name": "X", "nutriments": {"energy_100g": 418.4}})
    assert product["per100g"]["energyKcal"] == 100.0


def test_normalize_product_rejects_non_dict(adapter: ModuleType) -> None:
    with pytest.raises(TypeError):
        adapter.normalize_product([])  # type: ignore[arg-type]


def test_lookup_result_and_record(adapter: ModuleType) -> None:
    result = adapter.lookup_result("3017620422003", PRODUCT, found=True)
    assert result["found"] is True
    assert "ODbL" in result["attribution"]
    record = adapter.to_record(result["product"], 50)
    assert record["consumedGrams"] == 50
    assert record["energyKcal"] == 269.5
    assert record["proteinG"] == 3.15
    assert "非医疗器械" in record["nonDiagnostic"]


def test_lookup_result_not_found(adapter: ModuleType) -> None:
    result = adapter.lookup_result("3017620422003", None, found=False)
    assert result["found"] is False
    assert result["product"] is None


def test_to_record_rejects_bad_amount(adapter: ModuleType) -> None:
    product = adapter.normalize_product(PRODUCT)
    with pytest.raises(ValueError):
        adapter.to_record(product, 0)
    with pytest.raises(TypeError):
        adapter.to_record(product, "100")  # type: ignore[arg-type]


def test_worker_lookup_requires_barcode(worker: ModuleType) -> None:
    with pytest.raises(worker.RpcError) as info:
        worker.handle("lookup", {})
    assert info.value.data["code"] == "INVALID_INPUT"
    with pytest.raises(worker.RpcError):
        worker.handle("mapProduct", {"barcode": "bad"})


def test_worker_latest_and_health(worker: ModuleType) -> None:
    latest = worker.handle("latestProduct", {})
    assert latest["available"] is False
    assert latest["per100g"]["energyKcal"] == 0
    health = worker.handle("health", {})
    assert health["requiresNetwork"] is True
    assert "openfoodfactsAvailable" in health
