import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  Activity,
  Droplet,
  Droplets,
  Dumbbell,
  FilePlus2,
  FileSearch,
  Footprints,
  Gauge,
  HeartPulse,
  Moon,
  RefreshCw,
  Scale,
  Thermometer,
  Waves,
  Wind,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { RecordListSkeleton } from "@/components/common/loading";
import { useImport } from "@/components/import/import-provider";
import { useHealthRecords } from "@/lib/api/queries";
import {
  HEALTH_KINDS,
  HEALTH_RECORD_PREFIX,
  healthKindOf,
  healthRecordType,
  toHealthRecordView,
  type HealthRecordView,
  type HealthSourceId,
} from "@/lib/api/adapters";
import type { HealthRecordKind } from "@/lib/api/types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { formatSeconds } from "@/lib/waveform";

type TimeFilter = "all" | "7d" | "30d" | "90d";
type TypeFilter = "all" | HealthRecordKind;

const PAGE_SIZE = 20;

const KIND_ICON: Record<HealthRecordKind, LucideIcon> = {
  steps: Footprints,
  "heart-rate": HeartPulse,
  "resting-heart-rate": Activity,
  sleep: Moon,
  "body-mass": Scale,
  "blood-pressure": Gauge,
  spo2: Droplets,
  stress: Waves,
  workout: Dumbbell,
  "respiratory-rate": Wind,
  "body-temperature": Thermometer,
  "blood-glucose": Droplet,
  hrv: HeartPulse,
};

const SOURCE_LABEL_KEY: Record<HealthSourceId, string> = {
  "apple-health": "healthData.sources.apple",
  "samsung-health": "healthData.sources.samsung",
  "xiaomi-mi-fitness": "healthData.sources.xiaomi",
  "huawei-health": "healthData.sources.huawei",
  zepp: "healthData.sources.zepp",
  "oppo-health": "healthData.sources.oppo",
  "garmin-connect": "healthData.sources.garmin",
  fitbit: "healthData.sources.fitbit",
  withings: "healthData.sources.withings",
  "google-fit": "healthData.sources.googleFit",
  unknown: "healthData.sources.unknown",
};

function filterChipClass(active: boolean) {
  return cn(
    "h-7 rounded-full border px-3 text-xs transition-colors",
    active
      ? "border-primary bg-accent-soft font-medium text-foreground"
      : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

function valueText(
  view: HealthRecordView,
  t: TFunction,
  locale: string,
): string {
  const withUnit = (value: number, unit: string, digits = 0) =>
    `${formatNumber(value, locale, { maximumFractionDigits: digits })} ${unit}`;
  switch (view.kind) {
    case "steps":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.steps"));
    case "heart-rate":
    case "resting-heart-rate":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.bpm"));
    case "body-mass":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.kg"), 1);
    case "blood-pressure":
      if (view.systolic === null || view.diastolic === null) return "—";
      return `${formatNumber(view.systolic, locale)}/${formatNumber(
        view.diastolic,
        locale,
      )} ${t("healthData.units.mmHg")}`;
    case "sleep":
      return t(`healthData.sleepStages.${view.sleepStage ?? "unknown"}`);
    case "spo2":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.percent"));
    case "stress":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.score"));
    case "workout": {
      const workout = view.workout;
      if (!workout) return "—";
      const parts = [workout.activity || t("healthData.workout.activity")];
      if (workout.durationSec !== null) parts.push(formatSeconds(workout.durationSec));
      if (workout.distanceM !== null) {
        parts.push(`${formatNumber(workout.distanceM / 1000, locale, { maximumFractionDigits: 2 })} km`);
      }
      if (workout.energyKcal !== null) {
        parts.push(`${formatNumber(workout.energyKcal, locale)} kcal`);
      }
      if (workout.avgHeartRate !== null) {
        parts.push(`${formatNumber(workout.avgHeartRate, locale)} bpm`);
      }
      return parts.join(" · ");
    }
    case "respiratory-rate":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.perMinute"));
    case "body-temperature":
      return view.value === null
        ? "—"
        : withUnit(view.value, t("healthData.units.celsius"), 1);
    case "blood-glucose":
      return view.value === null
        ? "—"
        : withUnit(view.value, view.unit || t("healthData.units.mmolPerLiter"), 1);
    case "hrv":
      return view.value === null
        ? "—"
        : `${t(`healthData.hrvMetrics.${view.metric ?? "rmssd"}`, {
            defaultValue: view.metric ?? "HRV",
          })} ${formatNumber(view.value, locale)} ${view.unit || "ms"}`;
  }
}

function sleepDurationText(
  seconds: number,
  t: TFunction,
  locale: string,
): string {
  const totalMinutes = Math.round(seconds / 60);
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

function timeRangeText(view: HealthRecordView, locale: string, t: TFunction) {
  const start = view.startAt ? formatDateTime(view.startAt, locale) : null;
  const end = view.endAt ? formatDateTime(view.endAt, locale) : null;
  if (!start) return "—";
  if (!end || end === start) return t("healthData.startTime", { time: start });
  return t("healthData.timeRange", { start, end });
}

function payloadRows(
  view: HealthRecordView,
  t: TFunction,
): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  const add = (key: string, raw: unknown) => {
    if (raw === undefined || raw === null || raw === "") return;
    const value = typeof raw === "object" ? JSON.stringify(raw) : String(raw);
    rows.push({ label: t(`healthData.payloadFields.${key}`), value });
  };
  add("value", view.payload.value);
  add("unit", view.payload.unit);
  add("startAt", view.payload.startAt);
  add("endAt", view.payload.endAt);
  add("sourceApp", view.payload.sourceApp);
  add("importSource", view.metadata.importSource);
  add("externalId", view.metadata.externalId);
  return rows;
}

function HealthDataRow({ view }: { view: HealthRecordView }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const Icon = KIND_ICON[view.kind];
  const rows = payloadRows(view, t);
  const durationText =
    view.kind === "sleep" && view.durationSec !== null
      ? sleepDurationText(view.durationSec, t, locale)
      : null;

  return (
    <div className="px-5 py-3 transition-colors hover:bg-accent">
      <div className="flex items-start gap-3">
        <div
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-subtle text-muted-foreground"
          aria-hidden="true"
        >
          <Icon className="size-4" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-medium">
              {t(`healthData.kinds.${view.kind}`)}
            </span>
            <span className="eh-num text-sm font-semibold">
              {valueText(view, t, locale)}
            </span>
            {durationText ? (
              <span className="eh-caption text-muted-foreground">
                {t("healthData.duration", { duration: durationText })}
              </span>
            ) : null}
          </div>
          <p className="eh-caption mt-0.5 text-muted-foreground">
            {timeRangeText(view, locale, t)} ·{" "}
            {t("healthData.importedAt", {
              time: formatDateTime(view.importedAt, locale),
            })}
          </p>
        </div>

        <Badge variant="secondary" className="shrink-0 font-normal">
          {t(SOURCE_LABEL_KEY[view.sourceId])}
        </Badge>
      </div>

      <details className="group mt-2 pl-12">
        <summary className="eh-caption inline-flex cursor-pointer list-none items-center gap-1 text-muted-foreground hover:text-foreground">
          {t("healthData.payloadSummary")}
        </summary>
        <dl className="mt-2 grid gap-x-4 gap-y-1 border-l border-border pl-3 sm:grid-cols-2">
          {rows.map((row) => (
            <div key={row.label} className="flex min-w-0 gap-2 text-xs">
              <dt className="shrink-0 text-muted-foreground">{row.label}</dt>
              <dd className="eh-num truncate">{row.value}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}

export function HealthDataPage() {
  const { t } = useTranslation();
  const { openPicker } = useImport();
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [page, setPage] = useState(0);

  const capturedFrom = useMemo(() => {
    const days =
      timeFilter === "7d" ? 7 : timeFilter === "30d" ? 30 : timeFilter === "90d" ? 90 : 0;
    return days
      ? new Date(Date.now() - days * 86_400_000).toISOString()
      : undefined;
  }, [timeFilter]);

  const query = useHealthRecords({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    capturedFrom,
    // 精确类型走 recordType；「全部」用前缀，与后端互斥校验保持一致。
    recordType:
      typeFilter === "all" ? undefined : healthRecordType(typeFilter),
    recordTypePrefix:
      typeFilter === "all" ? HEALTH_RECORD_PREFIX : undefined,
  });

  const rows = useMemo(
    () =>
      (query.data?.items ?? []).flatMap((record) =>
        healthKindOf(record.recordType)
          ? [toHealthRecordView(record)]
          : [],
      ),
    [query.data],
  );
  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    if (page > 0 && page >= pageCount) setPage(pageCount - 1);
  }, [page, pageCount]);

  const hasFilters = typeFilter !== "all" || timeFilter !== "all";
  const clearFilters = () => {
    setTypeFilter("all");
    setTimeFilter("all");
    setPage(0);
  };

  return (
    <>
      <PageHeader
        eyebrow={t("healthData.eyebrow")}
        title={t("healthData.title")}
        description={t("healthData.description")}
        actions={
          <Button size="sm" onClick={openPicker}>
            <FilePlus2 data-icon="inline-start" />
            {t("healthData.emptyAction")}
          </Button>
        }
      />

      <Card>
        <CardContent className="px-0">
          <div className="flex flex-wrap items-end gap-3 border-b border-border px-5 py-3">
            <div
              className="flex min-h-14 flex-wrap items-center gap-1.5"
              role="group"
              aria-label={t("healthData.filters.type")}
            >
              <span className="eh-caption mr-1 text-muted-foreground">
                {t("healthData.filters.type")}
              </span>
              <button
                type="button"
                aria-pressed={typeFilter === "all"}
                className={filterChipClass(typeFilter === "all")}
                onClick={() => {
                  setTypeFilter("all");
                  setPage(0);
                }}
              >
                {t("healthData.filters.allTypes")}
              </button>
              {HEALTH_KINDS.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={typeFilter === kind}
                  className={filterChipClass(typeFilter === kind)}
                  onClick={() => {
                    setTypeFilter(kind);
                    setPage(0);
                  }}
                >
                  {t(`healthData.kinds.${kind}`)}
                </button>
              ))}
            </div>

            <div className="flex flex-col gap-1">
              <span className="eh-caption text-muted-foreground">
                {t("healthData.filters.time")}
              </span>
              <Select
                value={timeFilter}
                onValueChange={(value) => {
                  setTimeFilter(value as TimeFilter);
                  setPage(0);
                }}
              >
                <SelectTrigger
                  size="sm"
                  className="min-w-[128px]"
                  aria-label={t("healthData.filters.time")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">
                    {t("healthData.filters.allTime")}
                  </SelectItem>
                  <SelectItem value="7d">{t("healthData.filters.last7")}</SelectItem>
                  <SelectItem value="30d">{t("healthData.filters.last30")}</SelectItem>
                  <SelectItem value="90d">{t("healthData.filters.last90")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <span className="eh-caption ml-auto text-muted-foreground">
              {t("healthData.count", {
                shown: rows.length,
                total: query.data ? total : "—",
              })}
            </span>
          </div>

          {query.isLoading ? <RecordListSkeleton rows={4} /> : null}

          {query.isError ? (
            <div className="px-5 py-8">
              <EmptyState
                icon={RefreshCw}
                title={t("healthData.errorTitle")}
                description={t("healthData.errorDesc")}
                className="border-0 bg-transparent py-6"
              >
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  <RefreshCw data-icon="inline-start" />
                  {t("common.retry")}
                </Button>
              </EmptyState>
            </div>
          ) : null}

          {!query.isLoading && !query.isError && total === 0 && !hasFilters ? (
            <div className="px-5 py-6">
              {/* 顶部 PageHeader 已有唯一的「导入健康数据」入口，这里不再重复。 */}
              <EmptyState
                icon={FilePlus2}
                title={t("healthData.emptyTitle")}
                description={t("healthData.emptyDesc")}
                className="border-0 bg-transparent"
              />
            </div>
          ) : null}

          {!query.isLoading &&
          !query.isError &&
          rows.length === 0 &&
          (total > 0 || hasFilters) ? (
            <div className="px-5 py-6">
              <EmptyState
                icon={FileSearch}
                title={t("healthData.noMatchTitle")}
                description={t("healthData.noMatchDesc")}
                className="border-0 bg-transparent"
              >
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  {t("healthData.clearFilters")}
                </Button>
              </EmptyState>
            </div>
          ) : null}

          {rows.length > 0 ? (
            <div className="divide-y divide-border eh-stagger">
              {rows.map((view) => (
                <HealthDataRow key={view.id} view={view} />
              ))}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-5 py-2">
            <div className="flex items-center gap-2">
              {hasFilters ? (
                <Button variant="ghost" size="xs" onClick={clearFilters}>
                  {t("healthData.clearFilters")}
                </Button>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="xs"
                onClick={() => setPage((current) => Math.max(0, current - 1))}
                disabled={page === 0 || query.isFetching}
              >
                {t("healthData.previous")}
              </Button>
              <span className="eh-caption text-muted-foreground">
                {t("healthData.page", { page: page + 1, pages: pageCount })}
              </span>
              <Button
                variant="outline"
                size="xs"
                onClick={() =>
                  setPage((current) => Math.min(pageCount - 1, current + 1))
                }
                disabled={page + 1 >= pageCount || query.isFetching}
              >
                {t("healthData.next")}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
