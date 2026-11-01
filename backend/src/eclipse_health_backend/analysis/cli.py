"""命令行入口。

示例::

    python -m eclipse_health_backend.analysis.cli \\
        --record backend/resources/samples/100 --format wfdb \\
        --out reports/analysis-100.json

    python -m eclipse_health_backend.analysis.cli \\
        --csv watch.csv --fs 500 --lead I --out reports/analysis-watch.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import analyze
from .ids import new_id
from .ingest import load_csv, load_npy, load_wfdb
from .types import AnalysisError, AnalysisOptions, ModelLoadError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eclipse_health_backend.analysis.cli",
        description="Cardia 2.0 单导联心电分析（B1 纯库）",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--record", help="WFDB 记录前缀（不带扩展名）")
    source.add_argument("--csv", help="CSV 文件路径")
    source.add_argument("--npy", help="NPY 文件路径")

    parser.add_argument(
        "--format",
        choices=["wfdb", "csv", "npy"],
        default=None,
        help="输入格式；缺省时按 --record/--csv/--npy 推断",
    )
    parser.add_argument("--fs", type=float, default=None, help="CSV/NPY 采样率")
    parser.add_argument("--lead", default=None, help="导联名；WFDB 缺省优先 MLII")
    parser.add_argument(
        "--unit",
        default="mV",
        choices=["mV", "uV", "V", "ADC"],
        help="CSV/NPY 数值单位",
    )
    parser.add_argument("--column", type=int, default=None, help="CSV/NPY 列索引")
    parser.add_argument(
        "--gain",
        type=float,
        default=200.0,
        help="ADC/mV 换算增益（非 WFDB 输入）",
    )
    parser.add_argument("--ann-ext", default="atr", help="WFDB 标注扩展名")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--record-id", default=None, help="调用方记录 ID")
    parser.add_argument("--allow-short", action="store_true", help="允许 <64 搏")
    parser.add_argument(
        "--tail-mode",
        choices=["pad", "drop"],
        default="pad",
        help="末尾不足一窗时补窗（pad）或丢弃（drop，V2 行为）",
    )
    parser.add_argument("--model-dir", default=None, help="模型目录")
    return parser


def _infer_format(args: argparse.Namespace) -> str:
    if args.format:
        return args.format
    if args.record:
        return "wfdb"
    if args.csv:
        return "csv"
    return "npy"


def _load_signal(args: argparse.Namespace):
    fmt = _infer_format(args)
    path = args.record or args.csv or args.npy
    if fmt == "wfdb":
        return load_wfdb(path, lead=args.lead, ann_ext=args.ann_ext)
    if fmt == "csv":
        if args.fs is None:
            raise AnalysisError("--csv 需要同时提供 --fs")
        return load_csv(
            path,
            fs=args.fs,
            lead=args.lead or "I",
            unit=args.unit,
            column=args.column,
            gain=args.gain,
        )
    if args.fs is None:
        raise AnalysisError("--npy 需要同时提供 --fs")
    return load_npy(
        path,
        fs=args.fs,
        lead=args.lead or "I",
        unit=args.unit,
        column=args.column,
        gain=args.gain,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        signal = _load_signal(args)
        options = AnalysisOptions(
            record_id=args.record_id or new_id("rec"),
            model_dir=args.model_dir,
            allow_short_record=args.allow_short,
            tail_mode=args.tail_mode,
        )
        result = analyze(signal, options)
    except ModelLoadError as exc:
        print(f"模型错误：{exc}", file=sys.stderr)
        return 3
    except AnalysisError as exc:
        print(f"分析失败：{exc}", file=sys.stderr)
        return 2

    name = signal.record_name or "record"
    out_path = Path(args.out or Path("reports") / f"analysis-{name}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    params = result["parameters"]
    print(f"recordId: {result['recordId']}")
    print(
        "signal: "
        f"lead={params['lead']} fs={signal.fs:g} "
        f"(original {signal.original_fs:g}) "
        f"samples={signal.n_samples} duration={signal.duration_sec:.1f}s "
        f"source={signal.source} rpeaks={params['rpeakSource']}"
    )
    print(f"beats: {params['nBeatsClassified']}")
    print(f"summary: {result['summary']}")
    print(f"quality: {result['quality']['score']:.2f} {result['quality']['level']}")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
