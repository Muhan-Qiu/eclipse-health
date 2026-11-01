"""生成 Apple Health 心电图 CSV 的**合成**测试夹具（不是生产解析器）。

说明：截至 2026-10，没有找到可再分发的 Apple Health `electrocardiograms/*.csv`
公开样例；此文件按 HealthKit 文档（`HKElectrocardiogram`：采样频率字段、电压单位
为 volt）与社区常见的 `time,voltage` 两列布局合成，仅用于 B4-03 适配器测试。
真实导出仍需用户提供，详见 docs/FORMATS/apple.md。

波形取自 MIT-BIH 100 号记录 MLII 导联前 10 秒（PhysioNet，ODC-By 1.0），
线性重采样到 512 Hz，电压写成伏特。

用法（项目根目录）：
    backend\\.venv\\Scripts\\python.exe backend\\tests\\fixtures\\imports\\apple\\_make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parents[5]
SAMPLE_DIR = ROOT / "backend" / "resources" / "samples"
OUT = Path(__file__).resolve().parent / "electrocardiograms.csv"

SOURCE_FS = 360
TARGET_FS = 512
SECONDS = 10


def main() -> None:
    record = wfdb.rdrecord(str(SAMPLE_DIR / "100"), physical=True, sampto=SOURCE_FS * SECONDS)
    source = np.asarray(record.p_signal[:, 0], dtype=np.float64)  # MLII，单位 mV
    n_target = TARGET_FS * SECONDS
    source_t = np.arange(source.size) / SOURCE_FS
    target_t = np.arange(n_target) / TARGET_FS
    volts = np.interp(target_t, source_t, source) / 1000.0

    lines = ["time,voltage"]
    lines.extend(f"{t:.6f},{v:.9f}" for t, v in zip(target_t, volts))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({n_target} samples, {volts.min():.4f}..{volts.max():.4f} V)")


if __name__ == "__main__":
    main()
