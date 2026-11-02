import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Download,
  ExternalLink,
  FileChartColumn,
  FileText,
  Image as ImageIcon,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import type { RecordSummary } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import {
  deleteReport,
  formatBytes,
  reportFileUrl,
  reportHistoryKey,
} from "./api";
import type { ReportSummary } from "./types";

interface ReportHistoryProps {
  record: RecordSummary | null;
  reports: ReportSummary[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onDeleted: (reportId: string) => void;
}

export function ReportHistory({
  record,
  reports,
  isLoading,
  isError,
  onRetry,
  onDeleted,
}: ReportHistoryProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const queryClient = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<ReportSummary | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (reportId: string) => deleteReport(reportId),
    onSuccess: (_data, reportId) => {
      setPendingDelete(null);
      onDeleted(reportId);
      if (record) {
        void queryClient.invalidateQueries({
          queryKey: reportHistoryKey(record.id),
        });
      }
    },
  });

  const recordDate = record ? formatDateTime(record.recordedAt, locale) : null;

  return (
    <Card className="gap-0">
      <CardHeader className="gap-1">
        <CardTitle>{t("reports.history.title")}</CardTitle>
        <CardDescription>
          {record
            ? t("reports.history.description", {
                date: recordDate,
                count: reports.length,
              })
            : t("reports.history.selectRecord")}
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-3">
        {!record ? (
          <p className="eh-small py-2 text-muted-foreground">
            {t("reports.history.selectRecord")}
          </p>
        ) : null}

        {record && isLoading ? (
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : null}

        {record && isError ? (
          <EmptyState
            icon={RefreshCw}
            title={t("reports.history.loadError")}
            description={t("reports.composer.noRecordsDesc")}
            className="border-0 bg-transparent py-6"
          >
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw data-icon="inline-start" />
              {t("reports.history.retry")}
            </Button>
          </EmptyState>
        ) : null}

        {record && !isLoading && !isError && reports.length === 0 ? (
          <EmptyState
            icon={FileChartColumn}
            title={t("reports.history.emptyTitle")}
            description={t("reports.history.emptyDesc")}
            className="border-0 bg-transparent py-6"
          />
        ) : null}

        {record && !isLoading && !isError && reports.length > 0 ? (
          <ul className="divide-y divide-border">
            {reports.map((report) => {
              const isPdf = report.format === "pdf";
              const Icon = isPdf ? FileText : ImageIcon;
              const url = reportFileUrl(report.downloadUrl);
              const templateLabel = t(
                `reports.composer.templates.${report.template}`,
                { defaultValue: String(report.template) },
              );
              return (
                <li
                  key={report.reportId}
                  className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-0 items-start gap-2.5">
                    <span
                      className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-subtle text-muted-foreground"
                      aria-hidden="true"
                    >
                      <Icon className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {templateLabel} · {report.format.toUpperCase()}
                      </p>
                      <p className="eh-caption text-muted-foreground">
                        {report.createdAt
                          ? t("reports.history.createdAt", {
                              date: formatDateTime(report.createdAt, locale),
                            })
                          : "—"}
                        {" · "}
                        {formatBytes(report.size)}
                      </p>
                      <Badge
                        variant="outline"
                        className={`mt-1 font-normal ${
                          report.redacted
                            ? "text-muted-foreground"
                            : "border-warning/40 text-warning"
                        }`}
                      >
                        {report.redacted
                          ? t("reports.history.redacted")
                          : t("reports.history.unredacted")}
                      </Badge>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1">
                    <Button asChild size="xs" variant="outline">
                      <a href={url} download={report.fileName}>
                        <Download data-icon="inline-start" />
                        {t("reports.history.download")}
                      </a>
                    </Button>
                    {isPdf ? (
                      <Button asChild size="xs" variant="ghost">
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={t("reports.history.open")}
                        >
                          <ExternalLink data-icon="inline-start" />
                          {t("reports.history.open")}
                        </a>
                      </Button>
                    ) : null}
                    <Button
                      size="icon-xs"
                      variant="ghost"
                      aria-label={t("reports.history.delete")}
                      onClick={() => setPendingDelete(report)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </CardContent>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingDelete(null);
            deleteMutation.reset();
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("reports.history.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("reports.history.deleteDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteMutation.isError ? (
            <Alert variant="destructive">
              <AlertDescription>
                {t("reports.history.deleteFailed")}
              </AlertDescription>
            </Alert>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (pendingDelete) deleteMutation.mutate(pendingDelete.reportId);
              }}
            >
              {deleteMutation.isPending
                ? t("reports.history.deleting")
                : t("reports.history.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
