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
 * 650k 点只在包络构建时扫一遍，拖动时不重算整段。
 */
export function OverviewStrip({
  envelope,
  duration,
  view,
  quality,
  onViewChange,
  height = 44,
  className,
  ariaLabel,
  hint,
}: OverviewStripProps) {
  const colors = useWaveColors();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [width, setWidth] = useState(0);
  const viewRef = useRef(view);
  viewRef.current = view;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      setWidth(next > 0 ? next : 0);
    });
    observer.observe(canvas);
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

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || width <= 0 || duration <= 0) return;
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

    ctx.save();
    ctx.fillStyle = colors.surface;
    ctx.fillRect(0, 0, width, height);

    // 质量区段底色
    for (const segment of quality?.segments ?? []) {
      if (segment.quality >= 0.82) continue;
      ctx.globalAlpha = 0.16;
      ctx.fillStyle = segment.quality < 0.7 ? colors.danger : colors.warning;
      const left = xFor(Math.max(0, segment.startSec));
      const right = xFor(Math.min(duration, segment.endSec));
      ctx.fillRect(left, 0, Math.max(1, right - left), height);
    }

    // min/max 包络
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = colors.signal;
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (envelope.buckets > 0) {
      for (let bucket = 0; bucket < envelope.buckets; bucket += 1) {
        const x = ((bucket + 0.5) / envelope.buckets) * width;
        ctx.moveTo(x, yFor(envelope.max[bucket]));
        ctx.lineTo(x, yFor(envelope.min[bucket]));
      }
    }
    ctx.stroke();

    // 视窗外部压暗、内部高亮
    const viewLeft = xFor(Math.max(0, view[0]));
    const viewRight = xFor(Math.min(duration, view[1]));
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = colors.text;
    ctx.fillRect(0, 0, Math.max(0, viewLeft), height);
    ctx.fillRect(viewRight, 0, Math.max(0, width - viewRight), height);
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = colors.accent;
    ctx.fillRect(viewLeft, 0, Math.max(1, viewRight - viewLeft), height);
    ctx.globalAlpha = 0.9;
    ctx.strokeStyle = colors.accent;
    ctx.lineWidth = 1;
    ctx.strokeRect(viewLeft + 0.5, 0.5, Math.max(1, viewRight - viewLeft - 1), height - 1);
    ctx.restore();
  }, [envelope, range, view, duration, width, height, quality, colors]);

  const timeAt = useCallback(
    (clientX: number) => {
      const canvas = canvasRef.current;
      if (!canvas || !duration) return 0;
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      return ratio * duration;
    },
    [duration],
  );

  const draggingRef = useRef<{ grab: number; span: number } | null>(null);

  const emit = useCallback(
    (start: number, span: number) => {
      onViewChange(clampView(start, start + span, duration));
    },
    [duration, onViewChange],
  );

  const onPointerDown = (event: PointerEvent<HTMLCanvasElement>) => {
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

  const onPointerMove = (event: PointerEvent<HTMLCanvasElement>) => {
    const drag = draggingRef.current;
    if (!drag) return;
    const time = timeAt(event.clientX);
    emit(time - drag.grab, drag.span);
  };

  const endDrag = (event: PointerEvent<HTMLCanvasElement>) => {
    draggingRef.current = null;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      // 忽略
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLCanvasElement>) => {
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
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="eh-caption text-muted-foreground">{hint}</span>
        <span className="eh-caption eh-num text-muted-foreground">
          {formatClock(view[0])} – {formatClock(view[1])}
        </span>
      </div>
      <canvas
        ref={canvasRef}
        className="block w-full cursor-pointer rounded-md border border-border touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        style={{ height }}
        role="slider"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(view[0])}
        aria-valuetext={`${formatClock(view[0])} – ${formatClock(view[1])}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onKeyDown}
      />
    </div>
  );
}
