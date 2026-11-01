"""H1：manifest dependencies → 每模块 venv、解释器选择、失败回滚与卸载清理。"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import ClassVar

import pytest
from module_test_helpers import DEMO_DIR, DEMO_ID, build_demo_package
from pydantic import ValidationError as PydanticValidationError

from eclipse_health_backend.modules import manager as manager_module
from eclipse_health_backend.modules import package
from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manifest import Manifest, parse_manifest

_DEP = "demo-pkg==0.0.1"


def _demo_manifest(**updates: object) -> dict:
    data = json.loads((DEMO_DIR / "module.json").read_text(encoding="utf-8"))
    data.update(updates)
    return data


def _make_venv_layout(venv: Path) -> None:
    """伪造 venv 目录结构；真实创建 venv 的测试见文件末尾。"""
    python = package.venv_python_path(venv)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    package._site_packages_dir(venv).mkdir(parents=True, exist_ok=True)


def _fake_install(module_dir: Path, dependencies, **_kwargs: object) -> Path | None:
    """替换真实 pip 安装：只写 .ready，供 manager 选择解释器与卸载测试使用。"""
    if not dependencies:
        return None
    venv = package.module_venv_dir(module_dir)
    _make_venv_layout(venv)
    marker = {"dependencyHash": package.dependency_digest(dependencies)}
    (venv / ".ready").write_text(json.dumps(marker), encoding="utf-8")
    return venv


class _FakeHost:
    created: ClassVar[list[_FakeHost]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.alive = True
        _FakeHost.created.append(self)

    def start(self) -> None:
        self.alive = True

    def stop(self) -> None:
        self.alive = False


# ---------------------------------------------------------------- manifest 校验
@pytest.mark.parametrize(
    "spec",
    [
        "pandas>=2.1,<3",
        "pyedflib==0.1.38",
        "numpy",
        "requests[socks]>=2.28 ; python_version >= \"3.9\"",
        "pkg~=1.4.2",
    ],
)
def test_accepts_pep508_dependencies(spec: str) -> None:
    manifest = parse_manifest(_demo_manifest(dependencies=[spec]))
    assert manifest.dependencies == (spec,)


@pytest.mark.parametrize(
    "spec",
    [
        "pkg @ https://example.com/pkg.whl",
        "pkg @ file:///tmp/pkg.whl",
        "file:///tmp/pkg",
        "../pkg",
        "./pkg",
        "/abs/pkg",
        "-e .",
        "C:" + chr(92) + "pkg",
        "pkg" + chr(92) + "x",
        "",
    ],
)
def test_rejects_urls_paths_and_editable(spec: str) -> None:
    with pytest.raises(ModuleError) as info:
        parse_manifest(_demo_manifest(dependencies=[spec]))
    assert info.value.code == "INVALID_INPUT"


def test_empty_dependency_list_is_allowed() -> None:
    assert parse_manifest(_demo_manifest(dependencies=[])).dependencies == ()


def test_dependency_count_limit_and_duplicates() -> None:
    too_many = [f"pkg{index}==1.0" for index in range(33)]
    with pytest.raises(ModuleError):
        parse_manifest(_demo_manifest(dependencies=too_many))
    with pytest.raises(ModuleError):
        parse_manifest(_demo_manifest(dependencies=["pkg==1.0", "pkg==1.0"]))


def test_unknown_top_level_field_still_rejected() -> None:
    data = _demo_manifest()
    data["dependecies"] = ["pkg==1.0"]
    with pytest.raises(ModuleError) as info:
        parse_manifest(data)
    assert info.value.code == "INVALID_INPUT"


def test_manifest_model_validates_dependencies() -> None:
    with pytest.raises(PydanticValidationError):
        Manifest.model_validate(_demo_manifest(dependencies=["../evil"]))
    assert Manifest.model_validate(_demo_manifest(dependencies=["pandas>=2.1,<3"])).dependencies == (
        "pandas>=2.1,<3",
    )


# ---------------------------------------------------------------- venv 安装
def test_empty_dependencies_create_no_venv(tmp_path: Path) -> None:
    module_dir = tmp_path / "mod"
    (module_dir / "venv").mkdir(parents=True)
    (module_dir / "venv" / "stale.txt").write_text("old", encoding="utf-8")
    assert package.install_module_venv(module_dir, []) is None
    assert not (module_dir / "venv").exists()


def test_install_module_venv_runs_expected_commands(tmp_path: Path, monkeypatch) -> None:
    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    calls: list[list[str]] = []

    def fake_run(args, _timeout_s):
        calls.append(list(args))
        if list(args[1:3]) == ["-m", "venv"]:
            _make_venv_layout(Path(args[-1]))
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(package, "_run_command", fake_run)
    venv = package.install_module_venv(module_dir, [_DEP])
    assert venv == module_dir / "venv"
    assert calls[0] == [sys.executable, "-m", "venv", str(module_dir / "venv")]
    pip = calls[1]
    assert pip[:3] == [str(package.venv_python_path(venv)), "-m", "pip"]
    for flag in ("--disable-pip-version-check", "--no-input", "--no-warn-script-location"):
        assert flag in pip
    assert _DEP in pip

    marker = json.loads((venv / ".ready").read_text(encoding="utf-8"))
    assert marker["dependencies"] == [_DEP]
    assert marker["dependencyHash"] == package.dependency_digest([_DEP])
    assert package.read_ready_venv(module_dir, [_DEP]) == package.venv_python_path(venv)
    assert list(venv.rglob("eclipse_health_module.pth")), "模块目录应写入 venv 的 .pth"


def _failing_run(stderr: str):
    def fake_run(args, _timeout_s):
        if list(args[1:3]) == ["-m", "venv"]:
            _make_venv_layout(Path(args[-1]))
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", stderr)

    return fake_run


def test_pip_failure_cleans_half_built_venv(tmp_path: Path, monkeypatch) -> None:
    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    monkeypatch.setattr(package, "_run_command", _failing_run("ERROR: No matching distribution"))
    with pytest.raises(ModuleError) as info:
        package.install_module_venv(module_dir, ["missing-pkg==9.9"])
    assert info.value.detail["installError"] == "MODULE_INSTALL_FAILED"
    assert info.value.detail["reason"] == "pip-install-failed"
    assert not (module_dir / "venv").exists()


def test_pip_missing_and_timeout_are_reported(tmp_path: Path, monkeypatch) -> None:
    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    monkeypatch.setattr(package, "_run_command", _failing_run("No module named pip"))
    with pytest.raises(ModuleError) as info:
        package.install_module_venv(module_dir, [_DEP])
    assert info.value.detail["reason"] == "pip-missing"

    def timeout_run(args, timeout_s):
        raise subprocess.TimeoutExpired(args, timeout_s)

    monkeypatch.setattr(package, "_run_command", timeout_run)
    with pytest.raises(ModuleError) as info:
        package.install_module_venv(module_dir, [_DEP], timeout_s=1)
    assert info.value.detail["reason"] == "timeout"
    assert not (module_dir / "venv").exists()


def test_ready_marker_hash_must_match(tmp_path: Path) -> None:
    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    _fake_install(module_dir, [_DEP])
    assert package.read_ready_venv(module_dir, [_DEP]) is not None
    assert package.read_ready_venv(module_dir, ["other-pkg==2.0"]) is None
    assert package.read_ready_venv(module_dir, []) is None


def test_real_venv_install_from_local_wheel(tmp_path: Path, monkeypatch) -> None:
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    wheel = wheels / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("demo_pkg/__init__.py", "__version__ = '0.0.1'\n")
        archive.writestr(
            "demo_pkg-0.0.1.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: demo-pkg\nVersion: 0.0.1\n",
        )
        archive.writestr(
            "demo_pkg-0.0.1.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: handmade\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    monkeypatch.setenv("PIP_NO_INDEX", "1")
    monkeypatch.setenv("PIP_FIND_LINKS", str(wheels))

    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    (module_dir / "helper_mod.py").write_text("VALUE = 7\n", encoding="utf-8")
    venv = package.install_module_venv(module_dir, [_DEP], timeout_s=180)
    assert venv is not None and (venv / ".ready").is_file()
    probe = subprocess.run(
        [
            str(package.venv_python_path(venv)),
            "-c",
            "import demo_pkg, helper_mod; print(demo_pkg.__version__, helper_mod.VALUE)",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert probe.returncode == 0, probe.stderr
    assert "0.0.1 7" in probe.stdout


# ---------------------------------------------------------------- manager 集成
def test_install_without_dependencies_skips_venv(manager, tmp_path: Path) -> None:
    summary = manager.install(build_demo_package(tmp_path))
    assert summary["dependencies"] == []
    assert not (manager.modules_root / DEMO_ID / "1.0.0" / "venv").exists()
    event = manager.audit_events(module_id=DEMO_ID, action="module.install")[0]
    assert "dependencyHash" not in (event["detail"] or {})


def test_install_with_dependencies_creates_venv_and_audits_hash(
    manager, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(package, "install_module_venv", _fake_install)
    summary = manager.install(
        build_demo_package(tmp_path, manifest_updates={"dependencies": [_DEP]})
    )
    module_dir = manager.modules_root / DEMO_ID / "1.0.0"
    assert (module_dir / "venv" / ".ready").is_file()
    assert summary["dependencies"] == [_DEP]
    event = manager.audit_events(module_id=DEMO_ID, action="module.install")[0]
    assert event["detail"]["dependencies"] == [_DEP]
    assert event["detail"]["dependencyHash"] == package.dependency_digest([_DEP])


def test_host_uses_venv_interpreter_when_ready(manager, tmp_path: Path, monkeypatch) -> None:
    _FakeHost.created.clear()
    monkeypatch.setattr(package, "install_module_venv", _fake_install)
    monkeypatch.setattr(manager_module, "ModuleHost", _FakeHost)
    manager.install(
        build_demo_package(tmp_path, manifest_updates={"dependencies": [_DEP]}), enable=True
    )
    manager.start(DEMO_ID)
    assert _FakeHost.created[-1].kwargs["venv_path"] == (
        manager.modules_root / DEMO_ID / "1.0.0" / "venv"
    )


def test_host_uses_core_python_without_dependencies(manager, tmp_path: Path, monkeypatch) -> None:
    _FakeHost.created.clear()
    monkeypatch.setattr(manager_module, "ModuleHost", _FakeHost)
    manager.install(build_demo_package(tmp_path), enable=True)
    manager.start(DEMO_ID)
    assert _FakeHost.created[-1].kwargs["venv_path"] is None


def test_start_rejects_declared_dependencies_without_ready_venv(
    manager, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(package, "install_module_venv", lambda *_a, **_k: None)
    manager.install(
        build_demo_package(tmp_path, manifest_updates={"dependencies": [_DEP]}), enable=True
    )
    with pytest.raises(ModuleError) as info:
        manager.start(DEMO_ID)
    assert info.value.code == "MODULE_CRASH"
    assert "依赖环境未就绪" in info.value.message


def test_pip_failure_keeps_previous_version_runnable(
    manager, tmp_path: Path, monkeypatch
) -> None:
    manager.install(build_demo_package(tmp_path, version="1.0.0"), enable=True)
    monkeypatch.setattr(package, "_run_command", _failing_run("ERROR: No matching distribution"))
    bad = build_demo_package(
        tmp_path, version="1.0.1", manifest_updates={"dependencies": ["missing-pkg==9.9"]}
    )
    with pytest.raises(ModuleError) as info:
        manager.install(bad)
    assert info.value.detail["installError"] == "MODULE_INSTALL_FAILED"
    assert manager.get_module(DEMO_ID)["version"] == "1.0.0"
    assert not (manager.modules_root / DEMO_ID / "1.0.1").exists()
    assert (manager.modules_root / DEMO_ID / "1.0.0" / "src" / "main.py").is_file()
    assert manager.call(DEMO_ID, "echo", {"text": "still-ok"})["text"] == "still-ok"


def test_uninstall_removes_venv(manager, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(package, "install_module_venv", _fake_install)
    manager.install(build_demo_package(tmp_path, manifest_updates={"dependencies": [_DEP]}))
    module_root = manager.modules_root / DEMO_ID
    assert (module_root / "1.0.0" / "venv").is_dir()
    manager.uninstall(DEMO_ID, keep_data=False)
    assert not module_root.exists()


def test_rollback_rebuilds_missing_venv(manager, tmp_path: Path, monkeypatch) -> None:
    calls: list[Path] = []

    def recording_install(module_dir: Path, dependencies, **kwargs):
        calls.append(module_dir)
        return _fake_install(module_dir, dependencies, **kwargs)

    monkeypatch.setattr(package, "install_module_venv", recording_install)
    manifest = {"dependencies": [_DEP]}
    manager.install(
        build_demo_package(tmp_path, version="1.0.0", manifest_updates=manifest), enable=True
    )
    manager.install(build_demo_package(tmp_path, version="1.0.1", manifest_updates=manifest))
    old_version_dir = manager.modules_root / DEMO_ID / "1.0.0"
    package.remove_module_venv(old_version_dir)
    calls.clear()

    summary = manager.rollback(DEMO_ID, "1.0.0")
    assert summary["version"] == "1.0.0"
    assert calls == [old_version_dir]
    assert package.read_ready_venv(old_version_dir, [_DEP]) is not None
