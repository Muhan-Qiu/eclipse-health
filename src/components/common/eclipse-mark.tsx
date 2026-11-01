import { cn } from "cn";

/** 4 圈同心圆环；半径 / 线宽在同一 128 视口内，缩放时保持比例。 */
const RINGS = [
  { r: 46, width: 4.6, opacity: 1 },
  { r: 33, width: 3.8, opacity: 0.9 },
  { r: 21, width: 3.2, opacity: 0.8 },
  { r: 10, width: 2.6, opacity: 0.7 },
] as const;

/**
 * 深绿涟漪标识：同心圆环由外向内收，像水波回收。
 * loop 为 true 时常驻慢速循环（10s），由 branding.css 驱动，减少动效时静止。
 */
export function EclipseMark({
  className,
  loop = false,
}: {
  className?: string;
  loop?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 128 128"
      role="img"
      aria-label="eclipse health"
      className={cn("eh-brand-mark", "shrink-0", className)}
    >
      <g className={cn("eh-brand-ripple", loop && "eh-brand-ripple--loop")}>
        {RINGS.map((ring) => (
          <circle
            key={ring.r}
            className="eh-brand-ripple__ring"
            cx="64"
            cy="64"
            r={ring.r}
            fill="none"
            stroke="var(--eh-brand-ripple)"
            strokeWidth={ring.width}
            strokeOpacity={ring.opacity}
          />
        ))}
        <circle
          className="eh-brand-ripple__core"
          cx="64"
          cy="64"
          r="5.5"
          fill="var(--eh-brand-ripple)"
        />
      </g>
    </svg>
  );
}
