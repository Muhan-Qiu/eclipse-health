import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { cn } from "cn";
import type { AnalysisResult, Beat } from "@/lib/api/types";
import {
  beatRange,
  clampView,
  formatClock,
  minMaxDecimate,
  nearestPeakIndex,
} from "@/lib/waveform";
import { useWaveColors } from "@/features/waveform/colors";
import { prefersReducedMotion } from "@/lib/motion";

/** 选中 R 峰的一次性脉冲时长；到点后停帧，不循环。 */
const PULSE_MS = 180;
const HOVER_RAMP_MS = 120;

type HoverTarget = {
  kind: "beat" | "segment" | "warning";
  key: string;
  at: number;
};

export interface LeadStripProps {
  samples: Float32Array;
  fs: number;
  lead: string;
  unit: string;
  view: [number, number];
  duration: number;
  height: number;
  /** 网格里显示导联名/单位/标尺；单导联模式由外层标题承担。 */
  showHeader?: boolean;
  /** 网格里只给最后一行显示时间轴。 */
  showTimeAxis?: boolean;
  showScale?: boolean;
  isPrimary?: boolean;
  interactive?: boolean;
  className?: string;
  analysis?: AnalysisResult | null;
  selectedBeatIndex?: number | null;
  onBeatSelect?: (beat: Beat | null) => void;
  onViewChange?: (view: [number, number]) => void;
  ariaLabel?: string;
}

/**
 * 单条导联的 uPlot 画布。
 *
 * 视图（缩放/平移）由父组件统一持有：12 导联网格共享同一时间窗，
 * 主视图与节律条也读同一份 `view`。这里只负责按像素做 min/max 降采样。
 */
export function LeadStrip({
  samples,
  fs,
  lead,
  unit,
  view,
  duration,
  height,
  showHeader = false,
  showTimeAxis = true,
  showScale = false,
  isPrimary = true,
  interactive = true,
  className,
  analysis = null,
  selectedBeatIndex = null,
  onBeatSelect,
  onViewChange,
  ariaLabel,
}: LeadStripProps) {
  const colors = useWaveColors();
  const [width, setWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const plotRef = useRef<uPlot | null>(null);

  const viewRef = useRef<[number, number]>(view);
  viewRef.current = view;
  const analysisRef = useRef<AnalysisResult | null>(analysis);
  analysisRef.current = analysis;
  const selectedRef = useRef<number | null>(selectedBeatIndex);
  selectedRef.current = selectedBeatIndex;
  /** 选中时刻用于一次性脉冲；视图变化重建 plot 时不重置，避免缩放触发重播。 */
  const pulseRef = useRef<{ index: number; at: number } | null>(null);
  const hoverRef = useRef<HoverTarget | null>(null);
  const animateRef = useRef<((ms?: number) => void) | null>(null);
  const onChangeRef = useRef(onViewChange);
  onChangeRef.current = onViewChange;
  const onBeatRef = useRef(onBeatSelect);
  onBeatRef.current = onBeatSelect;
  const durationRef = useRef(duration);
  durationRef.current = duration;

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      setWidth(next > 0 ? next : 0);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || !samples.length || fs <= 0 || width <= 0) return;
    element.replaceChildren();
    const reduced = prefersReducedMotion();
    const selectedIndex = selectedRef.current;
    if (selectedIndex === null) {
      pulseRef.current = null;
    } else if (!pulseRef.current || pulseRef.current.index !== selectedIndex) {
      // 视图重建（缩放/平移）时索引不变，不重播脉冲。
      pulseRef.current = { index: selectedIndex, at: performance.now() };
    }
    hoverRef.current = null;

    const [start, end] = viewRef.current;
    const target = Math.max(200, Math.round(width * 2));
    const decimated = minMaxDecimate(samples, fs, start, end, target);
    const data: uPlot.AlignedData = [decimated.x, decimated.y];

    const drawAnnotations: uPlot.Plugin = {
      hooks: {
        draw: (plot) => {
          const bbox = plot.bbox;
          if (bbox.width <= 0 || bbox.height <= 0) return;
          const { ctx } = plot;
          const current = analysisRef.current;
          const xMin = plot.scales.x.min ?? 0;
          const xMax = plot.scales.x.max ?? durationRef.current;
          const now = performance.now();
          const hover = hoverRef.current;
          const hoverRamp = (kind: HoverTarget["kind"], key: string) =>
            hover && hover.kind === kind && hover.key === key
              ? Math.min(1, (now - hover.at) / HOVER_RAMP_MS)
              : 0;
          const pulse = pulseRef.current;
          const pulseT = pulse
            ? Math.min(1, (now - pulse.at) / PULSE_MS)
            : 1;

          const drawBand = (fromSec: number, toSec: number, color: string, alpha: number) => {
            const left = plot.valToPos(Math.max(xMin, fromSec), "x", true);
            const right = plot.valToPos(Math.min(xMax, toSec), "x", true);
            if (right <= left) return;
            ctx.save();
            ctx.globalAlpha = alpha;
            ctx.fillStyle = color;
            ctx.fillRect(left, bbox.top, right - left, bbox.height);
            ctx.restore();
          };

          ctx.save();
          if (current) {
            for (const segment of current.quality.segments ?? []) {
              if (segment.endSec <= xMin || segment.startSec >= xMax) continue;
              const lifted = 0.07 * hoverRamp("segment", `s:${segment.startSec}`);
              if (segment.quality < 0.7) {
                drawBand(segment.startSec, segment.endSec, colors.danger, 0.12 + lifted);
              } else if (segment.quality < 0.82) {
                drawBand(segment.startSec, segment.endSec, colors.warning, 0.11 + lifted);
              }
            }
            for (const warning of current.quality.warnings ?? []) {
              if (
                warning.startSec !== null &&
                warning.startSec !== undefined &&
                warning.endSec !== null &&
                warning.endSec !== undefined
              ) {
                const lifted = 0.07 * hoverRamp("warning", `w:${warning.startSec}`);
                drawBand(
                  warning.startSec,
                  warning.endSec,
                  warning.severity === "error" ? colors.danger : colors.warning,
                  0.1 + lifted,
                );
              }
            }

            const [from, to] = beatRange(current.beats, fs, xMin, xMax);
            for (let index = from; index < to; index += 1) {
              const beat = current.beats[index];
              const x = plot.valToPos(beat.rPeakSample / fs, "x", true);
              const isSelected = selectedRef.current === index;
              const isHovered = hoverRamp("beat", `b:${index}`) > 0;
              const enter =
                !reduced && pulse?.index === index ? pulseT : 1;
              const abnormal = beat.label !== "N";
              const hoverLift = hoverRamp("beat", `b:${index}`) * 0.22;
              ctx.globalAlpha = isSelected
                ? 0.55 + 0.4 * enter
                : Math.min(1, (abnormal ? 0.42 : 0.32) + hoverLift);
              ctx.strokeStyle = isSelected
                ? colors.accent
                : abnormal
                  ? colors.warning
                  : colors.signal;
              ctx.lineWidth = isSelected ? 2 : isHovered ? 1.5 : 1;
              ctx.beginPath();
              ctx.moveTo(x, bbox.top);
              ctx.lineTo(x, bbox.top + bbox.height);
              ctx.stroke();

              if (isSelected) {
                // 一次性扩散+淡出，不循环；减少动效时只保留静态色带。
                const spread = reduced ? 3 : 3 + 6 * pulseT;
                ctx.globalAlpha = reduced ? 0.16 : 0.18 * (1 - pulseT);
                ctx.fillStyle = colors.accent;
                ctx.fillRect(x - spread, bbox.top, spread * 2, bbox.height);

                const amplitude = samples[Math.round(beat.rPeakSample)];
                const y = Number.isFinite(amplitude)
                  ? plot.valToPos(amplitude, "y", true)
                  : null;
                if (y !== null && y >= bbox.top - 2 && y <= bbox.top + bbox.height + 2) {
                  ctx.globalAlpha = 0.95;
                  ctx.fillStyle = colors.accent;
                  ctx.beginPath();
                  ctx.arc(x, y, 2.6, 0, Math.PI * 2);
                  ctx.fill();
                  if (!reduced && pulseT < 1) {
                    ctx.globalAlpha = 0.35 * (1 - pulseT);
                    ctx.strokeStyle = colors.accent;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.arc(x, y, 2.6 + 6 * pulseT, 0, Math.PI * 2);
                    ctx.stroke();
                  }
                }
              }
              if (abnormal && isPrimary) {
                ctx.globalAlpha = Math.min(1, 0.9 + hoverRamp("beat", `b:${index}`));
                ctx.fillStyle = colors.warning;
                ctx.font = "10px ui-monospace, monospace";
                ctx.fillText(beat.label.slice(0, 4), x + 2, bbox.top + 10);
              }
            }
          }

          if (showScale) {
            const yMin = plot.scales.y.min ?? 0;
            const yMax = plot.scales.y.max ?? 1;
            const yRange = yMax - yMin;
            const span = xMax - xMin;
            if (yRange > 0 && span > 0) {
              const unitLabel = unit || "mV";
              const mvSpan = yRange <= 1.5 ? 0.5 : yRange <= 4 ? 1 : yRange <= 10 ? 2 : 5;
              let mvPx = (mvSpan / yRange) * bbox.height;
              let mvLabel = mvSpan;
              if (mvPx > bbox.height * 0.7) {
                mvPx /= 2;
                mvLabel /= 2;
              }
              const secPx = (0.2 / span) * bbox.width;
              const baseX = bbox.left + 10;
              const baseY = bbox.top + bbox.height - 4;
              ctx.globalAlpha = 0.75;
              ctx.strokeStyle = colors.muted;
              ctx.fillStyle = colors.muted;
              ctx.lineWidth = 1;
              ctx.font = "9px ui-monospace, monospace";
              ctx.beginPath();
              ctx.moveTo(baseX, baseY - mvPx);
              ctx.lineTo(baseX, baseY);
              ctx.lineTo(baseX + secPx, baseY);
              ctx.stroke();
              ctx.fillText(`${mvLabel} ${unitLabel}`, baseX + 3, baseY - mvPx + 4);
              ctx.fillText("0.2 s", baseX + secPx + 3, baseY - 2);
            }
          }
          ctx.restore();
        },
      },
    };

    const axes: uPlot.Axis[] = [
      {
        stroke: colors.muted,
        grid: { stroke: colors.grid, width: 1 },
        ticks: { stroke: colors.border, width: 1, size: 3 },
        font: showHeader ? "9px ui-monospace, monospace" : "10px ui-monospace, monospace",
        size: showTimeAxis ? (showHeader ? 14 : 20) : 0,
        show: showTimeAxis,
        space: showHeader ? 72 : 50,
        values: (_u, splits) => splits.map((value) => formatClock(value)),
      },
      {
        stroke: colors.muted,
        grid: { stroke: colors.grid, width: 1 },
        ticks: { stroke: colors.border, width: 1, size: 3 },
        font: "10px ui-monospace, monospace",
        size: showTimeAxis && !showHeader ? 48 : 0,
        show: showTimeAxis && !showHeader,
        values: (_u, splits) =>
          splits.map((value) => `${value.toFixed(1)} ${unit || "mV"}`),
      },
    ];

    const plot = new uPlot(
      {
        width,
        height,
        padding: showHeader ? [2, 24, 2, 24] : [6, 26, 2, 26],
        legend: { show: false },
        cursor: { show: false },
        scales: {
          x: { time: false, min: start, max: end },
          y: { auto: true },
        },
        axes,
        series: [
          {},
          {
            stroke: colors.signal,
            width: 1.2,
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
    plot.over.style.cursor = interactive ? "crosshair" : "default";

    let frame = 0;
    const animate = (ms = PULSE_MS) => {
      if (reduced) return;
      cancelAnimationFrame(frame);
      const started = performance.now();
      const tick = () => {
        plot.redraw(false);
        frame = performance.now() - started < ms ? requestAnimationFrame(tick) : 0;
      };
      frame = requestAnimationFrame(tick);
    };
    animateRef.current = animate;

    const xToSeconds = (clientX: number) => {
      const rect = plot.over.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const [viewStart, viewEnd] = viewRef.current;
      return viewStart + ratio * (viewEnd - viewStart);
    };

    const emit = (nextStart: number, nextEnd: number) => {
      if (!interactive) return;
      onChangeRef.current?.(
        clampView(nextStart, nextEnd, durationRef.current),
      );
    };

    const onWheel = (event: WheelEvent) => {
      if (!interactive) return;
      event.preventDefault();
      const rect = plot.over.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      const [viewStart, viewEnd] = viewRef.current;
      const span = viewEnd - viewStart;
      const factor = event.deltaY > 0 ? 1.25 : 0.8;
      const nextSpan = Math.min(
        durationRef.current,
        Math.max(0.2, span * factor),
      );
      const cursor = viewStart + span * ratio;
      emit(cursor - nextSpan * ratio, cursor + nextSpan * (1 - ratio));
    };
    plot.over.addEventListener("wheel", onWheel, { passive: false });

    let dragging = false;
    let moved = false;
    let startX = 0;
    let startView: [number, number] = [0, 0];

    const onPointerDown = (event: PointerEvent) => {
      if (!interactive || event.button !== 0) return;
      dragging = true;
      moved = false;
      startX = event.clientX;
      startView = [...viewRef.current] as [number, number];
      try {
        plot.over.setPointerCapture(event.pointerId);
      } catch {
        // 某些嵌入式 webview 不支持指针捕获
      }
      plot.over.style.cursor = "grabbing";
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!dragging) return;
      const dx = event.clientX - startX;
      if (Math.abs(dx) > 3) moved = true;
      if (!moved) return;
      const rect = plot.over.getBoundingClientRect();
      const span = startView[1] - startView[0];
      const shift = (-dx / Math.max(rect.width, 1)) * span;
      emit(startView[0] + shift, startView[1] + shift);
    };

    const onPointerUp = (event: PointerEvent) => {
      if (!dragging) return;
      dragging = false;
      plot.over.style.cursor = interactive ? "crosshair" : "default";
      try {
        if (plot.over.hasPointerCapture(event.pointerId)) {
          plot.over.releasePointerCapture(event.pointerId);
        }
      } catch {
        // 忽略指针捕获失败
      }
    };

    const onClick = (event: MouseEvent) => {
      if (!interactive) return;
      if (moved) {
        moved = false;
        return;
      }
      const current = analysisRef.current;
      const callback = onBeatRef.current;
      if (!current || !callback) return;
      const index = nearestPeakIndex(current.beats, fs, xToSeconds(event.clientX));
      callback(index === null ? null : current.beats[index]);
    };

    plot.over.addEventListener("pointerdown", onPointerDown);
    plot.over.addEventListener("pointermove", onPointerMove);
    plot.over.addEventListener("pointerup", onPointerUp);
    plot.over.addEventListener("pointercancel", onPointerUp);
    plot.over.addEventListener("click", onClick);

    const setHover = (next: Pick<HoverTarget, "kind" | "key"> | null) => {
      const current = hoverRef.current;
      if (!next) {
        if (!current) return;
        hoverRef.current = null;
        plot.redraw(false);
        return;
      }
      if (current && current.kind === next.kind && current.key === next.key) return;
      hoverRef.current = { ...next, at: performance.now() };
      plot.redraw(false);
      animate(HOVER_RAMP_MS);
    };

    const onHoverMove = (event: PointerEvent) => {
      if (!interactive || dragging) return;
      const current = analysisRef.current;
      if (!current) return;
      const seconds = xToSeconds(event.clientX);
      const inRange = (start?: number | null, end?: number | null) =>
        start !== null &&
        start !== undefined &&
        end !== null &&
        end !== undefined &&
        seconds >= start &&
        seconds <= end;

      for (const segment of current.quality.segments ?? []) {
        if (segment.quality < 0.82 && inRange(segment.startSec, segment.endSec)) {
          setHover({ kind: "segment", key: `s:${segment.startSec}` });
          return;
        }
      }
      for (const warning of current.quality.warnings ?? []) {
        if (inRange(warning.startSec, warning.endSec)) {
          setHover({ kind: "warning", key: `w:${warning.startSec}` });
          return;
        }
      }

      const index = nearestPeakIndex(current.beats, fs, seconds);
      if (index !== null) {
        const x = plot.valToPos(current.beats[index].rPeakSample / fs, "x", true);
        if (Math.abs(x - (event.clientX - plot.over.getBoundingClientRect().left)) <= 8) {
          setHover({ kind: "beat", key: `b:${index}` });
          return;
        }
      }
      setHover(null);
    };
    const onHoverLeave = () => setHover(null);
    plot.over.addEventListener("pointermove", onHoverMove);
    plot.over.addEventListener("pointerleave", onHoverLeave);

    return () => {
      cancelAnimationFrame(frame);
      animateRef.current = null;
      plot.over.removeEventListener("wheel", onWheel);
      plot.over.removeEventListener("pointerdown", onPointerDown);
      plot.over.removeEventListener("pointermove", onPointerMove);
      plot.over.removeEventListener("pointerup", onPointerUp);
      plot.over.removeEventListener("pointercancel", onPointerUp);
      plot.over.removeEventListener("click", onClick);
      plot.over.removeEventListener("pointermove", onHoverMove);
      plot.over.removeEventListener("pointerleave", onHoverLeave);
      plot.destroy();
      plotRef.current = null;
    };
  }, [
    samples,
    fs,
    width,
    height,
    interactive,
    showHeader,
    showTimeAxis,
    showScale,
    isPrimary,
    unit,
    colors,
  ]);

  useEffect(() => {
    const plot = plotRef.current;
    if (!plot || !samples.length || fs <= 0) return;
    const [start, end] = view;
    const target = Math.max(200, Math.round(width * 2));
    const decimated = minMaxDecimate(samples, fs, start, end, target);
    plot.batch(() => {
      plot.setData([decimated.x, decimated.y]);
      plot.setScale("x", { min: start, max: end });
    });
  }, [view, samples, fs, width]);

  useEffect(() => {
    const index = selectedBeatIndex;
    if (index === null) {
      pulseRef.current = null;
    } else if (!pulseRef.current || pulseRef.current.index !== index) {
      pulseRef.current = { index, at: performance.now() };
    }
    plotRef.current?.redraw(false);
    if (index !== null) animateRef.current?.(PULSE_MS);
  }, [analysis, selectedBeatIndex, colors]);

  const unitLabel = unit || "mV";

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-md border border-border bg-surface",
        className,
      )}
      role="group"
      aria-label={
        ariaLabel ??
        `${lead} · ${unitLabel} · ${formatClock(duration)}`
      }
    >
      {showHeader ? (
        <div className="flex items-baseline justify-between gap-2 px-2 pt-1 text-[10px] leading-4">
          <span className="font-medium tracking-wide text-foreground">{lead}</span>
          <span className="eh-num text-muted-foreground">
            {unitLabel} · {fs.toFixed(0)} Hz
          </span>
        </div>
      ) : null}
      <div
        ref={containerRef}
        className="w-full"
        style={{ height }}
        aria-hidden="true"
      />
    </div>
  );
}
