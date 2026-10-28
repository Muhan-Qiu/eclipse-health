import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "cn";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface/60 px-6 py-12 text-center",
        className,
      )}
    >
      <div
        className="mb-4 flex size-11 items-center justify-center rounded-full bg-subtle text-muted-foreground"
        aria-hidden="true"
      >
        <Icon className="size-5" />
      </div>
      <h3 className="eh-h3">{title}</h3>
      <p className="eh-small mt-2 max-w-[48ch] text-muted-foreground">
        {description}
      </p>
      {children ? (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {children}
        </div>
      ) : null}
    </div>
  );
}
