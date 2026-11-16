import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "cn";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: ReactNode;
  className?: string;
  /** 紧凑横向排版：用于卡片内部，避免空状态占满整块卡片。 */
  compact?: boolean;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      data-empty-state
      data-compact={compact ? "true" : undefined}
      className={cn(
        "eh-fade-in rounded-xl border border-dashed border-border bg-surface/60",
        compact
          ? "flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 text-left"
          : "flex flex-col items-center justify-center px-6 py-12 text-center",
        className,
      )}
    >
      <div
        data-empty-icon
        className={cn(
          "flex shrink-0 items-center justify-center rounded-full bg-subtle text-muted-foreground",
          compact ? "size-9" : "mb-4 size-11",
        )}
        aria-hidden="true"
      >
        <Icon className={compact ? "size-4" : "size-5"} />
      </div>
      <div data-empty-body className={compact ? "min-w-0 flex-1" : "min-w-0"}>
        <h3 className={compact ? "text-sm leading-5 font-medium" : "eh-h3"}>
          {title}
        </h3>
        <p
          className={cn(
            "text-muted-foreground",
            compact
              ? "eh-caption mt-0.5"
              : "eh-small mt-2 max-w-[48ch] text-pretty",
          )}
        >
          {description}
        </p>
      </div>
      {children ? (
        <div
          data-empty-actions
          className={
            compact
              ? "flex shrink-0 flex-wrap items-center gap-2"
              : "mt-6 flex flex-wrap items-center justify-center gap-2"
          }
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
