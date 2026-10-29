import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/common/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import type { LatestAnalysisStatus, RecordSummary } from "@/lib/api/types";
import { formatDateTime, formatDuration } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";

const STATUS_STYLES: Record<
  LatestAnalysisStatus,
  { className: string; Icon: typeof CheckCircle2 }
> = {
  completed: {
    className: "border-success/30 bg-success/10 text-success",
    Icon: CheckCircle2,
  },
  queued: {
    className: "border-info/30 bg-info/10 text-info",
    Icon: CircleDashed,
  },
  running: {
    className: "border-info/30 bg-info/10 text-info",
    Icon: Loader2,
  },
  failed: {
    className: "border-danger/30 bg-danger/10 text-danger",
    Icon: AlertCircle,
  },
  none: {
    className: "border-border text-muted-foreground",
    Icon: CircleDashed,
  },
};

export function AnalysisStatusBadge({ status }: { status: LatestAnalysisStatus }) {
  const { t } = useTranslation();
  const { className, Icon } = STATUS_STYLES[status] ?? STATUS_STYLES.none;
  return (
    <Badge variant="outline" className={cn("gap-1 font-normal", className)}>
      <Icon
        data-icon="inline-start"
        className={status === "running" ? "animate-spin" : undefined}
      />
      {t(`reports.composer.analysisStatus.${status}`, {
        defaultValue: status,
      })}
    </Badge>
  );
}

interface RecordPickerProps {
  records: RecordSummary[];
  total: number;
  selectedId: string | null;
  onSelect: (recordId: string) => void;
  search: string;
  onSearch: (value: string) => void;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

export function RecordPicker({
  records,
  total,
  selectedId,
  onSelect,
  search,
  onSearch,
  isLoading,
  isError,
  onRetry,
}: RecordPickerProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);

  return (
    <section aria-labelledby="report-record-heading" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="report-record-heading" className="text-sm font-medium">
          {t("reports.composer.record")}
        </h3>
        <span className="eh-caption text-muted-foreground">
          {t("reports.composer.recent", { count: total })}
        </span>
      </div>

      <div className="relative">
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder={t("reports.composer.searchPlaceholder")}
          aria-label={t("reports.composer.searchPlaceholder")}
          className="pr-8 pl-8"
        />
        {search ? (
          <button
            type="button"
            onClick={() => onSearch("")}
            aria-label={t("reports.composer.clearSearch")}
            className="absolute top-1/2 right-2 flex size-5 -translate-y-1/2 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </div>

      {isLoading ? (
        <div className="space-y-2 pt-1" aria-hidden="true">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-3/4" />
        </div>
      ) : null}

      {isError ? (
        <EmptyState
          icon={RefreshCw}
          title={t("common.loadError")}
          description={t("reports.composer.noRecordsDesc")}
          className="border-0 bg-transparent py-6"
        >
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw data-icon="inline-start" />
            {t("common.retry")}
          </Button>
        </EmptyState>
      ) : null}

      {!isLoading && !isError && total === 0 ? (
        <EmptyState
          icon={AlertCircle}
          title={t("reports.composer.noRecords")}
          description={t("reports.composer.noRecordsDesc")}
          className="py-6"
        >
          <Button asChild size="sm">
            <Link to="/records">{t("reports.composer.goRecords")}</Link>
          </Button>
        </EmptyState>
      ) : null}

      {!isLoading && !isError && total > 0 && records.length === 0 ? (
        <EmptyState
          icon={Search}
          title={t("reports.composer.noMatch")}
          description={t("reports.composer.noMatchDesc")}
          className="border-0 bg-transparent py-6"
        >
          <Button variant="outline" size="sm" onClick={() => onSearch("")}>
            {t("reports.composer.clearSearch")}
          </Button>
        </EmptyState>
      ) : null}

      {!isLoading && !isError && records.length > 0 ? (
        <div className="max-h-60 overflow-y-auto pr-1" role="listbox">
          {records.map((record) => {
            const active = record.id === selectedId;
            const source = record.device.model || "—";
            return (
              <button
                key={record.id}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => onSelect(record.id)}
                className={cn(
                  "mb-1 flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                  active
                    ? "border-primary bg-accent-soft"
                    : "border-transparent hover:bg-accent",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {formatDateTime(record.recordedAt, locale)}
                  </span>
                  <span className="eh-caption block truncate text-muted-foreground">
                    {source} · {formatDuration(Math.floor(record.durationSec), locale)}
                    {record.leads.length > 0
                      ? ` · ${record.leads.join("/")}`
                      : ""}
                  </span>
                </span>
                <AnalysisStatusBadge status={record.analysisStatus} />
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
