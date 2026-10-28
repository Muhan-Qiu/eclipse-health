import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { Maximize2, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecordSignals, useSignal } from "@/lib/api/queries";
import type { AnalysisResult, Beat } from "@/lib/api/types";
import { useAppTheme } from "@/lib/theme";
import {
  clampView,
  formatClock,
  formatSeconds,
  minMaxDecimate,
  nearestPeakIndex,
} from "@/lib/waveform";

interface WaveformViewerProps {
  recordId: string;
  leads: string[];
  analysis?: AnalysisResult | null;
  selectedBeatIndex?: number | null;
  onBeatSelect?: (beat: Beat | null) => void;
  height?: number;
  compact?: boolean;
  className?: string;
}

function cssToken(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

export function WaveformViewer({
  recordId,
  leads,
  analysis,
  selectedBeatIndex = null,
  onBeatSelect,
  height = 300,
  compact = false,
  className,
}: WaveformViewerProps) {
  const { t } = useTranslation();
  const { resolved, palette } = useAppTheme();
  const signalsQuery = useRecordSignals(recordId);
  const availableLeads = useMemo(() => {
    if (leads.length > 0) return leads;
    return (signalsQuery.data ?? []).map((signal) => signal.lead);
  }, [leads, signalsQuery.data]);

  const [lead, setLead] = useState(availableLeads[0] ?? "");
  useEffect(() => {
    if (!availableLeads.length) return;
    if (!availableLeads.includes(lead)) setLead(availableLeads[0]);
  }, [availableLeads, lead]);

  const signalQuery = useSignal(recordId, lead || undefined);
  const signal = signalQuery.data;
  const fs = signal?.fs ?? 0;
  const duration = signal && fs > 0 ? signal.sampleCount / fs : 0;

  const [width, setWidth] = useState(0);
  const [view, setView] = useState<[number, number]>([0, duration]);
  const viewRef = useRef(view);
  viewRef.current = view;

  const containerRef = useRef<HTMLDivElement>(null);
  const [containerEl, setContainerEl] = useState<HTMLDivElement | null>(null);
  const attachContainer = useCallback((element: HTMLDivElement | null) => {
    containerRef.current = element;
    setContainerEl(element);
  }, []);
  const plotRef = useRef<uPlot | null>(null);
  const analysisRef = useRef<AnalysisResult | null>(analysis ?? null);
  const selectedRef = useRef<number | null>(selectedBeatIndex);
  const onBeatSelectRef = useRef(onBeatSelect);
  analysisRef.current = analysis ?? null;
  selectedRef.current = selectedBeatIndex;
  onBeatSelectRef.current = onBeatSelect;

  useEffect(() => {
    if (!containerEl) return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      setWidth(next > 0 ? next : 0);
    });
    observer.observe(containerEl);
    return () => observer.disconnect();
  }, [containerEl]);

  useEffect(() => {
    if (!signal || duration <= 0) return;
    // 长记录默认展示前 12 秒；整段 30 分钟压成 650px 只会是一条实心带。
    setView([0, Math.min(duration, 12)]);
  }, [signal, duration]);

  const applyView = useCallback(
    (nextStart: number, nextEnd: number) => {
      if (!duration) return;
      setView(clampView(nextStart, nextEnd, duration));
    },
    [duration],
  );

  const resetView = useCallback(() => {
    applyView(0, Math.min(duration, 12));
  }, [applyView, duration]);

  const zoomAt = useCallback(
    (factor: number, ratio = 0.5) => {
      const [start, end] = viewRef.current;
      const span = end - start;
      const nextSpan = Math.min(duration, Math.max(0.2, span * factor));
      const cursor = start + span * ratio;
      applyView(cursor - nextSpan * ratio, cursor + nextSpan * (1 - ratio));
    },
    [applyView, duration],
  );

  const pan = useCallback(
    (fraction: number) => {
      const [start, end] = viewRef.current;
      const span = end - start;
      applyView(start + span * fraction, end + span * fraction);
    },
    [applyView],
  );

  /* uPlot 实例：只在数据/尺寸/主题变化时重建，视图变化走 setData。 */
  useEffect(() => {
    const element = containerEl;
    if (!element || !signal || fs <= 0 || width <= 0) return;
    element.replaceChildren();

    const [start, end] = viewRef.current;
    const target = Math.max(240, width * 2);
    const decimated = minMaxDecimate(signal.samples, fs, start, end, target);
    const data: uPlot.AlignedData = [decimated.x, decimated.y];

    const signalColor = cssToken("--eh-signal", "#2f6a63");
    const gridColor = cssToken("--eh-grid-line", "rgba(0,0,0,0.08)");
    const borderColor = cssToken("--eh-border-strong", "rgba(0,0,0,0.2)");
    const mutedColor = cssToken("--eh-text-muted", "#5e6974");
    const warningColor = cssToken("--eh-warning", "#8a5a00");
    const dangerColor = cssToken("--eh-danger", "#b4363f");
    const accentColor = cssToken("--eh-accent", "#4f6b6b");

    const drawAnnotations: uPlot.Plugin = {
      hooks: {
        draw: (plot) => {
          const current = analysisRef.current;
          const bbox = plot.bbox;
          if (!current || bbox.width <= 0) return;
          const { ctx } = plot;
          const xMin = plot.scales.x.min ?? 0;
          const xMax = plot.scales.x.max ?? duration;

          ctx.save();
          const drawBand = (fromSec: number, toSec: number, color: string, alpha: number) => {
            const left = plot.valToPos(Math.max(xMin, fromSec), "x", true);
            const right = plot.valToPos(Math.min(xMax, toSec), "x", true);
            if (right <= left) return;
            ctx.globalAlpha = alpha;
            ctx.fillStyle = color;
            ctx.fillRect(left, bbox.top, right - left, bbox.height);
          };

          for (const segment of current.quality.segments ?? []) {
            if (segment.quality < 0.7) {
              drawBand(segment.startSec, segment.endSec, dangerColor, 0.12);
            } else if (segment.quality < 0.82) {
              drawBand(segment.startSec, segment.endSec, warningColor, 0.11);
            }
          }
          for (const warning of current.quality.warnings ?? []) {
            if (
              warning.startSec !== null &&
              warning.startSec !== undefined &&
              warning.endSec !== null &&
              warning.endSec !== undefined
            ) {
              drawBand(
                warning.startSec,
                warning.endSec,
                warning.severity === "error" ? dangerColor : warningColor,
                0.1,
              );
            }
          }

          const selected = selectedRef.current;
          current.beats.forEach((beat, index) => {
            const seconds = beat.rPeakSample / fs;
            if (seconds < xMin || seconds > xMax) return;
            const x = plot.valToPos(seconds, "x", true);
            const isSelected = selected === index;
            const abnormal = beat.label !== "N";
            ctx.globalAlpha = isSelected ? 0.95 : 0.35;
            ctx.strokeStyle = isSelected
              ? accentColor
              : abnormal
                ? warningColor
                : signalColor;
            ctx.lineWidth = isSelected ? 2 : 1;
            ctx.beginPath();
            ctx.moveTo(x, bbox.top);
            ctx.lineTo(x, bbox.top + bbox.height);
            ctx.stroke();

            if (isSelected) {
              ctx.globalAlpha = 0.12;
              ctx.fillStyle = accentColor;
              ctx.fillRect(x - 3, bbox.top, 6, bbox.height);
            }
            if (abnormal) {
              ctx.globalAlpha = 0.9;
              ctx.fillStyle = warningColor;
              ctx.font = "10px ui-monospace, monospace";
              ctx.fillText(beat.label.slice(0, 4), x + 2, bbox.top + 10);
            }
          });
          ctx.restore();
        },
      },
    };

    const plot = new uPlot(
      {
        width,
        height,
        padding: [8, 12, 4, 4],
        legend: { show: false },
        cursor: { show: false },
        scales: {
          x: { time: false, min: start, max: end },
          y: { auto: true },
        },
        axes: [
          {
            stroke: mutedColor,
            grid: { stroke: gridColor, width: 1 },
            ticks: { stroke: borderColor, width: 1, size: 4 },
            font: "11px ui-monospace, monospace",
            values: (_u, splits) => splits.map((value) => formatClock(value)),
          },
          {
            stroke: mutedColor,
            grid: { stroke: gridColor, width: 1 },
            ticks: { stroke: borderColor, width: 1, size: 4 },
            font: "11px ui-monospace, monospace",
            size: 52,
            values: (_u, splits) =>
              splits.map((value) => `${value.toFixed(2)} mV`),
          },
        ],
        series: [
          {},
          {
            stroke: signalColor,
            width: 1.5,
            fill: "transparent",
            points: { show: false },
          },
        ],
        plugins: [drawAnnotations],
      },
      data,
      element,
    );
    plotRef.current = plot;

    const over = plot.over;
    over.style.cursor = compact ? "default" : "crosshair";

    const rectOf = () => over.getBoundingClientRect();
    const xToSeconds = (clientX: number) => {
      const rect = rectOf();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const [viewStart, viewEnd] = viewRef.current;
      return viewStart + ratio * (viewEnd - viewStart);
    };

    const onWheel = (event: WheelEvent) => {
      if (compact) return;
      event.preventDefault();
      const rect = rectOf();
      const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      zoomAt(event.deltaY > 0 ? 1.25 : 0.8, ratio);
    };
    over.addEventListener("wheel", onWheel, { passive: false });

    let dragging = false;
    let moved = false;
    let startX = 0;
    let startView: [number, number] = [0, 0];

    const selectAt = (clientX: number) => {
      const current = analysisRef.current;
      const callback = onBeatSelectRef.current;
      if (!current || !callback) return;
      const index = nearestPeakIndex(current.beats, fs, xToSeconds(clientX));
      callback(index === null ? null : current.beats[index]);
    };

    const onPointerDown = (event: PointerEvent) => {
      if (compact || event.button !== 0) return;
      dragging = true;
      moved = false;
      startX = event.clientX;
      startView = [...viewRef.current] as [number, number];
      try {
        over.setPointerCapture(event.pointerId);
      } catch {
        // 某些嵌入式 webview 不支持指针捕获；拖拽仍通过 over 上的事件完成
      }
      over.style.cursor = "grabbing";
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!dragging) return;
      const dx = event.clientX - startX;
      if (Math.abs(dx) > 3) moved = true;
      if (!moved) return;
      const rect = rectOf();
      const span = startView[1] - startView[0];
      const shift = (-dx / Math.max(rect.width, 1)) * span;
      applyView(startView[0] + shift, startView[1] + shift);
    };

    const onPointerUp = (event: PointerEvent) => {
      if (!dragging) return;
      dragging = false;
      over.style.cursor = compact ? "default" : "crosshair";
      try {
        if (over.hasPointerCapture(event.pointerId)) {
          over.releasePointerCapture(event.pointerId);
        }
      } catch {
        // 忽略指针捕获失败
      }
    };

    const onClick = (event: MouseEvent) => {
      if (compact) return;
      if (moved) {
        moved = false;
        return;
      }
      selectAt(event.clientX);
    };

    over.addEventListener("pointerdown", onPointerDown);
    over.addEventListener("pointermove", onPointerMove);
    over.addEventListener("pointerup", onPointerUp);
    over.addEventListener("pointercancel", onPointerUp);
    over.addEventListener("click", onClick);

    return () => {
      over.removeEventListener("wheel", onWheel);
      over.removeEventListener("pointerdown", onPointerDown);
      over.removeEventListener("pointermove", onPointerMove);
      over.removeEventListener("pointerup", onPointerUp);
      over.removeEventListener("pointercancel", onPointerUp);
      over.removeEventListener("click", onClick);
      plot.destroy();
      plotRef.current = null;
    };
  }, [
    signal,
    fs,
    width,
    height,
    compact,
    resolved,
    palette,
    duration,
    zoomAt,
    applyView,
    containerEl,
  ]);

  /* 视图变化：重新做像素级 min/max，而不是缩放大数组。 */
  useEffect(() => {
    const plot = plotRef.current;
    if (!plot || !signal || fs <= 0) return;
    const [start, end] = view;
    const target = Math.max(240, width * 2);
    const decimated = minMaxDecimate(signal.samples, fs, start, end, target);
    plot.batch(() => {
      plot.setData([decimated.x, decimated.y]);
      plot.setScale("x", { min: start, max: end });
    });
  }, [view, signal, fs, width]);

  useEffect(() => {
    plotRef.current?.redraw(false);
  }, [analysis, selectedBeatIndex, resolved, palette]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (compact) return;
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomAt(0.8);
    } else if (event.key === "-") {
      event.preventDefault();
      zoomAt(1.25);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      pan(-0.1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      pan(0.1);
    } else if (event.key === "0" || event.key === "Home") {
      event.preventDefault();
      resetView();
    }
  };

  if (signalQuery.isLoading) {
    return <Skeleton className={cn("w-full rounded-lg", className)} style={{ height }} />;
  }

  if (signalQuery.isError || !signal) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-lg border border-dashed border-border px-4 text-center",
          className,
        )}
        style={{ height }}
      >
        <p className="eh-small text-muted-foreground">
          {signalQuery.isError ? t("waveform.loadError") : t("waveform.empty")}
        </p>
      </div>
    );
  }

  const beatCount = analysis?.beats.length ?? 0;

  return (
    <div className={className}>
      {!compact ? (
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div
            className="flex flex-wrap items-center gap-1"
            role="group"
            aria-label={t("waveform.lead")}
          >
            {availableLeads.map((item) => (
              <Button
                key={item}
                variant={item === lead ? "secondary" : "ghost"}
                size="xs"
                aria-pressed={item === lead}
                onClick={() => setLead(item)}
              >
                {item}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={t("waveform.zoomIn")}
              onClick={() => zoomAt(0.8)}
            >
              <ZoomIn aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={t("waveform.zoomOut")}
              onClick={() => zoomAt(1.25)}
            >
              <ZoomOut aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={t("waveform.reset")}
              onClick={resetView}
            >
              <RotateCcw aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={t("waveform.showFull")}
              onClick={() => applyView(0, duration)}
              disabled={duration <= 12}
            >
              <Maximize2 aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}

      <div
        ref={attachContainer}
        role="group"
        tabIndex={compact ? -1 : 0}
        aria-label={t("waveform.ariaLabel", {
          lead,
          duration: formatSeconds(duration),
          beats: beatCount,
        })}
        aria-describedby={compact ? undefined : "waveform-instructions"}
        onKeyDown={onKeyDown}
        className={cn(
          "w-full overflow-hidden rounded-lg border border-border bg-surface",
          !compact && "focus-visible:ring-2 focus-visible:ring-ring",
        )}
        style={{ height }}
      />

      {!compact ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p id="waveform-instructions" className="eh-caption text-muted-foreground">
            {t("waveform.instructions")}
          </p>
          <p className="eh-caption text-muted-foreground">
            {t("waveform.summary", {
              duration: formatSeconds(duration),
              fs: fs.toFixed(0),
              beats: beatCount,
            })}
          </p>
        </div>
      ) : null}
    </div>
  );
}
