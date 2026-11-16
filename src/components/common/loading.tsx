import { Skeleton } from "@/components/ui/skeleton";

/** 列表加载骨架（A5）。 */
export function RecordListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="eh-fade-in divide-y divide-border" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex min-w-0 items-center gap-3 px-5 py-3">
          <Skeleton className="size-9 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-40 max-w-full" />
            <Skeleton className="h-3 w-64 max-w-full" />
          </div>
          <Skeleton className="hidden h-3 w-16 shrink-0 sm:block" />
          <Skeleton className="hidden h-7 w-16 shrink-0 rounded-lg sm:block" />
          <Skeleton className="size-8 shrink-0 rounded-md" />
        </div>
      ))}
    </div>
  );
}
