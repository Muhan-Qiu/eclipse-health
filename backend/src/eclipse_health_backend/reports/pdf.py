"""PDF 报告：A4 纵向、多页、矢量文字与波形（matplotlib PdfPages）。

三种模板：
- ``simple``：1 页，波形 + 4 个关键指标 + 免责声明；
- ``detailed``：2 页，全部测量、分类比例、质量/警告；
- ``doctor``：2 页，完整测量表 + 参数/模型版本/技术细节，仍保留非诊断声明。
"""

from __future__ import annotations

import textwrap
import threading
from collections.abc import Iterable
from io import BytesIO
from typing import Any

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from .content import (
    CLASS_LABELS,
    CLASS_ORDER,
    DISCLAIMER,
    MODEL_CARD,
    ReportContent,
    format_datetime,
    format_duration,
)
from .fonts import configure_fonts

A4 = (8.27, 11.69)
BACKGROUND = "#FFFFFF"
TILE = "#F6F2EA"
BORDER = "#D9D2C5"
TEXT = "#171A1D"
MUTED = "#5E6974"
ACCENT = "#9A6A1E"
SIGNAL = "#0F7C72"
DANGER = "#B4363F"
WARNING = "#8A5A00"
INFO = "#2C5AA0"

CLASS_COLORS = {"N": SIGNAL, "SVEB": INFO, "VEB": DANGER, "F": WARNING}
LEFT = 0.06
RIGHT = 0.94
WIDTH = RIGHT - LEFT

_render_lock = threading.Lock()


def render_pdf(content: ReportContent) -> bytes:
    """按 ``content.template`` 渲染 PDF，返回完整字节。"""
    configure_fonts()
    buffer = BytesIO()
    with _render_lock, PdfPages(buffer, metadata=_metadata(content)) as pdf:
        if content.template == "simple":
            _simple_page(pdf, content)
        else:
            _overview_page(pdf, content, page_no=1, total=2)
            if content.template == "doctor":
                _doctor_page(pdf, content)
            else:
                _detailed_page(pdf, content)
    return buffer.getvalue()


def _metadata(content: ReportContent) -> dict[str, str]:
    return {
        "Title": "ECG 分析报告 · eclipse health",
        "Author": "eclipse health",
        "Subject": "ECG analysis report (non-diagnostic)",
        "Keywords": "ECG, Cardia 2.0, report, non-diagnostic",
        "Creator": f"eclipse health {content.app_version}",
    }


# --------------------------------------------------------------------------- #
# 页面骨架
# --------------------------------------------------------------------------- #


def _new_page() -> Figure:
    figure = Figure(figsize=A4, facecolor=BACKGROUND)
    return figure


def _header(figure: Figure, content: ReportContent, *, page_label: str = "") -> None:
    figure.text(LEFT, 0.965, "ECLIPSE HEALTH", fontsize=7, color=MUTED, va="top")
    figure.text(LEFT, 0.943, "ECG 分析报告", fontsize=19, color=TEXT, va="top")
    label = content.template_label + (f" · {page_label}" if page_label else "")
    figure.text(RIGHT, 0.94, label, fontsize=8, color=ACCENT, ha="right", va="top")
    figure.text(
        LEFT,
        0.914,
        f"生成 {format_datetime(content.generated_at, content.timezone)}"
        f" · 报告 {content.report_id}",
        fontsize=6.5,
        color=MUTED,
        va="top",
    )
    figure.add_artist(
        Line2D([LEFT, RIGHT], [0.9, 0.9], color=BORDER, lw=0.7, transform=figure.transFigure)
    )


def _meta_block(figure: Figure, content: ReportContent) -> None:
    captured = format_datetime(content.captured_at, content.timezone)
    model = f"{MODEL_CARD['name']} · {content.model_version or content.model.get('modelId', '')}"
    pairs = [
        ("记录时间", f"{captured}（{content.timezone}）"),
        ("设备", content.device),
        ("导联", "、".join(content.leads) or "—"),
        ("采样率", f"{content.fs:g} Hz" if content.fs else "—"),
        ("时长", format_duration(content.duration_sec)),
        ("成员", content.member_name),
        ("模型", model),
        ("逐搏总数", f"{content.beats_total}"),
    ]
    for index, (label, value) in enumerate(pairs):
        column = index % 2
        row = index // 2
        x = LEFT + column * (WIDTH / 2)
        y = 0.882 - row * 0.019
        figure.text(x, y, label, fontsize=6.8, color=MUTED, va="top")
        figure.text(x + 0.085, y, value, fontsize=7.4, color=TEXT, va="top")
    if content.notes:
        figure.text(LEFT, 0.882 - 4 * 0.019, "备注", fontsize=6.8, color=MUTED, va="top")
        figure.text(
            LEFT + 0.085,
            0.882 - 4 * 0.019,
            _truncate(content.notes, 64),
            fontsize=7.4,
            color=TEXT,
            va="top",
        )


def _waveform_block(
    figure: Figure, content: ReportContent, rect: list[float], *, title: str | None = None
) -> None:
    axes = figure.add_axes(rect)
    waveform = content.waveform
    if waveform is None or waveform.samples.size == 0:
        axes.set_axis_off()
        axes.text(
            0.5,
            0.5,
            "无波形数据",
            ha="center",
            va="center",
            fontsize=8,
            color=MUTED,
            transform=axes.transAxes,
        )
        return

    samples = waveform.samples
    time = np.arange(samples.size, dtype=np.float64) / waveform.fs
    axes.plot(time, samples, color=SIGNAL, lw=0.55, antialiased=True)
    for index, label in waveform.rpeaks:
        if 0 <= index < samples.size:
            axes.plot(
                [time[index]],
                [samples[index]],
                marker="o",
                markersize=2.0,
                color=CLASS_COLORS.get(label, SIGNAL),
                linestyle="None",
                zorder=3,
            )
    axes.set_xlim(0, max(time[-1], 0.1))
    axes.set_xlabel("秒", fontsize=6.5, color=MUTED, labelpad=2)
    axes.set_ylabel("mV", fontsize=6.5, color=MUTED, labelpad=2)
    axes.tick_params(axis="both", labelsize=6, colors=MUTED, length=2, width=0.5)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        axes.spines[spine].set_color(BORDER)
        axes.spines[spine].set_linewidth(0.6)
    axes.grid(True, color="#ECE6DB", lw=0.4)
    axes.set_axisbelow(True)
    axes.margins(x=0)
    heading = title or (
        f"ECG · {waveform.lead} · 前 {waveform.duration_sec:.0f} 秒"
        f"（共 {format_duration(content.duration_sec)}）"
    )
    axes.set_title(heading, loc="left", fontsize=7.4, color=MUTED, pad=3)


def _metric_tiles(
    figure: Figure,
    items: list[tuple[str, str]],
    *,
    y_top: float,
    columns: int = 4,
    tile_height: float = 0.068,
) -> float:
    gap = 0.012
    tile_width = (WIDTH - gap * (columns - 1)) / columns
    rows = (len(items) + columns - 1) // columns
    for index, (label, value) in enumerate(items):
        row = index // columns
        column = index % columns
        x = LEFT + column * (tile_width + gap)
        y = y_top - (row + 1) * tile_height - row * 0.008
        figure.add_artist(
            Rectangle(
                (x, y),
                tile_width,
                tile_height,
                transform=figure.transFigure,
                facecolor=TILE,
                edgecolor=BORDER,
                lw=0.5,
            )
        )
        figure.text(x + 0.012, y + tile_height - 0.016, label, fontsize=6.4, color=MUTED, va="top")
        figure.text(x + 0.012, y + 0.010, value, fontsize=13, color=TEXT, va="bottom")
    last_row = rows - 1
    return y_top - rows * tile_height - last_row * 0.008


def _section(figure: Figure, x: float, y: float, title: str) -> None:
    figure.text(x, y, title, fontsize=9, color=TEXT, va="top")
    figure.add_artist(
        Line2D(
            [x, RIGHT],
            [y - 0.012, y - 0.012],
            color=BORDER,
            lw=0.5,
            transform=figure.transFigure,
        )
    )


def _footer(figure: Figure, content: ReportContent, *, page_no: int, total: int) -> None:
    figure.add_artist(
        Line2D([LEFT, RIGHT], [0.072, 0.072], color=BORDER, lw=0.6, transform=figure.transFigure)
    )
    wrapped = textwrap.fill(DISCLAIMER, width=78)
    figure.text(LEFT, 0.058, wrapped, fontsize=5.9, color=MUTED, va="top", linespacing=1.5)
    figure.text(RIGHT, 0.04, f"第 {page_no} / {total} 页", fontsize=6, color=MUTED, ha="right")
    if content.watermark:
        figure.text(
            0.5,
            0.5,
            content.watermark,
            fontsize=34,
            color=ACCENT,
            alpha=0.07,
            ha="center",
            va="center",
            rotation=28,
            transform=figure.transFigure,
        )


# --------------------------------------------------------------------------- #
# 模板
# --------------------------------------------------------------------------- #


def _simple_page(pdf: PdfPages, content: ReportContent) -> None:
    figure = _new_page()
    _header(figure, content)
    _meta_block(figure, content)
    _waveform_block(figure, content, [LEFT, 0.5, WIDTH, 0.29])
    _metric_tiles(figure, _key_tiles(content), y_top=0.455, columns=4, tile_height=0.084)
    figure.text(LEFT, 0.335, "关键指标", fontsize=8, color=MUTED)
    figure.text(
        LEFT,
        0.31,
        _summary_line(content),
        fontsize=8.5,
        color=TEXT,
        va="top",
        wrap=True,
    )
    figure.text(LEFT, 0.285, _quality_line(content), fontsize=7.2, color=MUTED, va="top")
    figure.text(LEFT, 0.24, "说明", fontsize=8, color=MUTED)
    figure.text(
        LEFT,
        0.22,
        textwrap.fill(
            "本页为分析结果摘要。完整测量值、分类比例、质量与警告请使用「详细版」或「医生版」模板。",
            width=70,
        ),
        fontsize=7,
        color=TEXT,
        va="top",
        linespacing=1.6,
    )
    figure.text(LEFT, 0.17, _model_line(), fontsize=6.4, color=MUTED, va="top")
    _footer(figure, content, page_no=1, total=1)
    pdf.savefig(figure)


def _overview_page(pdf: PdfPages, content: ReportContent, *, page_no: int, total: int) -> None:
    figure = _new_page()
    _header(figure, content, page_label="概览")
    _meta_block(figure, content)
    _waveform_block(figure, content, [LEFT, 0.46, WIDTH, 0.28])
    _metric_tiles(figure, _key_tiles(content, extended=True), y_top=0.41, columns=4, tile_height=0.062)
    figure.text(LEFT, 0.275, _summary_line(content), fontsize=8.2, color=TEXT, va="top")
    figure.text(LEFT, 0.252, _quality_line(content), fontsize=7, color=MUTED, va="top")
    figure.text(
        LEFT,
        0.215,
        textwrap.fill(
            "第一页为波形与关键指标；后续页包含全部测量、分类比例、质量与警告、模型卡与技术细节。"
            "异常搏动以彩色圆点标在 R 峰位置："
            "青绿 N、蓝 SVEB、红 VEB、琥珀 F。",
            width=82,
        ),
        fontsize=6.8,
        color=MUTED,
        va="top",
        linespacing=1.6,
    )
    figure.text(LEFT, 0.16, _model_line(), fontsize=6.2, color=MUTED, va="top")
    _footer(figure, content, page_no=page_no, total=total)
    pdf.savefig(figure)


def _detailed_page(pdf: PdfPages, content: ReportContent) -> None:
    figure = _new_page()
    _header(figure, content, page_label="测量与质量")
    _section(figure, LEFT, 0.87, "全部测量")
    bottom = _measurement_table(figure, content, y_top=0.84, simple=False)
    _section(figure, LEFT, bottom - 0.03, "分类比例")
    _class_bars(figure, content, y_top=bottom - 0.055)
    _section(figure, LEFT, 0.268, "质量与警告")
    _warning_lines(figure, content, y_top=0.245, max_lines=5)
    _section(figure, LEFT, 0.18, "模型卡")
    figure.text(LEFT, 0.155, _model_line(), fontsize=6.8, color=TEXT, va="top")
    figure.text(
        LEFT,
        0.128,
        (
            f"模型版本 {content.model_version or content.model.get('modelId')}"
            f" · 任务 {_task_text(content)}"
        ),
        fontsize=6.4,
        color=MUTED,
        va="top",
    )
    _footer(figure, content, page_no=2, total=2)
    pdf.savefig(figure)


def _doctor_page(pdf: PdfPages, content: ReportContent) -> None:
    figure = _new_page()
    _header(figure, content, page_label="技术细节")
    _section(figure, LEFT, 0.87, "完整测量表")
    bottom = _measurement_table(figure, content, y_top=0.84, simple=False, detailed=True)
    _section(figure, LEFT, bottom - 0.025, "技术细节")
    lines = _technical_lines(content)
    y = bottom - 0.05
    for line in lines:
        figure.text(LEFT, y, line, fontsize=6.5, color=TEXT, va="top")
        y -= 0.0165
    _section(figure, LEFT, min(y - 0.01, 0.23), "模型卡与局限")
    figure.text(LEFT, min(y - 0.035, 0.205), _model_line(), fontsize=6.6, color=TEXT, va="top")
    limitations = "；".join(MODEL_CARD["limitations"])
    figure.text(
        LEFT,
        min(y - 0.06, 0.18),
        textwrap.fill(f"局限：{limitations}", width=96),
        fontsize=6.2,
        color=MUTED,
        va="top",
        linespacing=1.5,
    )
    _footer(figure, content, page_no=2, total=2)
    pdf.savefig(figure)


# --------------------------------------------------------------------------- #
# 内容块
# --------------------------------------------------------------------------- #


def _key_tiles(content: ReportContent, *, extended: bool = False) -> list[tuple[str, str]]:
    metrics = content.metrics
    quality = (
        f"{content.quality_score * 100:.0f}%"
        if content.quality_score is not None
        else "—"
    )
    tiles = [
        ("平均心率", _metric(metrics.get("heart_rate_mean"), " bpm")),
        ("RMSSD", _metric(metrics.get("rmssd"), " ms")),
        ("SDNN", _metric(metrics.get("sdnn"), " ms")),
        ("正常心搏占比", _metric(metrics.get("n_ratio"), "%")),
    ]
    if extended:
        tiles.extend(
            [
                ("最小心率", _metric(metrics.get("heart_rate_min"), " bpm")),
                ("最大心率", _metric(metrics.get("heart_rate_max"), " bpm")),
                ("pNN50", _metric(metrics.get("pnn50"), "%")),
                ("信号质量", quality),
            ]
        )
    return tiles


def _metric(value: float | None, suffix: str) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}{suffix}" if suffix != "%" else f"{value:.1f}%"


def _summary_line(content: ReportContent) -> str:
    parts = [
        f"HR {_metric(content.metrics.get('heart_rate_mean'), ' bpm')}",
        f"N {_metric(content.metrics.get('n_ratio'), '%')}",
        f"SVEB {_metric(content.metrics.get('svb_ratio'), '%')}",
        f"VEB {_metric(content.metrics.get('veb_ratio'), '%')}",
        f"F {_metric(content.metrics.get('f_ratio'), '%')}",
    ]
    return " · ".join(parts)


def _quality_line(content: ReportContent) -> str:
    quality = (
        f"{content.quality_score * 100:.0f}%（{content.quality_level or '—'}）"
        if content.quality_score is not None
        else "—"
    )
    return f"信号质量 {quality} · 逐搏总数 {content.beats_total}"


def _measurement_table(
    figure: Figure,
    content: ReportContent,
    *,
    y_top: float,
    simple: bool,
    detailed: bool = False,
) -> float:
    row_height = 0.0225
    columns = (
        [("项目", LEFT), ("数值", 0.34), ("单位", 0.46), ("方法", 0.55), ("置信度", 0.74)]
        if detailed
        else [("项目", LEFT), ("数值", 0.42), ("单位", 0.54), ("方法", 0.64)]
    )
    figure.add_artist(
        Rectangle(
            (LEFT, y_top - row_height + 0.002),
            WIDTH,
            row_height,
            transform=figure.transFigure,
            facecolor=TILE,
            edgecolor="none",
        )
    )
    for label, x in columns:
        figure.text(x, y_top, label, fontsize=6.3, color=MUTED, va="top")
    y = y_top - row_height
    for index, item in enumerate(content.measurements):
        if index % 2 == 1:
            figure.add_artist(
                Rectangle(
                    (LEFT, y - row_height + 0.002),
                    WIDTH,
                    row_height,
                    transform=figure.transFigure,
                    facecolor="#FAF7F1",
                    edgecolor="none",
                )
            )
        label = str(item.get("label") or item.get("code") or "")
        value = _measurement_value(item)
        unit = str(item.get("unit") or "")
        method = str(item.get("method") or "—")
        confidence = item.get("confidence")
        figure.text(LEFT, y, label, fontsize=6.5, color=TEXT, va="top")
        figure.text(0.34 if detailed else 0.42, y, value, fontsize=6.5, color=TEXT, va="top")
        figure.text(0.46 if detailed else 0.54, y, unit, fontsize=6.3, color=MUTED, va="top")
        figure.text(0.55 if detailed else 0.64, y, method, fontsize=6.1, color=MUTED, va="top")
        if detailed:
            figure.text(
                0.74,
                y,
                f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "—",
                fontsize=6.2,
                color=MUTED,
                va="top",
            )
        y -= row_height
        if y < 0.36:
            break
    return y


def _measurement_value(item: dict[str, Any]) -> str:
    value = item.get("value")
    if not isinstance(value, (int, float)):
        return "—"
    number = float(value)
    if abs(number) >= 100:
        return f"{number:.1f}"
    return f"{number:.2f}" if number % 1 else f"{number:.1f}"


def _class_bars(figure: Figure, content: ReportContent, *, y_top: float) -> None:
    bar_x = 0.27
    bar_width = 0.52
    for index, label in enumerate(CLASS_ORDER):
        y = y_top - index * 0.032
        ratio = content.class_ratios.get(label)
        figure.text(LEFT, y, f"{label} · {CLASS_LABELS[label]}", fontsize=6.8, color=TEXT, va="top")
        figure.add_artist(
            Rectangle(
                (bar_x, y - 0.012),
                bar_width,
                0.012,
                transform=figure.transFigure,
                facecolor="#EFEADF",
                edgecolor="none",
            )
        )
        if ratio is not None:
            filled = max(0.0, min(1.0, ratio / 100.0)) * bar_width
            figure.add_artist(
                Rectangle(
                    (bar_x, y - 0.012),
                    filled,
                    0.012,
                    transform=figure.transFigure,
                    facecolor=CLASS_COLORS[label],
                    edgecolor="none",
                )
            )
        figure.text(
            bar_x + bar_width + 0.015,
            y,
            f"{ratio:.1f}%" if ratio is not None else "—",
            fontsize=6.6,
            color=MUTED,
            va="top",
        )


def _warning_lines(
    figure: Figure, content: ReportContent, *, y_top: float, max_lines: int
) -> None:
    if not content.warnings:
        figure.text(LEFT, y_top, "无警告。", fontsize=7, color=MUTED, va="top")
        return
    rendered = 0
    y = y_top
    for warning in content.warnings:
        if rendered >= max_lines:
            figure.text(LEFT, y, "…", fontsize=6.5, color=MUTED, va="top")
            break
        severity = str(warning.get("severity") or "warning")
        marker = {"error": "✕", "warning": "!", "info": "i"}.get(severity, "·")
        text = f"{marker} {warning.get('message') or warning.get('code')}"
        wrapped = textwrap.wrap(text, width=92) or [text]
        for line in wrapped:
            if rendered >= max_lines:
                break
            figure.text(LEFT, y, line, fontsize=6.5, color=TEXT, va="top")
            y -= 0.0145
            rendered += 1


def _model_line() -> str:
    input_info = MODEL_CARD["input"]
    return (
        f"{MODEL_CARD['name']}（{MODEL_CARD['modelId']}）· "
        f"{input_info['leads'][0]} 单导联 {input_info['fs']} Hz · "
        f"窗口 {input_info['beatsPerWindow']} 搏 · 特征 {input_info['features']} · "
        f"训练数据 {MODEL_CARD['trainingData']} · 参数 {MODEL_CARD['parameters']:,} · 非诊断用途"
    )


def _task_text(content: ReportContent) -> str:
    return str(content.model.get("task") or "beat-classification")


def _technical_lines(content: ReportContent) -> Iterable[str]:
    metrics = content.metrics
    parameter_keys = (
        "engine",
        "engineVersion",
        "sequenceLength",
        "windowSamples",
        "features",
        "nBeatsDetected",
        "nBeatsClassified",
        "meanConfidence",
    )
    parameters = ", ".join(
        f"{key}={content.parameters[key]}"
        for key in parameter_keys
        if key in content.parameters
    )
    provenance = ", ".join(
        f"{key}={content.provenance[key]}"
        for key in ("preprocess", "preprocessVersion", "modelFile", "engine")
        if key in content.provenance
    )
    quality_line = (
        f"信号质量：{content.quality_level or '—'}（{content.quality_score:.3f}）"
        if content.quality_score is not None
        else "信号质量：—"
    )
    lines = [
        (
            f"记录 ID：{content.record_id} · 分析 ID：{content.analysis_id} · "
            f"报告 ID：{content.report_id}"
        ),
        (
            f"模板：{content.template}（{content.template_label}）"
            f" · 脱敏：{'是' if content.redacted else '否'}"
            f" · 水印：{content.watermark or '无'}"
        ),
        f"设备来源：{content.source_kind} / {content.device} · 时区：{content.timezone}",
        (
            f"采样率：{content.fs:g} Hz · 记录时长：{format_duration(content.duration_sec)}"
            f" · 逐搏总数：{content.beats_total}"
            f" · 展示窗口：前 {content.window_seconds:g} 秒"
        ),
        "测量值："
        + "，".join(
            f"{code}={metrics.get(code):.2f}" if metrics.get(code) is not None else f"{code}=—"
            for code in (
                "heart_rate_mean",
                "heart_rate_min",
                "heart_rate_max",
                "sdnn",
                "rmssd",
                "pnn50",
            )
        ),
        "类别计数："
        + "，".join(f"{label}={content.class_counts.get(label, 0)}" for label in CLASS_ORDER),
        quality_line,
        f"分析参数：{parameters or '—'}",
        f"预处理与引擎：{provenance or '—'}",
        (
            f"模型：{MODEL_CARD['name']} / {content.model.get('modelId')}"
            f" · 版本 {content.model_version or '—'}"
            f" · 训练数据 {MODEL_CARD['trainingData']}"
        ),
        "报告由本地后端直接渲染（matplotlib），不经过浏览器或网络。",
    ]
    return lines


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


__all__ = ["render_pdf"]
