import { useMemo } from "react";
import { cn } from "cn";

const VIEW_WIDTH = 640;
const VIEW_HEIGHT = 160;
const BEATS = 6;
const SAMPLES_PER_BEAT = 120;

function gaussian(x: number, mu: number, sigma: number, amplitude: number) {
  const d = x - mu;
  return amplitude * Math.exp(-(d * d) / (2 * sigma * sigma));
}

/** 合成 PQRST 波形：确定性生成，不含任何真实记录。 */
function buildEcgPath(): string {
  const mid = VIEW_HEIGHT / 2;
  const amplitude = VIEW_HEIGHT * 0.34;
  const total = BEATS * SAMPLES_PER_BEAT;
  const points: string[] = [];

  for (let i = 0; i <= total; i += 1) {
    const phase = (i % SAMPLES_PER_BEAT) / SAMPLES_PER_BEAT;
    const wander = 0.012 * Math.sin((i / total) * Math.PI * 2 * 0.7);
    const value =
      gaussian(phase, 0.18, 0.022, 0.1) +
      gaussian(phase, 0.3, 0.009, 0.95) -
      gaussian(phase, 0.335, 0.012, 0.2) +
      gaussian(phase, 0.55, 0.045, 0.22) -
      gaussian(phase, 0.265, 0.01, 0.08) +
      wander;
    const x = (i / total) * VIEW_WIDTH;
    const y = mid - value * amplitude;
    points.push(`${x.toFixed(2)},${y.toFixed(2)}`);
  }

  return `M${points.join(" L")}`;
}

const GRID_X = Array.from({ length: 17 }, (_, index) => index * 40);
const GRID_Y = Array.from({ length: 5 }, (_, index) => index * 40);

interface WaveThumbnailProps {
  ariaLabel: string;
  className?: string;
}

export function WaveThumbnail({ ariaLabel, className }: WaveThumbnailProps) {
  const path = useMemo(buildEcgPath, []);

  return (
    <svg
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className={cn("eh-wave-grid h-32 w-full", className)}
    >
      {GRID_X.map((x) => (
        <line key={`x-${x}`} x1={x} y1={0} x2={x} y2={VIEW_HEIGHT} />
      ))}
      {GRID_Y.map((y) => (
        <line key={`y-${y}`} x1={0} y1={y} x2={VIEW_WIDTH} y2={y} />
      ))}
      <path
        d={path}
        fill="none"
        stroke="var(--eh-signal)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
