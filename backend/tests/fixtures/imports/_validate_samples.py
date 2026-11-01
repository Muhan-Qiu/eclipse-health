"""B4-02 样本最小校验（标准库 + numpy），不是生产解析器。

只做四件事：读文件头/关键字段、读时间列/采样率、核对 index.json 的 sha256 与大小、
尝试用现有工具打开。输出供 reports/B4-02-report.md 引用。

用法（项目根目录）：
    backend\\.venv\\Scripts\\python.exe backend\\tests\\fixtures\\imports\\_validate_samples.py
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
UPLOADS = ROOT / "uploads"
INDEX = UPLOADS / "samples" / "index.json"


def read_edf(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) < 256:
        raise ValueError("文件短于 256 字节，不是 EDF")
    ns = int(raw[252:256].decode().strip())
    n_records = int(raw[236:244].decode().strip())
    record_seconds = float(raw[244:252].decode().strip())
    base = 256 + ns * (16 + 80 + 8 * 5 + 80)
    labels = [raw[256 + i * 16 : 256 + (i + 1) * 16].decode().strip() for i in range(ns)]
    units = [raw[256 + ns * 96 + i * 8 : 256 + ns * 96 + (i + 1) * 8].decode().strip() for i in range(ns)]
    spr = [int(raw[base + i * 8 : base + (i + 1) * 8].decode().strip()) for i in range(ns)]
    return {
        "version": raw[0:8].decode().strip(),
        "start": raw[168:176].decode() + " " + raw[176:184].decode(),
        "header_bytes": int(raw[184:192].decode().strip()),
        "edf_plus": raw[192:236].decode().strip(),
        "n_records": n_records,
        "record_seconds": record_seconds,
        "labels": labels,
        "units": units,
        "fs": [s / record_seconds if record_seconds else None for s in spr],
        "duration_s": n_records * record_seconds,
    }


def read_scp(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) < 22:
        raise ValueError("文件短于 22 字节，不是 SCP-ECG")
    if raw[16:22] != b"SCPECG":
        return {"standard": False, "reason": "缺少 'SCPECG' 标记：Healforce 等非标准变体，标准解析器不适用"}
    info: dict = {"standard": True}
    length = struct.unpack_from("<I", raw, 2)[0]
    info["length_field"] = length
    sec0_len = struct.unpack_from("<I", raw, 10)[0]
    ptrs, pos = {}, 22
    while pos + 10 <= 6 + sec0_len:
        sid, plen, idx = struct.unpack_from("<HII", raw, pos)
        if idx >= 1:
            ptrs[sid] = (idx - 1, plen)
        pos += 10
    info["sections"] = {k: v[1] for k, v in sorted(ptrs.items())}
    if 1 in ptrs:
        off, ln = ptrs[1]
        p, end, tags = off + 16, off + ln, {}
        while p < end:
            tag = raw[p]
            p += 1
            if tag == 255:
                break
            size = struct.unpack_from("<H", raw, p)[0]
            p += 2
            if size == 0:
                continue
            tags[tag] = raw[p : p + size]
            p += size
        if 25 in tags:
            year, month, day = struct.unpack_from("<HBB", tags[25])
            info["acquisition_date"] = f"{year:04d}-{month:02d}-{day:02d}"
        if 26 in tags:
            info["acquisition_time"] = ":".join(f"{b:02d}" for b in tags[26])
        if 14 in tags:
            info["device_model"] = tags[14][8:14].decode("latin-1").strip("\0 ")
    if 3 in ptrs:
        off, _ = ptrs[3]
        p = off + 16
        count, flag = raw[p], raw[p + 1]
        p += 2
        leads = []
        for _ in range(count):
            start, end = struct.unpack_from("<II", raw, p)
            leads.append({"id": raw[p + 8], "samples": end - start + 1})
            p += 9
        info["leads"] = leads
        info["simultaneous"] = bool(flag & 4)
    if 6 in ptrs:
        off, _ = ptrs[6]
        amp, interval, encoding, compression = struct.unpack_from("<HHBB", raw, off + 16)
        info.update(
            amp_nv_per_lsb=amp,
            interval_us=interval,
            fs=1e6 / interval if interval else None,
            encoding=encoding,
            compression=compression,
        )
    return info


def read_apple_csv(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        rows = list(reader)
    if not header or len(header) < 2:
        raise ValueError("CSV 缺少 time/voltage 两列表头")
    times = [float(r[header[0]]) for r in rows]
    volts = [float(r[header[1]]) for r in rows]
    steps = {round(b - a, 9) for a, b in itertools.pairwise(times)}
    return {
        "header": header,
        "rows": len(rows),
        "duration_s": times[-1] - times[0],
        "step_s": sorted(steps)[:3],
        "fs": round(1 / (times[1] - times[0]), 3),
        "min": min(volts),
        "max": max(volts),
    }


def negative_checks() -> None:
    """边界/非法输入：截断文件、空 CSV。只写系统临时目录，不碰仓库。"""
    import tempfile

    valid_edf = (UPLOADS / "samples" / "edf" / "mitdb100-1lead-10s.edf").read_bytes()
    valid_scp = (UPLOADS / "samples" / "scp-ecg" / "example.scp").read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "truncated.edf").write_bytes(valid_edf[:100])
        (tmp / "truncated.scp").write_bytes(valid_scp[:20])
        (tmp / "empty.csv").write_text("", encoding="utf-8")
        for name, fn in (
            ("truncated.edf", read_edf),
            ("truncated.scp", read_scp),
            ("empty.csv", read_apple_csv),
        ):
            try:
                fn(tmp / name)
            except (struct.error, ValueError, IndexError, StopIteration) as exc:
                print(f"  {name}: rejected as expected ({type(exc).__name__})")
            else:
                print(f"  {name}: unexpectedly accepted (需检查)")


def main() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    print(f"index: {len(index['samples'])} samples, {len(index['missing'])} missing")
    for entry in index["samples"]:
        path = UPLOADS / entry["path"]
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        status = "OK" if sha == entry["sha256"] and len(raw) == entry["bytes"] else "MISMATCH"
        print(f"[{status}] {entry['id']} {len(raw)}B sha256={sha[:12]} license={entry['license'].split(' ')[0]}")

    print("\nEDF headers:")
    for path in sorted((UPLOADS / "samples" / "edf").glob("*.edf")):
        print(f"  {path.name}: {read_edf(path)}")

    print("\nSCP-ECG headers:")
    for path in sorted((UPLOADS / "samples" / "scp-ecg").glob("*")):
        if path.suffix.lower() == ".scp":
            print(f"  {path.name}: {read_scp(path)}")

    print("\nApple synthetic CSV:")
    print(f"  {read_apple_csv(ROOT / 'backend/tests/fixtures/imports/apple/electrocardiograms.csv')}")

    try:
        import wfdb

        try:
            wfdb.rdheader(str(UPLOADS / "samples" / "edf" / "mitdb100-1lead-10s.edf"))
            print("\nwfdb can read EDF: yes")
        except Exception as exc:  # noqa: BLE001 - 这里就是要记录第三方工具的真实报错
            print(f"\nwfdb can read EDF: no ({type(exc).__name__}: {exc})")
    except ImportError:
        print("\nwfdb not installed")

    print("\nBoundary / invalid input:")
    negative_checks()


if __name__ == "__main__":
    main()
