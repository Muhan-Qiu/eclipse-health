import { cn } from "cn";

/**
 * 应用内日食标识：深色圆盘 + 两圈深绿光环。
 * 保持最初版本的两圈结构；loop 时只做缓慢呼吸，不做多圈扩散。
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
      viewBox="0 0 32 32"
      role="img"
      aria-label="eclipse health"
      className={cn("shrink-0", className)}
    >
      <g className={cn(loop && "eh-brand-mark__loop")}>
        <circle
          cx="16"
          cy="16"
          r="11"
          fill="none"
          stroke="var(--eh-signal)"
          strokeWidth="1.6"
          opacity="0.55"
          className={cn(loop && "eh-brand-mark__halo")}
        />
        <circle
          cx="16"
          cy="16"
          r="9.2"
          fill="none"
          stroke="var(--eh-signal)"
          strokeWidth="2"
        />
        <circle cx="16" cy="16" r="7.4" fill="var(--eh-logo-disk)" />
      </g>
    </svg>
  );
}
