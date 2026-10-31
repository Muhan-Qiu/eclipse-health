import { useMemo } from "react";
import { cn } from "cn";

const WIDTH = 120;
const HEIGHT = 32;

interface SparklineProps {
  values: number[];
  ariaLabel: string;
  className?: string;
}

export function Sparkline({ values, ariaLabel, className }: SparklineProps) {
  const points = useMemo(() => {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    return values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * WIDTH;
        const y = HEIGHT - 3 - ((value - min) / range) * (HEIGHT - 6);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [values]);

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className={cn("h-8 w-30", className)}
    >
      <polyline
        points={points}
        pathLength={1}
        fill="none"
        stroke="var(--eh-signal)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        className="eh-sparkline__line"
      />
    </svg>
  );
}
