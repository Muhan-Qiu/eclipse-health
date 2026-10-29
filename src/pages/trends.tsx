import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileSearch, RefreshCw, TrendingUp } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { MetricChart } from "@/components/trends/metric-chart";
import { useRecords, useTrends } from "@/lib/api/queries";

const METRIC_OPTIONS = [
  "heart_rate_mean",
  "heart_rate_min",
  "heart_rate_max",
  "rmssd",
  "sdnn",
  "pnn50",
  "n_ratio",
  "svb_ratio",
  "veb_ratio",
  "f_ratio",
] as const;

const METRIC_COLORS = [
  "var(--eh-signal)",
  "var(--eh-accent)",
  "var(--eh-info)",
  "var(--eh-warning)",
  "var(--eh-chart-5)",
  "var(--eh-chart-4)",
];

const MAX_METRICS = 6;

type RangeKey = "7d" | "30d" | "90d" | "all";

const RANGE_DAYS: Record<Exclude<RangeKey, "all">, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
};

function chipClass(active: boolean) {
  return cn(
    "h-7 rounded-full border px-3 text-xs transition-colors",
    active
      ? "border-primary bg-accent-soft font-medium text-foreground"
      : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
    "disabled:cursor-not-allowed disabled:opacity-40",
  );
}

export function TrendsPage() {
  const { t } = useTranslation();
  const [metrics, setMetrics] = useState<string[]>([
    "heart_rate_mean",
    "rmssd",
  ]);
  const [range, setRange] = useState<RangeKey>("30d");

  const from = useMemo(() => {
    if (range === "all") return undefined;
    return new Date(
      Date.now() - RANGE_DAYS[range] * 86_400_000,
    ).toISOString();
  }, [range]);

  const params = useMemo(() => ({ metrics, from }), [metrics, from]);
  const query = useTrends(params);
  // 首次运行引导：有记录但没分析 vs 完全没有记录，文案不同。
  const recordsQuery = useRecords({ limit: 1, recordType: "org.eclipsehealth.ecg" });
  const hasRecords = (recordsQuery.data?.total ?? 0) > 0;

  const toggleMetric = (metric: string) => {
    setMetrics((current) => {
      if (current.includes(metric)) {
        // 至少保留一个指标，否则没有可画的图。
        return current.length === 1
          ? current
          : current.filter((item) => item !== metric);
      }
      return current.length >= MAX_METRICS ? current : [...current, metric];
    });
  };

  const series = query.data?.series ?? [];
  const hasPoints = series.some((item) => item.points.length > 0);

  return (
    <>
      <PageHeader
        eyebrow={t("trends.eyebrow")}
        title={t("trends.title")}
        description={t("trends.description")}
      />

      <Card className="mb-4">
        <CardContent className="space-y-3">
          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label={t("trends.metrics.label")}
          >
            <span className="eh-caption mr-1 text-muted-foreground">
              {t("trends.metrics.label")}
            </span>
            {METRIC_OPTIONS.map((metric) => {
              const active = metrics.includes(metric);
              return (
                <button
                  key={metric}
                  type="button"
                  aria-pressed={active}
                  className={chipClass(active)}
                  disabled={!active && metrics.length >= MAX_METRICS}
                  onClick={() => toggleMetric(metric)}
                >
                  {t(`measurements.codes.${metric}`, { defaultValue: metric })}
                </button>
              );
            })}
          </div>

          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label={t("trends.range.label")}
          >
            <span className="eh-caption mr-1 text-muted-foreground">
              {t("trends.range.label")}
            </span>
            {(
              [
                ["7d", t("trends.range.d7")],
                ["30d", t("trends.range.d30")],
                ["90d", t("trends.range.d90")],
                ["all", t("trends.range.all")],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={range === value}
                className={chipClass(range === value)}
                onClick={() => setRange(value)}
              >
                {label}
              </button>
            ))}
            <span className="eh-caption ml-auto text-muted-foreground">
              {t("trends.metrics.hint")}
            </span>
          </div>
        </CardContent>
      </Card>

      {query.isLoading ? (
        <div className="grid gap-4 desk:grid-cols-2">
          {metrics.slice(0, 2).map((metric) => (
            <Card key={metric}>
              <CardContent className="space-y-3">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-[220px] w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      {query.isError ? (
        <EmptyState
          icon={RefreshCw}
          title={t("trends.errorTitle")}
          description={t("trends.errorDesc")}
        >
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            <RefreshCw data-icon="inline-start" />
            {t("common.retry")}
          </Button>
        </EmptyState>
      ) : null}

      {!query.isLoading && !query.isError && !hasPoints ? (
        <EmptyState
          icon={hasRecords ? FileSearch : TrendingUp}
          title={t("trends.emptyTitle")}
          description={t("trends.emptyDesc")}
        >
          <Button variant="outline" size="sm" asChild>
            <Link to="/records">{t("trends.emptyAction")}</Link>
          </Button>
        </EmptyState>
      ) : null}

      {!query.isLoading && !query.isError && hasPoints ? (
        <div className="grid gap-4 desk:grid-cols-2">
          {series.map((item, index) => (
            <MetricChart
              key={item.metric}
              series={item}
              color={METRIC_COLORS[index % METRIC_COLORS.length] ?? "var(--eh-signal)"}
            />
          ))}
        </div>
      ) : null}
    </>
  );
}
