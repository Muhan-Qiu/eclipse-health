import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  CircleAlert,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/common/empty-state";
import { errorMessage } from "@/lib/api/error";
import { intlLocale } from "@/lib/i18n";
import {
  useCreateMetric,
  useDeleteMetric,
  useMetrics,
} from "./use-profile-data";
import { METRIC_KINDS, METRIC_UNITS } from "./types";
import type { Metric, MetricKind, MetricValues } from "./types";

const RANGE_DAYS = { "7d": 7, "30d": 30, "90d": 90 } as const;
type RangeKey = keyof typeof RANGE_DAYS | "all";

function chipClass(active: boolean) {
  return cn(
    "h-7 rounded-full border px-3 text-xs transition-colors",
    active
      ? "border-primary bg-accent-soft font-medium text-foreground"
      : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function localInputValue(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function resolvedTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function formatMetricValue(metric: Metric): string {
  if (metric.kind === "blood_pressure") {
    return `${metric.values.systolic ?? "–"}/${metric.values.diastolic ?? "–"} ${metric.unit}`;
  }
  const value =
    metric.kind === "weight"
      ? metric.values.weight
      : metric.kind === "spo2"
        ? metric.values.spo2
        : metric.values.glucose;
  return `${value ?? "–"} ${metric.unit}`;
}

interface QuickCardProps {
  kind: MetricKind;
  measuredAt: string;
  notes: string;
  onRecorded: (metric: Metric) => void;
}

function QuickCard({ kind, measuredAt, notes, onRecorded }: QuickCardProps) {
  const { t } = useTranslation();
  const mutation = useCreateMetric();
  const [systolic, setSystolic] = useState("");
  const [diastolic, setDiastolic] = useState("");
  const [single, setSingle] = useState("");
  const [added, setAdded] = useState(false);

  const parse = (value: string): number | undefined => {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    const number = Number(trimmed);
    return Number.isFinite(number) ? number : undefined;
  };

  const values: MetricValues | null = (() => {
    if (kind === "blood_pressure") {
      const s = parse(systolic);
      const d = parse(diastolic);
      return s === undefined || d === undefined
        ? null
        : { systolic: s, diastolic: d };
    }
    const value = parse(single);
    if (value === undefined) return null;
    if (kind === "weight") return { weight: value };
    if (kind === "spo2") return { spo2: value };
    return { glucose: value };
  })();

  const submit = () => {
    if (!values) {
      toast.error(t("profile.metrics.invalid"));
      return;
    }
    if (!measuredAt) {
      toast.error(t("profile.metrics.invalid"));
      return;
    }
    mutation.mutate(
      {
        kind,
        measuredAt: new Date(measuredAt).toISOString(),
        values,
        notes: notes.trim(),
        timezone: resolvedTimezone(),
      },
      {
        onSuccess: (metric) => {
          onRecorded(metric);
          setAdded(true);
          setTimeout(() => setAdded(false), 2_000);
          if (kind === "blood_pressure") {
            setSystolic("");
            setDiastolic("");
          } else {
            setSingle("");
          }
          toast.success(t("profile.metrics.added"));
        },
        onError: (error) => {
          toast.error(errorMessage(error));
        },
      },
    );
  };

  return (
    <div className="flex flex-col rounded-xl border border-border bg-surface/60 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="eh-small font-medium">{t(`profile.metrics.kinds.${kind}`)}</h3>
        <span className="eh-caption text-muted-foreground">
          {METRIC_UNITS[kind]}
        </span>
      </div>

      <div className="mt-3 flex gap-2">
        {kind === "blood_pressure" ? (
          <>
            <div className="min-w-0 flex-1 space-y-1">
              <Label htmlFor={`metric-${kind}-systolic`} className="eh-caption">
                {t("profile.metrics.fields.systolic")}
              </Label>
              <Input
                id={`metric-${kind}-systolic`}
                inputMode="numeric"
                className="eh-num h-9"
                value={systolic}
                onChange={(event) => setSystolic(event.target.value)}
              />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <Label htmlFor={`metric-${kind}-diastolic`} className="eh-caption">
                {t("profile.metrics.fields.diastolic")}
              </Label>
              <Input
                id={`metric-${kind}-diastolic`}
                inputMode="numeric"
                className="eh-num h-9"
                value={diastolic}
                onChange={(event) => setDiastolic(event.target.value)}
              />
            </div>
          </>
        ) : (
          <div className="min-w-0 flex-1 space-y-1">
            <Label htmlFor={`metric-${kind}-value`} className="eh-caption">
              {t("profile.metrics.value")}
            </Label>
            <Input
              id={`metric-${kind}-value`}
              inputMode="decimal"
              className="eh-num h-9"
              value={single}
              onChange={(event) => setSingle(event.target.value)}
            />
          </div>
        )}
      </div>

      <p className="eh-caption mt-2 text-muted-foreground">
        {t(`profile.metrics.rangeHint.${kind}`)}
      </p>

      <div className="mt-auto flex items-center gap-2 pt-3">
        <Button
          size="sm"
          onClick={submit}
          disabled={mutation.isPending || !values}
          aria-label={t("profile.metrics.addKind", {
            kind: t(`profile.metrics.kinds.${kind}`),
          })}
        >
          {mutation.isPending ? (
            <LoaderCircle className="animate-spin" data-icon="inline-start" />
          ) : (
            <Plus data-icon="inline-start" />
          )}
          {mutation.isPending
            ? t("profile.metrics.adding")
            : t("profile.metrics.add")}
        </Button>
        {added ? (
          <span className="eh-caption text-muted-foreground" role="status">
            {t("profile.metrics.added")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function WarningBadges({ metric }: { metric: Metric }) {
  const { t } = useTranslation();
  if (!metric.warnings.length) return null;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {metric.warnings.map((warning) => (
        <span
          key={warning.code}
          className={cn(
            "eh-caption inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
            warning.severity === "error"
              ? "border-destructive/30 text-destructive"
              : "border-border text-muted-foreground",
          )}
        >
          <CircleAlert className="size-3" aria-hidden="true" />
          {t(`profile.metrics.warningCodes.${warning.code}`, {
            defaultValue: warning.message,
          })}
        </span>
      ))}
    </span>
  );
}

export function MetricsPanel({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const [kindFilter, setKindFilter] = useState<MetricKind | "all">("all");
  const [range, setRange] = useState<RangeKey>("30d");
  const [measuredAt, setMeasuredAt] = useState(() => localInputValue(new Date()));
  const [notes, setNotes] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const from = useMemo(() => {
    if (range === "all") return undefined;
    return new Date(Date.now() - RANGE_DAYS[range] * 86_400_000).toISOString();
  }, [range]);

  const params = useMemo(
    () => ({
      kind: kindFilter === "all" ? undefined : kindFilter,
      from,
      limit: 50,
    }),
    [kindFilter, from],
  );

  const query = useMetrics(params);
  const deleteMutation = useDeleteMetric();

  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(intlLocale(i18n.language), {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));

  const onRecorded = (metric: Metric) => {
    if (metric.warnings.length) {
      toast.warning(
        metric.warnings
          .map((warning) =>
            t(`profile.metrics.warningCodes.${warning.code}`, {
              defaultValue: warning.message,
            }),
          )
          .join(" · "),
      );
    }
  };

  const items = query.data?.items ?? [];

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="eh-h3">{t("profile.metrics.title")}</CardTitle>
        <CardDescription>{t("profile.metrics.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="space-y-3">
          <h3 className="eh-caption text-muted-foreground">
            {t("profile.metrics.quickEntry")}
          </h3>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="metric-measured-at">
                {t("profile.metrics.measuredAt")}
              </Label>
              <Input
                id="metric-measured-at"
                type="datetime-local"
                className="eh-num w-[15.5rem]"
                value={measuredAt}
                onChange={(event) => setMeasuredAt(event.target.value)}
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-9"
              onClick={() => setMeasuredAt(localInputValue(new Date()))}
            >
              {t("profile.metrics.now")}
            </Button>
            <div className="min-w-[12rem] flex-1 space-y-1.5">
              <Label htmlFor="metric-notes">{t("profile.metrics.notes")}</Label>
              <Textarea
                id="metric-notes"
                rows={1}
                className="min-h-9"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {METRIC_KINDS.map((kind) => (
              <QuickCard
                key={kind}
                kind={kind}
                measuredAt={measuredAt}
                notes={notes}
                onRecorded={onRecorded}
              />
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="eh-h3">{t("profile.metrics.history.title")}</h3>
              <p className="eh-caption mt-1 text-muted-foreground">
                {t("profile.metrics.history.description")}
              </p>
            </div>
            <span className="eh-caption text-muted-foreground">
              {t("profile.metrics.history.total", {
                total: query.data?.total ?? 0,
              })}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              aria-pressed={kindFilter === "all"}
              className={chipClass(kindFilter === "all")}
              onClick={() => setKindFilter("all")}
            >
              {t("profile.metrics.history.allKinds")}
            </button>
            {METRIC_KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                aria-pressed={kindFilter === kind}
                className={chipClass(kindFilter === kind)}
                onClick={() => setKindFilter(kind)}
              >
                {t(`profile.metrics.kinds.${kind}`)}
              </button>
            ))}
            <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
            {(
              [
                ["7d", t("profile.metrics.history.ranges.7d")],
                ["30d", t("profile.metrics.history.ranges.30d")],
                ["90d", t("profile.metrics.history.ranges.90d")],
                ["all", t("profile.metrics.history.ranges.all")],
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
          </div>

          {query.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : null}

          {query.isError ? (
            <EmptyState
              icon={RefreshCw}
              title={t("profile.metrics.history.error")}
              description={t("profile.metrics.description")}
            >
              <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                <RefreshCw data-icon="inline-start" />
                {t("profile.metrics.history.retry")}
              </Button>
            </EmptyState>
          ) : null}

          {!query.isLoading && !query.isError && items.length === 0 ? (
            <EmptyState
              icon={Activity}
              title={t("profile.metrics.history.emptyTitle")}
              description={t("profile.metrics.history.emptyDesc")}
            />
          ) : null}

          {items.length > 0 ? (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {items.map((metric) => (
                <li
                  key={metric.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5"
                >
                  <span className="eh-caption w-36 shrink-0 text-muted-foreground">
                    {formatDate(metric.measuredAt)}
                  </span>
                  <span className="eh-small min-w-20 font-medium">
                    {t(`profile.metrics.kinds.${metric.kind}`)}
                  </span>
                  <span className="eh-num text-sm">{formatMetricValue(metric)}</span>
                  {metric.notes ? (
                    <span className="eh-caption min-w-0 flex-1 truncate text-muted-foreground">
                      {metric.notes}
                    </span>
                  ) : (
                    <span className="flex-1" />
                  )}
                  <WarningBadges metric={metric} />
                  {confirmId === metric.id ? (
                    <span className="flex items-center gap-1">
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={deleteMutation.isPending}
                        onClick={() =>
                          deleteMutation.mutate(metric.id, {
                            onSuccess: () => {
                              setConfirmId(null);
                              toast.success(t("profile.metrics.history.delete"));
                            },
                            onError: (error) => toast.error(errorMessage(error)),
                          })
                        }
                      >
                        {t("profile.metrics.history.deleteConfirm")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmId(null)}
                      >
                        {t("common.cancel")}
                      </Button>
                    </span>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("profile.metrics.history.delete")}
                      onClick={() => setConfirmId(metric.id)}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </CardContent>
    </Card>
  );
}
