import type { Beat, Quality } from "@/lib/api/types";
import { beatRange, formatClock, minMaxDecimate } from "@/lib/waveform";
import type { WaveColors } from "@/features/waveform/colors";

export interface PngLead {
  lead: string;
  unit: string;
  samples: Float32Array;
  fs: number;
}

export interface PngLabels {
  title: string;
  date: string;
  meta: string;
  watermark: string;
  duration: string;
  layout: string;
}

export interface WaveformPngOptions {
  leads: PngLead[];
  view: [number, number];
  duration: number;
  layout: "single" | "grid";
  recordDate: string;
  beats?: Beat[];
  selectedBeatIndex?: number | null;
  quality?: Quality | null;
  labels: PngLabels;
  colors: WaveColors;
  filename: string;
}

const FONT_STACK =
  '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif';
const MONO_STACK = '"Cascadia Mono", "JetBrains Mono", ui-monospace, monospace';

function niceStep(span: number, target = 8): number {
  if (!Number.isFinite(span) || span <= 0) return 1;
  const raw = span / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / power;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * power;
}

function drawText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  font: string,
  color: string,
  align: CanvasTextAlign = "left",
) {
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(text, x, y);
}

function drawLead(
  ctx: CanvasRenderingContext2D,
  lead: PngLead,
  box: { x: number; y: number; w: number; h: number },
  options: WaveformPngOptions,
  colors: WaveColors,
  showTimeAxis: boolean,
) {
  const { view, beats = [], selectedBeatIndex = null, quality } = options;
  const [start, end] = view;
  const plotX = box.x + 10;
  const plotY = box.y + 24;
  const plotW = Math.max(20, box.w - 20);
  const plotH = Math.max(20, box.h - 34);

  ctx.save();
  ctx.fillStyle = colors.surface;
  ctx.fillRect(box.x, box.y, box.w, box.h);
  ctx.strokeStyle = colors.border;
  ctx.lineWidth = 1;
  ctx.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);

  drawText(
    ctx,
    lead.lead,
    box.x + 10,
    box.y + 16,
    `600 12px ${FONT_STACK}`,
    colors.text,
  );
  drawText(
    ctx,
    `${lead.unit || "mV"} · ${lead.fs.toFixed(0)} Hz`,
    box.x + box.w - 10,
    box.y + 16,
    `11px ${MONO_STACK}`,
    colors.muted,
    "right",
  );

  const decimated = minMaxDecimate(lead.samples, lead.fs, start, end, plotW * 2);
  let yMin = Number.POSITIVE_INFINITY;
  let yMax = Number.NEGATIVE_INFINITY;
  for (const value of decimated.y) {
    if (value < yMin) yMin = value;
    if (value > yMax) yMax = value;
  }
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMin === yMax) {
    yMin -= 0.5;
    yMax += 0.5;
  }
  const pad = (yMax - yMin) * 0.12;
  yMin -= pad;
  yMax += pad;
  const yRange = yMax - yMin || 1;
  const toX = (seconds: number) => plotX + ((seconds - start) / (end - start || 1)) * plotW;
  const toY = (value: number) => plotY + (1 - (value - yMin) / yRange) * plotH;

  ctx.beginPath();
  ctx.rect(plotX, plotY, plotW, plotH);
  ctx.clip();

  // 质量区段底色
  for (const segment of quality?.segments ?? []) {
    if (segment.quality >= 0.82) continue;
    if (segment.endSec <= start || segment.startSec >= end) continue;
    ctx.globalAlpha = 0.14;
    ctx.fillStyle = segment.quality < 0.7 ? colors.danger : colors.warning;
    const left = Math.max(plotX, toX(segment.startSec));
    const right = Math.min(plotX + plotW, toX(segment.endSec));
    ctx.fillRect(left, plotY, Math.max(1, right - left), plotH);
  }
  ctx.globalAlpha = 1;

  // 网格
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  const step = niceStep(end - start, 8);
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) {
    const x = toX(t);
    ctx.beginPath();
    ctx.moveTo(x, plotY);
    ctx.lineTo(x, plotY + plotH);
    ctx.stroke();
  }
  for (let i = 0; i <= 4; i += 1) {
    const y = plotY + (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(plotX, y);
    ctx.lineTo(plotX + plotW, y);
    ctx.stroke();
  }

  // R 峰
  if (beats.length) {
    const [from, to] = beatRange(beats, lead.fs, start, end);
    for (let index = from; index < to; index += 1) {
      const beat = beats[index];
      const x = toX(beat.rPeakSample / lead.fs);
      const selected = selectedBeatIndex === index;
      ctx.globalAlpha = selected ? 0.95 : beat.label === "N" ? 0.28 : 0.55;
      ctx.strokeStyle = selected
        ? colors.accent
        : beat.label === "N"
          ? colors.signal
          : colors.warning;
      ctx.lineWidth = selected ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(x, plotY);
      ctx.lineTo(x, plotY + plotH);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // 波形
  ctx.strokeStyle = colors.signal;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  for (let index = 0; index < decimated.x.length; index += 1) {
    const x = toX(decimated.x[index]);
    const y = toY(decimated.y[index]);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // 标尺
  const mvSpan = yRange <= 1.5 ? 0.5 : yRange <= 4 ? 1 : yRange <= 10 ? 2 : 5;
  let mvPx = (mvSpan / yRange) * plotH;
  let mvLabel = mvSpan;
  if (mvPx > plotH * 0.7) {
    mvPx /= 2;
    mvLabel /= 2;
  }
  const secPx = (0.2 / (end - start || 1)) * plotW;
  const barX = plotX + 12;
  const barY = plotY + plotH - 10;
  ctx.globalAlpha = 0.85;
  ctx.strokeStyle = colors.muted;
  ctx.fillStyle = colors.muted;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(barX, barY - mvPx);
  ctx.lineTo(barX, barY);
  ctx.lineTo(barX + secPx, barY);
  ctx.stroke();
  drawText(ctx, `${mvLabel} ${lead.unit || "mV"}`, barX + 3, barY - mvPx + 4, `9px ${MONO_STACK}`, colors.muted);
  drawText(ctx, "0.2 s", barX + secPx + 3, barY - 4, `9px ${MONO_STACK}`, colors.muted);

  ctx.restore();

  // 时间刻度（在裁剪区外，避免被 plot 高度截断）；边缘标签对齐到格子内侧
  if (showTimeAxis) {
    ctx.save();
    for (let t = Math.ceil(start / step) * step; t <= end; t += step) {
      const edgeLeft = t - start < step * 0.05;
      const edgeRight = end - t < step * 0.05;
      const x = edgeLeft ? toX(t) + 2 : edgeRight ? toX(t) - 2 : toX(t);
      drawText(
        ctx,
        formatClock(t),
        x,
        plotY + plotH + 14,
        `10px ${MONO_STACK}`,
        colors.muted,
        edgeLeft ? "left" : edgeRight ? "right" : "center",
      );
    }
    ctx.restore();
  }
}

/**
 * 前端 Canvas 生成波形 PNG（B7）：不依赖后端，包含导联/采样率/时间范围、
 * 记录日期与非诊断水印。12 导联网格导出时按当前布局绘制全部导联。
 */
export function renderWaveformPng(options: WaveformPngOptions): HTMLCanvasElement {
  const { leads, layout, labels, colors, recordDate, view, duration } = options;
  const multi = layout === "grid" && leads.length > 1;
  const cols = !multi ? 1 : leads.length <= 2 ? 1 : leads.length <= 4 ? 2 : 3;
  const rows = Math.max(1, Math.ceil(leads.length / cols));
  const width = multi ? 1800 : 1600;
  const cellH = multi ? 138 : 620;
  const headerH = 96;
  const footerH = 76;
  const gap = 12;
  const height = headerH + rows * cellH + (rows - 1) * gap + footerH;

  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas;
  ctx.scale(scale, scale);

  ctx.fillStyle = colors.background;
  ctx.fillRect(0, 0, width, height);

  const margin = 40;
  drawText(ctx, labels.title, margin, 46, `600 26px ${FONT_STACK}`, colors.text);
  drawText(
    ctx,
    `${recordDate} · ${labels.layout}`,
    margin,
    70,
    `13px ${FONT_STACK}`,
    colors.muted,
  );
  drawText(
    ctx,
    `${formatClock(view[0])} – ${formatClock(view[1])} · ${duration.toFixed(1)} s`,
    width - margin,
    46,
    `13px ${MONO_STACK}`,
    colors.muted,
    "right",
  );

  const contentW = width - margin * 2;
  const colW = (contentW - gap * (cols - 1)) / cols;
  const visible = multi ? leads : leads.slice(0, 1);
  visible.forEach((lead, index) => {
    const row = Math.floor(index / cols);
    const col = index % cols;
    drawLead(
      ctx,
      lead,
      {
        x: margin + col * (colW + gap),
        y: headerH + row * (cellH + gap),
        w: colW,
        h: cellH,
      },
      options,
      colors,
      !multi || row === rows - 1,
    );
  });

  // 非诊断水印：斜向低透明度 + 页脚明示
  const plotTop = headerH;
  const plotBottom = headerH + rows * cellH + (rows - 1) * gap;
  ctx.save();
  ctx.translate(width / 2, (plotTop + plotBottom) / 2);
  ctx.rotate((-18 * Math.PI) / 180);
  ctx.globalAlpha = 0.08;
  ctx.fillStyle = colors.danger;
  ctx.font = `700 44px ${FONT_STACK}`;
  ctx.textAlign = "center";
  ctx.fillText(labels.watermark, 0, 0);
  ctx.restore();

  drawText(
    ctx,
    labels.watermark,
    margin,
    height - 34,
    `12px ${FONT_STACK}`,
    colors.danger,
  );
  drawText(
    ctx,
    `${labels.date} · ${labels.duration} · ${labels.meta}`,
    margin,
    height - 16,
    `11px ${MONO_STACK}`,
    colors.muted,
  );
  return canvas;
}

export async function exportWaveformPng(options: WaveformPngOptions): Promise<void> {
  const canvas = renderWaveformPng(options);
  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((value) => resolve(value), "image/png");
  });
  if (!blob) throw new Error("png_export_failed");
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = options.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_500);
}
