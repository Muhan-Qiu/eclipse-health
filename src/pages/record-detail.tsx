import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Activity, FileSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoBadge } from "@/components/common/demo-badge";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { WaveThumbnail } from "@/components/common/wave-thumbnail";
import { api } from "@/lib/api/client";
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
} from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { useTagLabel } from "@/lib/tags";

export function RecordDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const tagLabel = useTagLabel();

  const { data: record, isLoading, isError } = useQuery({
    queryKey: ["records", id],
    queryFn: () => api.records.get(id ?? ""),
    enabled: Boolean(id),
  });

  const backButton = (
    <Button variant="outline" size="sm" asChild>
      <Link to="/records">
        <ArrowLeft data-icon="inline-start" />
        {t("recordDetail.backToRecords")}
      </Link>
    </Button>
  );

  if (isLoading) {
    return (
      <>
        <PageHeader
          eyebrow={t("recordDetail.eyebrow")}
          title={t("common.loading")}
          actions={backButton}
        />
        <div className="eh-grid">
          <Card className="desk:col-span-5 xl:col-span-7">
            <CardContent className="space-y-3">
              <Skeleton className="h-40 w-full" />
            </CardContent>
          </Card>
          <Card className="desk:col-span-3 xl:col-span-5">
            <CardContent className="space-y-4">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-10 w-24" />
              <Skeleton className="h-4 w-40" />
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  if (isError || !record) {
    return (
      <>
        <PageHeader
          eyebrow={t("recordDetail.eyebrow")}
          title={t("recordDetail.notFound")}
          actions={backButton}
        />
        <EmptyState
          icon={FileSearch}
          title={t("recordDetail.notFound")}
          description={t("recordDetail.notFoundDesc")}
        >
          {backButton}
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={t("recordDetail.eyebrow")}
        title={formatDate(record.recordedAt, locale)}
        description={`${record.device.model} · ${formatDateTime(
          record.recordedAt,
          locale,
        )} · ${formatDuration(record.durationSec, locale)}`}
        actions={backButton}
      />

      <div className="eh-grid">
        <Card className="desk:col-span-5 xl:col-span-7">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("dashboard.waveform.title")}
            </CardTitle>
            <CardDescription>
              {t("records.leads")} {record.leads.join(" / ")} ·{" "}
              {formatNumber(record.sampleRateHz, locale)} Hz
            </CardDescription>
            <CardAction>
              <DemoBadge />
            </CardAction>
          </CardHeader>
          <CardContent>
            <WaveThumbnail
              ariaLabel={t("dashboard.waveform.aria")}
              className="h-48"
            />
          </CardContent>
        </Card>

        <Card className="desk:col-span-3 xl:col-span-5">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("recordDetail.summaryTitle")}
            </CardTitle>
            <CardDescription>{t("recordDetail.pendingDesc")}</CardDescription>
            <CardAction>
              <Activity
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-9 w-28" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-9 w-24" />
            </div>
            <p className="eh-small text-muted-foreground">
              {t("recordDetail.pendingTitle")}
            </p>
          </CardContent>
        </Card>
      </div>

      <p className="eh-small mt-6 text-muted-foreground">
        {t("records.filters.tag")}:{" "}
        {record.tags.map((tag) => tagLabel(tag)).join(" · ")}
      </p>
    </>
  );
}
