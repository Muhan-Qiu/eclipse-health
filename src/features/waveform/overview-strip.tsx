import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { cn } from "cn";
import type { Quality } from "@/lib/api/types";
import { clampView, formatClock, type WaveEnvelope } from "@/lib/waveform";
import { useWaveColors } from "@/features/waveform/colors";

export interface OverviewStripProps {
  envelope: WaveEnvelope;
  duration: number;
  view: [number, number];
  quality?: Quality | null;
  onViewChange: (view: [number, number]) => void;
  height?: number;
  className?: string;
  ariaLabel?: string;
  hint?: string;
}

/**
 * 整段记录节律条（B6）：预计算包络 + 当前视窗高亮，点击/拖动跳转。
 *
 * 两层画布：底层（包络、基线、质量区段）只在尺寸/数据变化时重绘，
 * 顶层只画视窗遮罩与手柄。拖动时不再重扫 650k 点或重画整段包络。
 */
export function OverviewStrip({
  envelope,
  duration,
  view,
  quality,
  onViewChange,
  height = 60,
  className,
  ariaLabel,
  hint,
}: OverviewStripProps) {
  const colors = useWaveColors();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const baseRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const [width, setWidth] = useState(0);
  const viewRef = useRef(view);
  viewRef.current = view;

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      setWidth(next > 0 ? next : 0);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const range = useMemo(() => {
    if (!envelope.buckets) return { min: 0, max: 1 };
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (let index = 0; index < envelope.buckets; index += 1) {
      if (envelope.min[index] < min) min = envelope.min[index];
      if (envelope.max[index] > max) max = envelope.max[index];
    }
    if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
      return { min: min - 0.5, max: max + 0.5 };
    }
    const pad = (max - min) * 0.12;
    return { min: min - pad, max: max + pad };
  }, [envelope]);

  /** 底层：对称 min/max 包络填充 + 中心基线 + 低饱和质量底色。 */
  useEffect(() => {
    const canvas = baseRef.current;
    if (!canvas || width <= 0 || height <= 0 || duration <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const span = range.max - range.min || 1;
    const yFor = (value: number) =>
      2 + (height - 4) * (1 - (value - range.min) / span);
    const xFor = (seconds: number) =>
      duration > 0 ? (seconds / duration) * width : 0;

    ctx.fillStyle = colors.surface;
    ctx.fillRect(0, 0, width, height);

    // 质量较差区段：低饱和底色，不遮挡波形包络。
    for (const segment of quality?.segments ?? []) {
      if (segment.quality >= 0.82) continue;
      const left = xFor(Math.max(0, segment.startSec));
      const right = xFor(Math.min(duration, segment.endSec));
      if (right <= left) continue;
      ctx.globalAlpha = segment.quality < 0.7 ? 0.13 : 0.09;
      ctx.fillStyle = segment.quality < 0.7 ? colors.danger : colors.warning;
      ctx.fillRect(left, 0, Math.max(1, right - left), height);
    }

    // 中心基线：比包络更细、更浅，给整条带一个参考零点。
    const baselineValue = Math.min(range.max, Math.max(range.min, 0));
    const baselineY = Math.round(yFor(baselineValue)) + 0.5;
    ctx.save();
    ctx.globalAlpha = 0.55;
    ctx.strokeStyle = colors.border;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(0, baselineY);
    ctx.lineTo(width, baselineY);
    ctx.stroke();
    ctx.restore();

    // 把 2000 个桶聚合成一列一像素，再填充 max→min 的对称包络。
    if (envelope.buckets > 0) {
      const buckets = envelope.buckets;
      const columns = Math.max(1, Math.min(buckets, Math.round(width)));
      const xs = new Float32Array(columns);
      const upper = new Float32Array(columns);
      const lower = new Float32Array(columns);
      for (let column = 0; column < columns; column += 1) {
        const from = Math.floor((column * buckets) / columns);
        const to = Math.max(
          from + 1,
          Math.floor(((column + 1) * buckets) / columns),
        );
        let low = Number.POSITIVE_INFINITY;
        let high = Number.NEGATIVE_INFINITY;
        for (let bucket = from; bucket < to; bucket += 1) {
          if (envelope.min[bucket] < low) low = envelope.min[bucket];
          if (envelope.max[bucket] > high) high = envelope.max[bucket];
        }
        xs[column] = ((column + 0.5) / columns) * width;
        upper[column] = yFor(high);
        lower[column] = yFor(low);
      }

      ctx.beginPath();
      ctx.moveTo(xs[0], upper[0]);
      for (let column = 1; column < columns; column += 1) {
        ctx.lineTo(xs[column], upper[column]);
      }
      for (let column = columns - 1; column >= 0; column -= 1) {
        ctx.lineTo(xs[column], lower[column]);
      }
      ctx.closePath();
      ctx.globalAlpha = 0.2;
      ctx.fillStyle = colors.signal;
      ctx.fill();

      ctx.globalAlpha = 0.55;
      ctx.strokeStyle = colors.signal;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(xs[0], upper[0]);
      for (let column = 1; column < columns; column += 1) {
        ctx.lineTo(xs[column], upper[column]);
      }
      ctx.moveTo(xs[0], lower[0]);
      for (let column = 1; column < columns; column += 1) {
        ctx.lineTo(xs[column], lower[column]);
      }
      ctx.stroke();
    }
  }, [envelope, range, duration, width, height, quality, colors]);

  /** 顶层：视窗遮罩 / 高亮 / 手柄。拖动时只重绘这一层。 */
  useEffect(() => {
    const canvas = overlayRef.current;
    if (!canvas || width <= 0 || height <= 0 || duration <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const xFor = (seconds: number) =>
      duration > 0 ? (seconds / duration) * width : 0;
    const left = Math.max(0, Math.min(width, xFor(view[0])));
    const right = Math.max(left, Math.min(width, xFor(view[1])));
    const visible = Math.max(2, right - left);

    // 视窗外压暗，视窗内浅色 accent 提亮。
    if (left > 0) {
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = colors.text;
      ctx.fillRect(0, 0, left, height);
    }
    if (right < width) {
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = colors.text;
      ctx.fillRect(right, 0, width - right, height);
    }
    ctx.globalAlpha = 0.09;
    ctx.fillStyle = colors.accent;
    ctx.fillRect(left, 0, visible, height);

    // 上下细线 + 两侧手柄，让当前视窗边界一眼可见。
    ctx.globalAlpha = 0.45;
    ctx.fillRect(left, 0, visible, 1);
    ctx.fillRect(left, height - 1, visible, 1);
    ctx.globalAlpha = 0.9;
    ctx.fillRect(left, 0, 2, height);
    ctx.fillRect(Math.max(left + 2, right - 2), 0, 2, height);

    // 视窗顶部中央的小握柄，暗示可拖动。
    const gripWidth = Math.min(18, Math.max(8, visible - 8));
    if (visible >= 24) {
      ctx.globalAlpha = 0.7;
      ctx.fillRect(left + visible / 2 - gripWidth / 2, 1, gripWidth, 2);
    }
  }, [view, width, height, duration, colors]);

  const timeAt = useCallback((clientX: number) => {
    const element = wrapRef.current;
    if (!element || !duration) return 0;
    const rect = element.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return ratio * duration;
  }, [duration]);

  const draggingRef = useRef<{ grab: number; span: number } | null>(null);

  const emit = useCallback(
    (start: number, span: number) => {
      onViewChange(clampView(start, start + span, duration));
    },
    [duration, onViewChange],
  );

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const time = timeAt(event.clientX);
    const [start, end] = viewRef.current;
    const inside = time >= start && time <= end;
    const span = Math.max(0.2, end - start);
    draggingRef.current = { grab: inside ? time - start : span / 2, span };
    if (!inside) emit(time - span / 2, span);
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // 忽略指针捕获失败
    }
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const drag = draggingRef.current;
    if (!drag) return;
    const time = timeAt(event.clientX);
    emit(time - drag.grab, drag.span);
  };

  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    draggingRef.current = null;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      // 忽略
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const [start, end] = viewRef.current;
    const span = end - start;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      emit(start - span * 0.1, span);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      emit(start + span * 0.1, span);
    } else if (event.key === "PageUp") {
      event.preventDefault();
      emit(start - span * 0.5, span);
    } else if (event.key === "PageDown") {
      event.preventDefault();
      emit(start + span * 0.5, span);
    } else if (event.key === "Home") {
      event.preventDefault();
      emit(0, span);
    } else if (event.key === "End") {
      event.preventDefault();
      emit(duration - span, span);
    }
  };

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="eh-caption truncate text-muted-foreground">{hint}</span>
        <span className="eh-caption eh-num shrink-0 text-muted-foreground">
          {formatClock(view[0])} – {formatClock(view[1])}
        </span>
      </div>
      <div
        ref={wrapRef}
        className="group relative w-full cursor-grab touch-none overflow-hidden rounded-lg border border-border bg-surface transition-[border-color,box-shadow] duration-150 select-none hover:border-accent/60 hover:shadow-[0_0_0_1px_var(--eh-accent-soft)] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none active:cursor-grabbing"
        style={{ height }}
        role="slider"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-orientation="horizontal"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(view[0])}
        aria-valuetext={`${formatClock(view[0])} – ${formatClock(view[1])}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onKeyDown}
      >
        <canvas
          ref={baseRef}
          className="pointer-events-none absolute inset-0 block size-full"
          aria-hidden="true"
        />
        <canvas
          ref={overlayRef}
          className="pointer-events-none absolute inset-0 block size-full"
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
