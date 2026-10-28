"""manifest JSON Schema 与兼容性测试。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manifest import (
    Manifest,
    check_compatibility,
    load_manifest_file,
    parse_manifest,
)
from eclipse_health_backend.modules.semver import satisfies

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = sorted((ROOT / "schemas" / "examples").glob("*.module.json"))
DEMO_MANIFEST = json.loads((ROOT / "modules" / "demo.echo" / "module.json").read_text(encoding="utf-8"))


def _manifest(**overrides):
    data = copy.deepcopy(DEMO_MANIFEST)
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def test_schema_is_valid_2020_12() -> None:
    schema = json.loads((ROOT / "schemas" / "module.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda item: item.name)
def test_example_manifests_are_valid(path: Path) -> None:
    manifest = load_manifest_file(path)
    assert manifest.id
    assert manifest.type.value
    check_compatibility(manifest)


def test_demo_manifest_is_valid() -> None:
    manifest = parse_manifest(DEMO_MANIFEST)
    assert isinstance(manifest, Manifest)
    assert manifest.id == "org.eclipsehealth.demo.echo"
    assert manifest.entry_path == "src/main.py"
    assert manifest.startup_timeout_s == 5.0


@pytest.mark.parametrize(
    "data",
    [
        _manifest(version=None),
        _manifest(id="org.eclipsehealth"),
        _manifest(id="io.github.someone.thing_extra"),
        _manifest(version="1.0"),
        _manifest(permissions=["totally:unknown"]),
        _manifest(permissions=["network"]),
        _manifest(entry={"python": "../main.py", "factory": "create_module"}),
        _manifest(contributes={}),
        _manifest(extraField=True),
    ],
    ids=[
        "missing-version",
        "bad-id",
        "bad-id-underscore",
        "bad-semver",
        "unknown-permission",
        "network-without-hosts",
        "path-traversal-entry",
        "missing-contribution",
        "additional-property",
    ],
)
def test_invalid_manifests_are_rejected(data: dict) -> None:
    with pytest.raises(ModuleError) as info:
        parse_manifest(data)
    assert info.value.code == "INVALID_INPUT"
    errors = info.value.detail["errors"]
    assert errors
    assert all("path" in item and item["path"].startswith("$") for item in errors)


def test_manifest_error_is_readable() -> None:
    with pytest.raises(ModuleError) as info:
        parse_manifest(_manifest(version="one.two.three"))
    assert info.value.detail["errors"][0]["path"] == "$.version"


def test_network_permission_with_allowed_hosts_passes() -> None:
    manifest = parse_manifest(
        _manifest(permissions=["network", "llm"], allowedHosts=["api.example.com"])
    )
    assert manifest.allowed_hosts == ["api.example.com"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("apiVersion", "2.0"), ("engines", {"eclipse": ">=2.0 <3.0"})],
)
def test_incompatible_api_is_rejected(field: str, value: object) -> None:
    manifest = parse_manifest(_manifest(**{field: value}))
    with pytest.raises(ModuleError) as info:
        check_compatibility(manifest)
    assert info.value.code == "INCOMPATIBLE_API"


@pytest.mark.parametrize(
    ("version", "spec", "expected"),
    [
        ("1.0.0", ">=1.0 <2.0", True),
        ("2.0.0", ">=1.0 <2.0", False),
        ("1.2.3", "^1.2.0", True),
        ("2.0.0", "^1.2.0", False),
        ("1.2.9", "~1.2.3", True),
        ("1.3.0", "~1.2.3", False),
        ("1.0.0", "1.0.0", True),
        ("1.0.1", "1.0.0", False),
        ("1.0.0-beta.1", ">=1.0.0", False),
    ],
)
def test_semver_satisfies(version: str, spec: str, expected: bool) -> None:
    assert satisfies(version, spec) is expected


def test_load_manifest_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "module.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ModuleError) as info:
        load_manifest_file(path)
    assert info.value.code == "INVALID_PACKAGE"


def test_load_manifest_rejects_oversize(tmp_path: Path) -> None:
    path = tmp_path / "module.json"
    path.write_text(json.dumps({"padding": "x" * (1024 * 1024 + 10)}), encoding="utf-8")
    with pytest.raises(ModuleError) as info:
        load_manifest_file(path)
    assert info.value.code == "INVALID_PACKAGE"
