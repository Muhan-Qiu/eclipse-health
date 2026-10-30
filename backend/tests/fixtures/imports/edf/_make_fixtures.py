"""生成 B4-02 的 EDF 测试夹具（一次性脚本，不是生产解析器）。

来源：MIT-BIH Arrhythmia Database（PhysioNet，ODC-By 1.0，见
https://physionet.org/content/mitdb/1.0.0/），仓库内已有 100/200/208 号记录。
这里取 100 号记录的前 10 秒，写成标准 EDF（16-bit，单位 mV）。

用法（项目根目录）：
    backend\\.venv\\Scripts\\python.exe backend\\tests\\fixtures\\imports\\edf\\_make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parents[5]
SAMPLE_DIR = ROOT / "backend" / "resources" / "samples"
OUT_DIR = ROOT / "uploads" / "samples" / "edf"

FS = 360
SECONDS = 10


def _field(value: str, length: int) -> bytes:
    encoded = value.encode("ascii", "replace")[:length]
    return encoded.ljust(length, b" ")


def write_edf(path: Path, signals_mv: np.ndarray, labels: list[str], fs: int) -> None:
    """signals_mv: shape (n_samples, n_signals)，物理单位 mV。"""
    _n_samples, n_signals = signals_mv.shape
    header_bytes = 256 + 256 * n_signals
    phys_min, phys_max = -5.0, 5.0
    dig_min, dig_max = -32768, 32767

    header = b"".join(
        [
            _field("0", 8),
            _field("X X X X", 80),
            _field("MIT-BIH derived sample (B4-02)", 80),
            _field("01.01.80", 8),
            _field("00.00.00", 8),
            _field(str(header_bytes), 8),
            _field("", 44),  # 不写 EDF+C：没有 EDF Annotations 通道，按普通 EDF 输出
            _field(str(SECONDS), 8),  # n_records = 1 秒一条
            _field("1", 8),  # 每条记录 1 秒
            _field(str(n_signals), 4),
        ]
    )
    # EDF 头部按字段分列存放（不是按通道分块）。
    per_signal = b"".join(
        [
            b"".join(_field(label, 16) for label in labels),
            b"".join(_field("", 80) for _ in labels),
            b"".join(_field("mV", 8) for _ in labels),
            b"".join(_field(f"{phys_min}", 8) for _ in labels),
            b"".join(_field(f"{phys_max}", 8) for _ in labels),
            b"".join(_field(f"{dig_min}", 8) for _ in labels),
            b"".join(_field(f"{dig_max}", 8) for _ in labels),
            b"".join(_field("HP:0.1Hz LP:100Hz", 80) for _ in labels),
            b"".join(_field(str(fs), 8) for _ in labels),
            b"".join(_field("", 32) for _ in labels),
        ]
    )
    payload = bytearray()
    for second in range(SECONDS):
        chunk = signals_mv[second * fs : (second + 1) * fs]
        digital = np.round((chunk - phys_min) / (phys_max - phys_min) * (dig_max - dig_min) + dig_min)
        digital = np.clip(digital, dig_min, dig_max).astype("<i2")
        payload += digital.tobytes(order="F")  # 每条记录内按通道交错

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + per_signal + bytes(payload))


def main() -> None:
    record = wfdb.rdrecord(str(SAMPLE_DIR / "100"), physical=True)
    signals = np.asarray(record.p_signal[: FS * SECONDS], dtype=np.float64)
    labels = [str(name).strip() for name in record.sig_name]

    write_edf(OUT_DIR / "mitdb100-2lead-10s.edf", signals, labels, FS)
    write_edf(OUT_DIR / "mitdb100-1lead-10s.edf", signals[:, :1], labels[:1], FS)
    print("wrote", OUT_DIR)
    for label, sig in zip(labels, signals.T):
        print(f"  {label}: {sig.min():.3f}..{sig.max():.3f} mV")


if __name__ == "__main__":
    main()
