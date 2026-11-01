import { useMemo } from "react";

/** 与模块 widget 视图一致的轻量 SVG 图表；不引第三方图表库。 */

const CHART_WIDTH = 240;
const CHART_HEIGHT = 72;

export function MiniLineChart({
  values,
  color,
  ariaLabel,
}: {
  values: number[];
  color: string;
  ariaLabel: string;
}) {
  const points = useMemo(() => {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const padding = 4;
    return values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * CHART_WIDTH;
        const y =
          CHART_HEIGHT -
          padding -
          ((value - min) / span) * (CHART_HEIGHT - padding * 2);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [values]);

  return (
    <svg
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className="h-16 w-full"
    >
      <polyline
        points={points}
        pathLength={1}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function MiniBarChart({
  values,
  color,
  ariaLabel,
}: {
  values: number[];
  color: string;
  ariaLabel: string;
}) {
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const span = max - min || 1;
  const zeroY = CHART_HEIGHT - ((0 - min) / span) * CHART_HEIGHT;
  const slot = CHART_WIDTH / Math.max(values.length, 1);
  const barWidth = Math.max(slot * 0.62, 1);

  return (
    <svg
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className="h-16 w-full"
    >
      {values.map((value, index) => {
        const y = CHART_HEIGHT - ((value - min) / span) * CHART_HEIGHT;
        const top = Math.min(y, zeroY);
        const height = Math.max(Math.abs(zeroY - y), value === 0 ? 0 : 1);
        return (
          <rect
            key={index}
            x={(index * slot + (slot - barWidth) / 2).toFixed(2)}
            y={top.toFixed(2)}
            width={barWidth.toFixed(2)}
            height={height.toFixed(2)}
            rx={1}
            fill={color}
            opacity={0.85}
          />
        );
      })}
      <line
        x1={0}
        x2={CHART_WIDTH}
        y1={zeroY}
        y2={zeroY}
        stroke="var(--eh-grid-line)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
