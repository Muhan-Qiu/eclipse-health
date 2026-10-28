from __future__ import annotations

import numpy as np
import pytest

from eclipse_health_backend.domain.errors import InvalidInputError, StorageIntegrityError
from eclipse_health_backend.domain.ids import new_id
from eclipse_health_backend.settings import get_settings
from eclipse_health_backend.storage.files import (
    atomic_write_bytes,
    decode_float32,
    delete_signal,
    read_import_file,
    read_report,
    read_signal,
    sha256_hex,
    write_report,
    write_signal,
)


def test_sha256_hex_matches_hashlib() -> None:
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_atomic_write_replaces_content(tmp_path) -> None:
    target = tmp_path / "wave.bin"
    atomic_write_bytes(target, b"first")
    atomic_write_bytes(target, b"second")
    assert target.read_bytes() == b"second"
    assert not list(tmp_path.glob("*.tmp"))


def test_signal_roundtrip_is_bit_exact(tmp_path) -> None:
    signal_id = new_id("signal")
    samples = np.linspace(-0.5, 0.5, 1000, dtype="<f4")
    relative, digest, size = write_signal(signal_id, samples)

    assert relative == f"signals/{signal_id}.f32"
    assert size == samples.nbytes
    assert len(digest) == 64

    raw = read_signal(relative, digest)
    restored = decode_float32(raw)
    assert np.array_equal(restored, samples)

    delete_signal(relative)
    assert not (get_settings().signals_dir / f"{signal_id}.f32").exists()


def test_read_signal_detects_tampering() -> None:
    signal_id = new_id("signal")
    relative, digest, _ = write_signal(signal_id, np.zeros(16, dtype="<f4"))
    path = get_settings().signals_dir / f"{signal_id}.f32"
    path.write_bytes(b"\x01" * 64)

    with pytest.raises(StorageIntegrityError):
        read_signal(relative, digest)


def test_read_signal_rejects_traversal() -> None:
    with pytest.raises(StorageIntegrityError):
        read_signal("../signals/x.f32", "0" * 64)
    with pytest.raises(StorageIntegrityError):
        read_signal("signals/../../x.f32", "0" * 64)
    with pytest.raises(StorageIntegrityError):
        read_signal("signals\\x.f32", "0" * 64)


def test_read_signal_missing_file() -> None:
    with pytest.raises(StorageIntegrityError):
        read_signal(f"signals/{new_id('signal')}.f32", "0" * 64)


def test_import_file_accepts_relative_path() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    path = settings.imports_dir / "sample.f32"
    samples = np.array([0.25, -0.25], dtype="<f4")
    path.write_bytes(samples.tobytes())

    raw = read_import_file("sample.f32")
    assert np.array_equal(decode_float32(raw), samples)


@pytest.mark.parametrize(
    "file_ref",
    ["../escape.f32", "sub/../../escape.f32", "C:/Windows/win.ini", "C:\\Windows\\win.ini", ""],
)
def test_import_file_rejects_unsafe_paths(file_ref: str) -> None:
    with pytest.raises(InvalidInputError):
        read_import_file(file_ref)


def test_import_file_missing() -> None:
    with pytest.raises(InvalidInputError):
        read_import_file(f"missing-{new_id('signal')}.f32")


def test_report_roundtrip() -> None:
    report_id = new_id("report")
    relative, digest, size = write_report(report_id, "pdf", b"%PDF-1.4 demo")
    assert relative == f"reports/{report_id}.pdf"
    assert size == len(b"%PDF-1.4 demo")
    assert read_report(relative, digest) == b"%PDF-1.4 demo"


def test_report_rejects_unknown_format() -> None:
    with pytest.raises(InvalidInputError):
        write_report(new_id("report"), "exe", b"MZ")
