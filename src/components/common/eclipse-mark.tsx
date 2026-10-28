import { cn } from "cn";

/**
 * 日食标识：深墨圆盘 + 一圈暖色光环。
 * 正式 logo 与四个版本在 B2 完成，这里是占位实现。
 */
export function EclipseMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label="eclipse health"
      className={cn("shrink-0", className)}
    >
      <circle
        cx="16"
        cy="16"
        r="11"
        fill="none"
        stroke="var(--eh-logo-ring)"
        strokeWidth="1.4"
        opacity="0.55"
      />
      <circle
        cx="16"
        cy="16"
        r="9.2"
        fill="none"
        stroke="var(--eh-logo-ring)"
        strokeWidth="1.8"
      />
      <circle cx="16" cy="16" r="7.4" fill="var(--eh-logo-disk)" />
    </svg>
  );
}
