"""`.ehmod` 安全性、checksums 与安装失败清理测试。"""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest
from module_test_helpers import build_demo_package, build_zip

from eclipse_health_backend.modules import package
from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manifest import load_manifest_file

DEMO_ID = "org.eclipsehealth.demo.echo"


def _demo_files() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3] / "modules" / "demo.echo"
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and path.name != "checksums.json"
    }


def test_path_traversal_is_rejected_before_writing(tmp_path: Path) -> None:
    entries = _demo_files()
    entries["../evil.txt"] = "pwned"
    archive = build_zip(tmp_path, entries, "traversal.ehmod")
    staging = tmp_path / "staging"
    with zipfile.ZipFile(archive) as zf, pytest.raises(ModuleError) as info:
        package.extract_package(zf, staging)
    assert info.value.code == "UNSAFE_PACKAGE_PATH"
    assert not (tmp_path / "evil.txt").exists()
    assert not staging.exists()


@pytest.mark.parametrize("bad_name", ["/absolute.txt", "C:\\win\\abs.txt", "src/../../escape.txt"])
def test_absolute_and_nested_traversal_paths_rejected(tmp_path: Path, bad_name: str) -> None:
    entries = _demo_files()
    entries[bad_name] = "x"
    archive = build_zip(tmp_path, entries, "absolute.ehmod")
    with zipfile.ZipFile(archive) as zf, pytest.raises(ModuleError) as info:
        package.extract_package(zf, tmp_path / "staging")
    assert info.value.code == "UNSAFE_PACKAGE_PATH"


def test_symlink_entry_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.ehmod"
    with zipfile.ZipFile(archive, "w") as zf:
        for name, content in _demo_files().items():
            zf.writestr(name, content)
        info = zipfile.ZipInfo("src/link.py")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with zipfile.ZipFile(archive) as zf, pytest.raises(ModuleError) as error:
        package.extract_package(zf, tmp_path / "staging")
    assert error.value.code == "UNSAFE_PACKAGE_PATH"


def test_case_insensitive_duplicate_paths_rejected(tmp_path: Path) -> None:
    entries = _demo_files()
    entries["SRC/Main.py"] = "duplicate"
    archive = build_zip(tmp_path, entries, "duplicate.ehmod")
    with zipfile.ZipFile(archive) as zf, pytest.raises(ModuleError) as info:
        package.extract_package(zf, tmp_path / "staging")
    assert info.value.code == "INVALID_PACKAGE"


@pytest.mark.parametrize("bad_name", ["src/CON.py", "src/evil:stream.py", "src/trailing. "])
def test_windows_unsafe_names_rejected(tmp_path: Path, bad_name: str) -> None:
    entries = _demo_files()
    entries[bad_name] = "x"
    archive = build_zip(tmp_path, entries, "windows-names.ehmod")
    with zipfile.ZipFile(archive) as zf, pytest.raises(ModuleError) as info:
        package.extract_package(zf, tmp_path / "staging")
    assert info.value.code == "UNSAFE_PACKAGE_PATH"


def test_checksums_missing_is_warning_only(manager, demo_package: Path, tmp_path: Path) -> None:
    no_checksums = build_demo_package(tmp_path, checksums=False)
    summary = manager.install(no_checksums)
    assert summary["id"] == DEMO_ID
    assert any("checksums.json" in warning for warning in summary["warnings"])


def test_checksum_mismatch_is_rejected(manager, demo_package: Path, tmp_path: Path) -> None:
    tampered = tmp_path / "tampered.ehmod"
    with zipfile.ZipFile(demo_package) as source, zipfile.ZipFile(tampered, "w") as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "src/main.py":
                data += b"\n# tampered after checksums were written\n"
            target.writestr(entry.filename, data)
    with pytest.raises(ModuleError) as info:
        manager.install(tampered)
    assert info.value.code == "CHECKSUM_MISMATCH"
    assert not any((manager.modules_root / ".staging").iterdir())


def test_missing_module_json_rejected(manager, tmp_path: Path) -> None:
    archive = build_zip(tmp_path, {"src/main.py": "print('hi')\n"})
    with pytest.raises(ModuleError) as info:
        manager.install(archive)
    assert info.value.code == "INVALID_PACKAGE"


def test_missing_src_directory_rejected(manager, tmp_path: Path) -> None:
    manifest = _demo_files()["module.json"]
    archive = build_zip(tmp_path, {"module.json": manifest})
    with pytest.raises(ModuleError) as info:
        manager.install(archive)
    assert info.value.code == "INVALID_PACKAGE"


def test_bad_zip_rejected(manager, tmp_path: Path) -> None:
    path = tmp_path / "broken.ehmod"
    path.write_bytes(b"not a zip at all")
    with pytest.raises(ModuleError) as info:
        manager.install(path)
    assert info.value.code == "INVALID_PACKAGE"


def test_non_ehmod_suffix_rejected(manager, tmp_path: Path) -> None:
    path = tmp_path / "module.zip"
    path.write_bytes(b"anything")
    with pytest.raises(ModuleError) as info:
        manager.install(path)
    assert info.value.code == "INVALID_INPUT"


def test_checksums_cover_all_files(tmp_path: Path) -> None:
    source = tmp_path / "module"
    (source / "src").mkdir(parents=True)
    (source / "module.json").write_text("{}", encoding="utf-8")
    (source / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")
    package.write_checksums(source)
    checksums = package.load_checksums(source)
    assert checksums is not None
    assert set(checksums) == {"module.json", "src/main.py"}
    assert package.verify_checksums(source) == []


def test_layout_checks_entry_exists(tmp_path: Path) -> None:
    source = tmp_path / "module"
    (source / "src").mkdir(parents=True)
    manifest = load_manifest_file(Path(__file__).resolve().parents[3] / "modules" / "demo.echo" / "module.json")
    (source / "module.json").write_text(
        (Path(__file__).resolve().parents[3] / "modules" / "demo.echo" / "module.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ModuleError) as info:
        package.verify_layout(source, manifest)
    assert info.value.code == "INVALID_PACKAGE"
