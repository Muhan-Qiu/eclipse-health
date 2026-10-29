"""PNG 分享卡：1080×1350，适合微信/小红书。

分享卡永远不含成员姓名、备注或原始文件名；只展示日期、关键指标、小波形和水印。
"""

from __future__ import annotations

import threading
from io import BytesIO

import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from .content import (
    CLASS_ORDER,
    WATERMARK,
    ReportContent,
    format_datetime,
    format_duration,
)
from .fonts import configure_fonts

CARD_SIZE = (1080, 1350)
CARD_DPI = 150
BACKGROUND = "#FAF8F3"
TILE = "#F2EDE3"
BORDER = "#D9D2C5"
TEXT = "#171A1D"
MUTED = "#5E6974"
ACCENT = "#9A6A1E"
SIGNAL = "#0F7C72"
DANGER = "#B4363F"
WARNING = "#8A5A00"
INFO = "#2C5AA0"

CLASS_COLORS = {"N": SIGNAL, "SVEB": INFO, "VEB": DANGER, "F": WARNING}
LEFT = 0.07
RIGHT = 0.93
WIDTH = RIGHT - LEFT

_render_lock = threading.Lock()


def render_share_card(content: ReportContent) -> bytes:
    configure_fonts()
    figure = Figure(
        figsize=(CARD_SIZE[0] / CARD_DPI, CARD_SIZE[1] / CARD_DPI),
        dpi=CARD_DPI,
        facecolor=BACKGROUND,
    )
    with _render_lock:
        _header(figure, content)
        _hero(figure, content)
        _secondary(figure, content)
        _class_row(figure, content)
        _waveform(figure, content)
        _footer(figure, content)
        buffer = BytesIO()
        figure.savefig(
            buffer,
            format="png",
            dpi=CARD_DPI,
            facecolor=BACKGROUND,
            edgecolor="none",
        )
    return buffer.getvalue()


def _header(figure: Figure, content: ReportContent) -> None:
    figure.text(LEFT, 0.958, "ECLIPSE HEALTH", fontsize=10, color=MUTED, va="top")
    figure.text(
        RIGHT,
        0.958,
        f"生成 {format_datetime(content.generated_at, content.timezone)}",
        fontsize=9,
        color=MUTED,
        ha="right",
        va="top",
    )
    figure.text(LEFT, 0.905, "ECG 分析", fontsize=30, color=TEXT, va="top")
    subtitle = (
        f"{format_datetime(content.captured_at, content.timezone)}"
        f" · {format_duration(content.duration_sec)}"
        f" · 导联 {'、'.join(content.leads) or '—'}"
    )
    figure.text(LEFT, 0.845, subtitle, fontsize=10.5, color=MUTED, va="top")
    figure.add_artist(
        Line2D([LEFT, RIGHT], [0.825, 0.825], color=BORDER, lw=0.8, transform=figure.transFigure)
    )


def _hero(figure: Figure, content: ReportContent) -> None:
    hr = content.metrics.get("heart_rate_mean")
    figure.text(LEFT, 0.79, "平均心率", fontsize=11, color=MUTED, va="top")
    figure.text(
        LEFT,
        0.745,
        f"{hr:.0f}" if hr is not None else "—",
        fontsize=74,
        color=TEXT,
        va="top",
    )
    figure.text(LEFT + 0.31, 0.705, "bpm", fontsize=15, color=MUTED, va="top")
    if content.quality_score is not None:
        figure.text(
            LEFT + 0.31,
            0.752,
            f"信号质量 {content.quality_score * 100:.0f}%",
            fontsize=10,
            color=ACCENT,
            va="top",
        )


def _secondary(figure: Figure, content: ReportContent) -> None:
    metrics = content.metrics
    items = [
        ("RMSSD", _metric(metrics.get("rmssd"), " ms")),
        ("SDNN", _metric(metrics.get("sdnn"), " ms")),
        ("pNN50", _metric(metrics.get("pnn50"), "%")),
        ("正常心搏", _metric(metrics.get("n_ratio"), "%")),
    ]
    gap = 0.012
    tile_width = (WIDTH - gap * 3) / 4
    y = 0.565
    height = 0.085
    for index, (label, value) in enumerate(items):
        x = LEFT + index * (tile_width + gap)
        figure.add_artist(
            Rectangle(
                (x, y),
                tile_width,
                height,
                transform=figure.transFigure,
                facecolor=TILE,
                edgecolor=BORDER,
                lw=0.6,
            )
        )
        figure.text(x + 0.012, y + height - 0.017, label, fontsize=8, color=MUTED, va="top")
        figure.text(x + 0.012, y + 0.009, value, fontsize=16, color=TEXT, va="bottom")


def _class_row(figure: Figure, content: ReportContent) -> None:
    figure.text(LEFT, 0.525, "心搏分类", fontsize=9, color=MUTED, va="top")
    y = 0.49
    for index, label in enumerate(CLASS_ORDER):
        x = LEFT + index * 0.215
        figure.add_artist(
            Rectangle(
                (x, y - 0.008),
                0.018,
                0.018,
                transform=figure.transFigure,
                facecolor=CLASS_COLORS[label],
                edgecolor="none",
            )
        )
        ratio = content.class_ratios.get(label)
        figure.text(x + 0.025, y, f"{label}", fontsize=8.5, color=TEXT, va="top")
        figure.text(
            x + 0.025,
            y - 0.028,
            f"{ratio:.1f}%" if ratio is not None else "—",
            fontsize=7.8,
            color=MUTED,
            va="top",
        )


def _waveform(figure: Figure, content: ReportContent) -> None:
    axes = figure.add_axes([LEFT, 0.16, WIDTH, 0.26])
    waveform = content.waveform
    if waveform is None or waveform.samples.size == 0:
        axes.set_axis_off()
        axes.text(
            0.5,
            0.5,
            "无波形数据",
            ha="center",
            va="center",
            fontsize=12,
            color=MUTED,
            transform=axes.transAxes,
        )
        return
    samples = waveform.samples
    time = np.arange(samples.size, dtype=np.float64) / waveform.fs
    axes.plot(time, samples, color=SIGNAL, lw=0.7, antialiased=True)
    for index, label in waveform.rpeaks:
        if 0 <= index < samples.size:
            axes.plot(
                [time[index]],
                [samples[index]],
                marker="o",
                markersize=2.6,
                color=CLASS_COLORS.get(label, SIGNAL),
                linestyle="None",
                zorder=3,
            )
    axes.set_xlim(0, max(time[-1], 0.1))
    axes.set_axis_off()
    axes.set_title(
        f"ECG · {waveform.lead} · 前 {waveform.duration_sec:.0f} 秒",
        loc="left",
        fontsize=9,
        color=MUTED,
        pad=4,
    )


def _footer(figure: Figure, content: ReportContent) -> None:
    figure.add_artist(
        Line2D([LEFT, RIGHT], [0.115, 0.115], color=BORDER, lw=0.8, transform=figure.transFigure)
    )
    figure.text(LEFT, 0.088, WATERMARK, fontsize=11, color=ACCENT, va="top")
    figure.text(
        RIGHT,
        0.088,
        "eclipse health · 本地生成",
        fontsize=8.5,
        color=MUTED,
        ha="right",
        va="top",
    )
    figure.text(
        LEFT,
        0.052,
        "研究/教育用途，不构成医疗诊断。数据未离开本机。",
        fontsize=7.5,
        color=MUTED,
        va="top",
    )
    figure.text(
        0.5,
        0.47,
        WATERMARK,
        fontsize=44,
        color=ACCENT,
        alpha=0.045,
        ha="center",
        va="center",
        rotation=28,
        transform=figure.transFigure,
    )


def _metric(value: float | None, suffix: str) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}{suffix}" if suffix != "%" else f"{value:.1f}%"


__all__ = ["CARD_SIZE", "render_share_card"]
