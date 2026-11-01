import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { ArrowRight, FilePlus2, Gauge, Footprints, HeartPulse, Moon, Scale, RefreshCw, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { useImport } from "@/components/import/import-provider";
import { useHealthRecords } from "@/lib/api/queries";
import {
  HEALTH_RECORD_PREFIX,
  healthKindOf,
  toHealthRecordView,
  type HealthRecordView,
} from "@/lib/api/adapters";
import type { HealthRecordKind } from "@/lib/api/types";
import { formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { cn } from "cn";

const KIND_ORDER: readonly HealthRecordKind[] = [
  "steps",
  "heart-rate",
  "sleep",
  "body-mass",
  "blood-pressure",
];

const KIND_ICON: Partial<Record<HealthRecordKind, LucideIcon>> = {
  steps: Footprints,
  "heart-rate": HeartPulse,
  sleep: Moon,
  "body-mass": Scale,
  "blood-pressure": Gauge,
};

function durationText(seconds: number, locale: string, t: TFunction): string {
  const totalMinutes = Math.max(0, Math.round(seconds / 60));
  if (totalMinutes < 60) {
    return t("healthData.durationMinutes", {
      minutes: formatNumber(totalMinutes, locale),
    });
  }
  return t("healthData.durationHoursMinutes", {
    hours: formatNumber(Math.floor(totalMinutes / 60), locale),
    minutes: formatNumber(totalMinutes % 60, locale),
  });
}

function valueText(
  view: HealthRecordView,
  locale: string,
  t: TFunction,
): string {
  switch (view.kind) {
    case "steps":
      return view.value === null
        ? "—"
        : `${formatNumber(view.value, locale)} ${t("healthData.units.steps")}`;
    case "heart-rate":
      return view.value === null
        ? "—"
        : `${formatNumber(view.value, locale)} ${t("healthData.units.bpm")}`;
    case "body-mass":
      return view.value === null
        ? "—"
        : `${formatNumber(view.value, locale, { maximumFractionDigits: 1 })} ${t("healthData.units.kg")}`;
    case "blood-pressure":
      return view.systolic === null || view.diastolic === null
        ? "—"
        : `${formatNumber(view.systolic, locale)}/${formatNumber(view.diastolic, locale)} ${t("healthData.units.mmHg")}`;
    case "sleep":
      return view.durationSec !== null
        ? durationText(view.durationSec, locale, t)
        : t(`healthData.sleepStages.${view.sleepStage ?? "unknown"}`);
    default:
      return view.value === null ? "—" : formatNumber(view.value, locale);
  }
}

export function HealthSummaryCard({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const { openPicker } = useImport();
  const query = useHealthRecords({
    limit: 100,
    recordTypePrefix: HEALTH_RECORD_PREFIX,
  });

  const latest = useMemo(() => {
    const map = new Map<HealthRecordKind, HealthRecordView>();
    for (const record of query.data?.items ?? []) {
      const kind = healthKindOf(record.recordType);
      if (!kind || map.has(kind)) continue;
      map.set(kind, toHealthRecordView(record));
    }
    return map;
  }, [query.data]);

  const total = query.data?.total ?? 0;
  const hasData = total > 0 && latest.size > 0;

  return (
    <Card className={cn("eh-lift", className)}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("dashboard.healthSummary.title")}</CardTitle>
        <CardDescription>{t("dashboard.healthSummary.description")}</CardDescription>
        {hasData ? (
          <CardAction>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/health-data">
                {t("dashboard.healthSummary.viewAll")}
                <ArrowRight data-icon="inline-end" />
              </Link>
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5" aria-hidden="true">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-20 w-full" />
            ))}
          </div>
        ) : query.isError ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-border bg-surface/60 px-4 py-4">
            <p className="eh-caption text-muted-foreground">
              {t("healthData.errorDesc")}
            </p>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              <RefreshCw data-icon="inline-start" />
              {t("common.retry")}
            </Button>
          </div>
        ) : !hasData ? (
          <EmptyState
            icon={FilePlus2}
            title={t("dashboard.healthSummary.emptyTitle")}
            description={t("dashboard.healthSummary.emptyDesc")}
            className="border-0 bg-transparent py-4"
          >
            <Button size="sm" onClick={openPicker}>
              {t("dashboard.healthSummary.import")}
            </Button>
          </EmptyState>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
            {KIND_ORDER.filter((kind) => latest.has(kind)).map((kind) => {
              const Icon = KIND_ICON[kind] ?? HeartPulse;
              const view = latest.get(kind) as HealthRecordView;
              return (
                <div key={kind} className="rounded-xl border border-border bg-subtle/40 p-3">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Icon className="size-3.5" aria-hidden="true" />
                    <span className="eh-caption truncate">
                      {t(`healthData.kinds.${kind}`)}
                    </span>
                  </div>
                  <p className="eh-num mt-1.5 truncate text-lg leading-7 font-medium">
                    {valueText(view, locale, t)}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
