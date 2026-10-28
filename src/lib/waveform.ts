export interface DecimatedSeries {
  x: number[];
  y: number[];
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

/** 找到离点击秒数最近的 R 峰（限定容差，避免误选）。 */
export function nearestPeakIndex(
  peaks: { rPeakSample: number }[],
  fs: number,
  seconds: number,
  toleranceSec = 0.12,
): number | null {
  if (!peaks.length || fs <= 0) return null;
  let best = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < peaks.length; index += 1) {
    const distance = Math.abs(peaks[index].rPeakSample / fs - seconds);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  }
  return bestDistance <= toleranceSec ? best : null;
}
