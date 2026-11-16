import type { ReactNode } from "react";
import { cn } from "cn";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "mb-8 flex flex-col gap-4 desk:flex-row desk:items-end desk:justify-between desk:gap-8",
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        {eyebrow ? (
          <p className="eh-caption tracking-[0.14em] text-muted-foreground uppercase">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="eh-h1 mt-1.5 text-balance">{title}</h1>
        {description ? (
          <p className="eh-small mt-2 max-w-[72ch] text-pretty text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2 desk:justify-end">
          {actions}
        </div>
      ) : null}
    </header>
  );
}
