export interface DecimatedSeries {
  x: number[];
  y: number[];
}

export interface WaveEnvelope {
  /** 每个桶的最小值，长度 = buckets。 */
  min: Float32Array;
  /** 每个桶的最大值，长度 = buckets。 */
  max: Float32Array;
  buckets: number;
  duration: number;
  bucketSec: number;
}

/**
 * 整段记录的 min/max 包络，供节律条一次性预计算。
 * 650k 点只扫一遍；之后拖动视图不再重算整段。
 */
export function buildEnvelope(
  samples: Float32Array,
  fs: number,
  bucketCount = 2_000,
): WaveEnvelope {
  if (!samples.length) {
    return {
      min: new Float32Array(0),
      max: new Float32Array(0),
      buckets: 0,
      duration: 0,
      bucketSec: 0,
    };
  }
  const buckets = Math.max(1, Math.min(Math.trunc(bucketCount), samples.length));
  const min = new Float32Array(buckets);
  const max = new Float32Array(buckets);
  const bucketSize = samples.length / buckets;
  for (let bucket = 0; bucket < buckets; bucket += 1) {
    const start = Math.floor(bucket * bucketSize);
    const end = Math.max(start + 1, Math.min(samples.length, Math.floor((bucket + 1) * bucketSize)));
    let lo = samples[start];
    let hi = samples[start];
    for (let index = start + 1; index < end; index += 1) {
      const value = samples[index];
      if (value < lo) lo = value;
      if (value > hi) hi = value;
    }
    min[bucket] = lo;
    max[bucket] = hi;
  }
  return {
    min,
    max,
    buckets,
    duration: fs > 0 ? samples.length / fs : 0,
    bucketSec: fs > 0 ? bucketSize / fs : 0,
  };
}

export type QualityLevel = "good" | "fair" | "poor";

/** 与波形底色、图例、区段列表共用同一阈值（B4-05）。 */
export function qualityLevel(quality: number): QualityLevel {
  if (quality < 0.7) return "poor";
  if (quality < 0.82) return "fair";
  return "good";
}

/** 二分查找落在 [startSec, endSec] 内的 R 峰区间（beats 必须按 rPeakSample 升序）。 */
export function beatRange(
  beats: { rPeakSample: number }[],
  fs: number,
  startSec: number,
  endSec: number,
): [number, number] {
  if (!beats.length || fs <= 0) return [0, 0];
  const lower = Math.floor(startSec * fs);
  const upper = Math.ceil(endSec * fs);
  let left = 0;
  let right = beats.length;
  while (left < right) {
    const mid = (left + right) >> 1;
    if (beats[mid].rPeakSample < lower) left = mid + 1;
    else right = mid;
  }
  const first = left;
  left = first;
  right = beats.length;
  while (left < right) {
    const mid = (left + right) >> 1;
    if (beats[mid].rPeakSample <= upper) left = mid + 1;
    else right = mid;
  }
  return [first, left];
}

/**
 * 按像素桶取 min/max：既能保留 R 峰尖峰，也把 65 万点压到约 2×像素数。
 * 返回的点按时间顺序排列，x 为秒。
 */
export function minMaxDecimate(
  samples: Float32Array,
  fs: number,
  startSec: number,
  endSec: number,
  targetPoints: number,
): DecimatedSeries {
  if (!samples.length || fs <= 0) return { x: [], y: [] };
  const duration = samples.length / fs;
  const start = Math.max(0, Math.min(startSec, duration));
  const end = Math.max(start, Math.min(endSec, duration));
  const first = Math.max(0, Math.floor(start * fs));
  const last = Math.min(samples.length, Math.max(first + 1, Math.ceil(end * fs)));
  const count = last - first;
  if (count <= 0) return { x: [], y: [] };

  const buckets = Math.max(1, Math.floor(targetPoints / 2));
  if (count <= buckets) {
    const x: number[] = [];
    const y: number[] = [];
    for (let index = first; index < last; index += 1) {
      x.push(index / fs);
      y.push(samples[index]);
    }
    return { x, y };
  }

  const bucketSize = count / buckets;
  const x: number[] = [];
  const y: number[] = [];
  for (let bucket = 0; bucket < buckets; bucket += 1) {
    const bucketStart = first + Math.floor(bucket * bucketSize);
    const bucketEnd = Math.min(
      last,
      first + Math.floor((bucket + 1) * bucketSize),
    );
    if (bucketEnd <= bucketStart) continue;
    let minIndex = bucketStart;
    let maxIndex = bucketStart;
    let minValue = samples[bucketStart];
    let maxValue = samples[bucketStart];
    for (let index = bucketStart + 1; index < bucketEnd; index += 1) {
      const value = samples[index];
      if (value < minValue) {
        minValue = value;
        minIndex = index;
      }
      if (value > maxValue) {
        maxValue = value;
        maxIndex = index;
      }
    }
    if (minIndex <= maxIndex) {
      x.push(minIndex / fs, maxIndex / fs);
      y.push(minValue, maxValue);
    } else {
      x.push(maxIndex / fs, minIndex / fs);
      y.push(maxValue, minValue);
    }
  }
  return { x, y };
}

export function clampView(
  startSec: number,
  endSec: number,
  duration: number,
  minSpan = 0.2,
): [number, number] {
  const safeDuration = Math.max(duration, minSpan);
  const span = Math.min(
    safeDuration,
    Math.max(minSpan, Math.min(endSec - startSec, safeDuration)),
  );
  const start = Math.max(0, Math.min(startSec, safeDuration - span));
  return [start, start + span];
}

export function formatSeconds(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value < 1) return `${value.toFixed(3)} s`;
  if (value < 60) return `${value.toFixed(2)} s`;
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return `${minutes}:${seconds.toFixed(1).padStart(4, "0")}`;
}

export function formatClock(seconds: number): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

/** 找到离点击秒数最近的 R 峰（二分查找，限定容差避免误选）。 */
export function nearestPeakIndex(
  peaks: { rPeakSample: number }[],
  fs: number,
  seconds: number,
  toleranceSec = 0.12,
): number | null {
  if (!peaks.length || fs <= 0) return null;
  const target = seconds * fs;
  let left = 0;
  let right = peaks.length - 1;
  while (left < right) {
    const mid = (left + right) >> 1;
    if (peaks[mid].rPeakSample < target) left = mid + 1;
    else right = mid;
  }
  let best = left;
  if (left > 0) {
    const prev = left - 1;
    if (
      Math.abs(peaks[prev].rPeakSample - target) <=
      Math.abs(peaks[best].rPeakSample - target)
    ) {
      best = prev;
    }
  }
  const distance = Math.abs(peaks[best].rPeakSample / fs - seconds);
  return distance <= toleranceSec ? best : null;
}
