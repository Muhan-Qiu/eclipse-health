"""输入适配：WFDB / CSV / NPY / ndarray -> EcgSignal。

统一约定：
- ``samples`` 为 mV、目标采样率 360 Hz（非 360 时用多项式重采样）；
- ``digital`` 保留 ADC 数字量，Cardia 的 104 维特征吃数字量；
- 原始采样率、是否重采样、导联、标注都记录在 EcgSignal 里。
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import resample_poly

from .types import (
    DEFAULT_FEATURE_GAIN,
    TARGET_FS,
    EcgSignal,
    InvalidSignalError,
)

UNIT_TO_MV = {
    "mv": 1.0,
    "millivolt": 1.0,
    "uv": 0.001,
    "µv": 0.001,
    "μv": 0.001,
    "microvolt": 0.001,
    "v": 1000.0,
    "volt": 1000.0,
}
ADC_UNITS = {"adc", "count", "counts", "digital", "lsb"}

LEAD_ALIASES = {
    "mlii": "MLII",
    "ml ii": "MLII",
    "i": "I",
    "ii": "II",
    "iii": "III",
    "avr": "aVR",
    "avl": "aVL",
    "avf": "aVF",
    "v1": "V1",
    "v2": "V2",
    "v3": "V3",
    "v4": "V4",
    "v5": "V5",
    "v6": "V6",
}
_NON_SIGNAL_COLUMNS = {"time", "t", "index", "idx", "sample", "timestamp", "序号"}


def _warning(code: str, message: str, severity: str = "info") -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "startSec": None,
        "endSec": None,
    }


def _normalize_lead(name: str) -> str:
    key = str(name).strip().lower()
    return LEAD_ALIASES.get(key, str(name).strip())


def _resample_to(x: np.ndarray, fs_in: float, fs_out: float) -> np.ndarray:
    """按有理数比例重采样，长度由输出采样率决定。"""
    if abs(fs_in - fs_out) < 1e-9:
        return np.asarray(x, dtype=np.float64)
    ratio = Fraction(float(fs_out) / float(fs_in)).limit_denominator(10_000)
    up, down = ratio.numerator, ratio.denominator
    if up <= 0 or down <= 0:
        raise InvalidSignalError(f"无法重采样：{fs_in} -> {fs_out}")
    return resample_poly(np.asarray(x, dtype=np.float64), up, down)


def resample_signal(sig: EcgSignal, target_fs: float = TARGET_FS) -> EcgSignal:
    """重采样到目标采样率；物理波形与数字量一起重采样，标注同步缩放。"""
    if abs(sig.fs - target_fs) < 1e-6:
        return sig
    original_fs = sig.original_fs or sig.fs
    samples = _resample_to(sig.samples, sig.fs, target_fs)
    digital = (
        _resample_to(sig.digital, sig.fs, target_fs)
        if sig.digital is not None
        else None
    )
    annotations = None
    if sig.annotations:
        scale = target_fs / sig.fs
        scaled = sorted(
            (round(pos * scale), sym) for pos, sym in sig.annotations
        )
        # 缩放后可能出现重复位置；保留第一个符号，避免同一采样点重复计搏。
        deduped: list[tuple[int, str]] = []
        for pos, sym in scaled:
            if deduped and deduped[-1][0] == pos:
                continue
            deduped.append((pos, sym))
        annotations = deduped

    warnings = list(sig.warnings)
    warnings.append(
        _warning(
            "resampled",
            f"采样率 {sig.fs:g} Hz 已重采样到 {target_fs:g} Hz",
        )
    )
    return EcgSignal(
        samples=samples,
        fs=target_fs,
        lead=sig.lead,
        source=sig.source,
        original_fs=original_fs,
        resampled=True,
        digital=digital,
        gain=sig.gain,
        annotations=annotations,
        record_name=sig.record_name,
        warnings=warnings,
    )


def _choose_lead(names: Sequence[str], requested: str | None) -> tuple[int, list[dict]]:
    warnings: list[dict] = []
    upper = [str(n).upper() for n in names]
    if requested:
        wanted = _normalize_lead(requested).upper()
        for idx, name in enumerate(upper):
            if name == wanted:
                return idx, warnings
        warnings.append(
            _warning(
                "lead_not_found",
                f"未找到导联 {requested}，回退到 MLII/第一导联",
                severity="warning",
            )
        )
    if "MLII" in upper:
        return upper.index("MLII"), warnings
    return 0, warnings


def load_wfdb(
    prefix: str | Path,
    *,
    lead: str | None = None,
    ann_ext: str = "atr",
    target_fs: float = TARGET_FS,
) -> EcgSignal:
    """读取 WFDB 记录；优先 MLII，否则第一导联。

    只读一次数字量（``physical=False``），再按 WFDB 的标准公式
    ``(d - baseline) / gain`` 转 mV，保证与 V2 特征管线使用同一份数字量。
    """
    import wfdb

    prefix = Path(prefix)
    try:
        record = wfdb.rdrecord(str(prefix), physical=False)
    except Exception as exc:  # wfdb 的异常类型很杂，统一转成业务异常
        raise InvalidSignalError(f"无法读取 WFDB 记录 {prefix}：{exc}") from exc

    if not record.sig_name or record.d_signal is None:
        raise InvalidSignalError("WFDB 记录没有波形或导联信息")
    ch, warnings = _choose_lead(record.sig_name, lead)
    if ch >= record.d_signal.shape[1]:
        raise InvalidSignalError(f"导联索引越界：{ch}")

    digital = np.asarray(record.d_signal[:, ch], dtype=np.float64)
    gain = float(record.adc_gain[ch]) if record.adc_gain is not None else 1.0
    if gain == 0:
        gain = 1.0
    baseline = (
        float(record.baseline[ch]) if record.baseline is not None else 0.0
    )
    unit = str(record.units[ch]) if record.units else "mV"
    samples = (digital - baseline) / gain * _unit_to_mv_scale(unit)

    annotations = None
    try:
        ann = wfdb.rdann(str(prefix), ann_ext)
    except Exception:  # noqa: BLE001 - 标注文件可能缺失或格式不一
        ann = None
    if ann is not None and len(ann.sample):
        annotations = [
            (int(pos), str(sym)) for pos, sym in zip(ann.sample, ann.symbol)
        ]

    sig = EcgSignal(
        samples=samples,
        fs=float(record.fs),
        lead=str(record.sig_name[ch]),
        source="wfdb",
        digital=digital,
        gain=gain,
        annotations=annotations,
        record_name=prefix.name,
        warnings=warnings,
    )
    return resample_signal(sig, target_fs)


def _unit_to_mv_scale(unit: str) -> float:
    key = str(unit).strip().lower()
    if key in {"mv", "millivolt"}:
        return 1.0
    if key in {"uv", "µv", "μv", "microvolt"}:
        return 0.001
    if key in {"v", "volt"}:
        return 1000.0
    return 1.0


def _read_numeric_table(path: str | Path) -> tuple[np.ndarray, list[str] | None]:
    """跳过厂商元数据头，读取第一个数值行开始的表格。"""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise InvalidSignalError(f"无法读取文件 {path}：{exc}") from exc
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        first = stripped.split(",")[0].strip()
        try:
            float(first)
        except ValueError:
            continue
        start = i
        break
    if start is None:
        raise InvalidSignalError("文件里找不到数值数据行")

    header: list[str] | None = None
    if start > 0 and lines[start - 1].strip():
        candidate = [p.strip() for p in lines[start - 1].split(",")]
        try:
            float(candidate[0])
        except ValueError:
            header = candidate

    rows: list[list[float]] = []
    for line in lines[start:]:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        try:
            rows.append([float(p) for p in parts])
        except ValueError:
            continue
    if not rows:
        raise InvalidSignalError("文件里没有可解析的数值行")

    array = np.asarray(rows, dtype=np.float64)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    return array, header


def _pick_column(
    array: np.ndarray, header: list[str] | None, column: int | None
) -> int:
    n_cols = int(array.shape[1])
    if column is not None:
        if column < 0 or column >= n_cols:
            raise InvalidSignalError(f"列索引 {column} 超出范围（共 {n_cols} 列）")
        return int(column)

    if header and len(header) >= n_cols:
        normalized = [h.strip().lower() for h in header[:n_cols]]
        for idx, name in enumerate(normalized):
            if name in _NON_SIGNAL_COLUMNS:
                continue
            if name in LEAD_ALIASES or name in {"ecg", "ekg", "signal", "心电"}:
                return idx

    if n_cols > 1:
        first = array[:, 0]
        if len(first) > 2 and np.all(np.diff(first) > 0):
            return 1  # 第一列是时间轴
    return 0


def _values_to_mv(
    values: np.ndarray, unit: str, gain: float
) -> tuple[np.ndarray, np.ndarray | None, list[dict]]:
    """返回 (mV, digital, warnings)。"""
    key = str(unit or "mV").strip().lower()
    warnings: list[dict] = []
    if key in ADC_UNITS:
        digital = np.asarray(values, dtype=np.float64)
        mv = (digital - float(np.median(digital))) / gain
        warnings.append(
            _warning(
                "adc_input",
                f"输入为 ADC 数字量，按 gain={gain:g} 换算为 mV 供展示；"
                "特征仍使用原始数字量",
            )
        )
        return mv, digital, warnings
    if key not in UNIT_TO_MV:
        raise InvalidSignalError(f"不支持的单位：{unit!r}（可用 mV/uV/V/ADC）")
    mv = np.asarray(values, dtype=np.float64) * UNIT_TO_MV[key]
    digital = mv * gain
    warnings.append(
        _warning(
            "unverified_amplitude",
            f"非 WFDB 输入按 gain={gain:g} ADC/mV 映射到 Cardia 特征尺度；"
            "绝对电压仅作参考",
        )
    )
    return mv, digital, warnings


def load_array(
    samples: np.ndarray | Sequence[float],
    *,
    fs: float,
    lead: str = "I",
    unit: str = "mV",
    gain: float = DEFAULT_FEATURE_GAIN,
    source: str = "array",
    target_fs: float = TARGET_FS,
) -> EcgSignal:
    values = np.asarray(samples, dtype=np.float64).ravel()
    if values.size == 0:
        raise InvalidSignalError("输入数组为空")
    if not np.isfinite(values).all():
        raise InvalidSignalError("输入数组含 NaN/Inf")
    mv, digital, warnings = _values_to_mv(values, unit, float(gain))
    sig = EcgSignal(
        samples=mv,
        fs=float(fs),
        lead=_normalize_lead(lead),
        source=source,
        digital=digital,
        gain=float(gain),
        warnings=warnings,
    )
    return resample_signal(sig, target_fs)


def load_csv(
    path: str | Path,
    *,
    fs: float,
    lead: str = "I",
    unit: str = "mV",
    column: int | None = None,
    gain: float = DEFAULT_FEATURE_GAIN,
    target_fs: float = TARGET_FS,
) -> EcgSignal:
    array, header = _read_numeric_table(path)
    col = _pick_column(array, header, column)
    sig = load_array(
        array[:, col],
        fs=fs,
        lead=lead,
        unit=unit,
        gain=gain,
        source="csv",
        target_fs=target_fs,
    )
    sig.record_name = Path(path).stem
    return sig


def load_npy(
    path: str | Path,
    *,
    fs: float,
    lead: str = "I",
    unit: str = "mV",
    column: int | None = None,
    gain: float = DEFAULT_FEATURE_GAIN,
    target_fs: float = TARGET_FS,
) -> EcgSignal:
    path = Path(path)
    try:
        array = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise InvalidSignalError(f"无法读取 NPY {path}：{exc}") from exc
    array = np.asarray(array, dtype=np.float64)
    if array.ndim == 2:
        col = _pick_column(array, None, column)
        array = array[:, col]
    elif array.ndim != 1:
        raise InvalidSignalError(f"NPY 必须是一维或二维数组，实际 {array.ndim} 维")
    sig = load_array(
        array,
        fs=fs,
        lead=lead,
        unit=unit,
        gain=gain,
        source="npy",
        target_fs=target_fs,
    )
    sig.record_name = path.stem
    return sig


def ingest(path: str | Path, *, fmt: str, **kwargs: Any) -> EcgSignal:
    """CLI/调用方用的分发器。"""
    fmt = fmt.lower()
    if fmt == "wfdb":
        return load_wfdb(path, **kwargs)
    if fmt == "csv":
        return load_csv(path, **kwargs)
    if fmt == "npy":
        return load_npy(path, **kwargs)
    raise InvalidSignalError(f"未知输入格式：{fmt!r}")
