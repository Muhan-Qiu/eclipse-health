import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  CircleDot,
  FileSearch,
  GitCompare,
  RefreshCw,
} from "lucide-react";
import { cn } from "cn";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { WaveformViewer } from "@/components/records/waveform-viewer";
import { measurementsByCode } from "@/components/records/measurement-list";
import { useRecordCompare, useRecords } from "@/lib/api/queries";
import type { AnalysisResult, HealthRecord } from "@/lib/api/types";
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
} from "@/lib/format";
import { intlLocale } from "@/lib/i18n";

const METRIC_ROWS = [
  { key: "heart_rate_mean", unit: "bpm" },
  { key: "rmssd", unit: "ms" },
  { key: "sdnn", unit: "ms" },
  { key: "n_ratio", unit: "%" },
  { key: "svb_ratio", unit: "%" },
  { key: "veb_ratio", unit: "%" },
  { key: "f_ratio", unit: "%" },
] as const;

const EPSILON = 0.05;

function parseIds(raw: string | null): string[] {
  const ids = (raw ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return [...new Set(ids)];
}

export function ComparePage() {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [searchParams, setSearchParams] = useSearchParams();
  const ids = useMemo(
    () => parseIds(searchParams.get("ids")).slice(0, 4),
    [searchParams],
  );
  const compareQuery = useRecordCompare(ids);
  const recordsQuery = useRecords({ limit: 100, recordType: "org.eclipsehealth.ecg" });
  const recordOptions = recordsQuery.data?.items ?? [];

  const setSlot = (slot: 0 | 1, value: string) => {
    const next = [ids[0] ?? "", ids[1] ?? ""];
    next[slot] = value;
    const picked = [...new Set(next.filter(Boolean))];
    setSearchParams(picked.length ? { ids: picked.join(",") } : {});
  };

  const clearSelection = () => setSearchParams({});

  const data = compareQuery.data;
  const records: HealthRecord[] = data?.records ?? [];
  const analyses = useMemo(() => {
    const map = new Map<string, AnalysisResult | null>();
    for (const entry of data?.analyses ?? []) {
      map.set(entry.recordId, entry.latestCompleted);
    }
    return map;
  }, [data]);

  const analysisFor = (recordId: string) => analyses.get(recordId) ?? null;
  const byCodeFor = (analysis: AnalysisResult | null) =>
    measurementsByCode(analysis?.measurements ?? []);

  const slots = [ids[0] ?? "", ids[1] ?? ""];
  const hasBoth = ids.length === 2;
  const anyAnalysis = records.some((record) => analysisFor(record.id) !== null);

  const formatValue = (value: number | null, unit: string) =>
    value === null
      ? t("compare.noData")
      : `${formatNumber(value, locale, { maximumFractionDigits: 1 })} ${unit}`;

  const extraRows = [
    {
      key: "quality",
      label: t("compare.quality"),
      unit: "%" as const,
      values: records.map((record) => {
        const score = analysisFor(record.id)?.quality.score;
        return score === null || score === undefined ? null : score * 100;
      }),
    },
    {
      key: "duration",
      label: t("compare.duration"),
      unit: "duration" as const,
      values: records.map((record) => record.durationSec ?? null),
    },
  ];

  const backButton = (
    <Button variant="outline" size="sm" asChild>
      <Link to="/records">
        <ArrowLeft data-icon="inline-start" />
        {t("compare.backToRecords")}
      </Link>
    </Button>
  );

  return (
    <>
      <PageHeader
        eyebrow={t("compare.eyebrow")}
        title={t("compare.title")}
        description={t("compare.description")}
        actions={
          <>
            {backButton}
            {ids.length > 0 ? (
              <Button variant="ghost" size="sm" onClick={clearSelection}>
                {t("compare.clear")}
              </Button>
            ) : null}
          </>
        }
      />

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-end gap-4">
          {([0, 1] as const).map((slot) => (
            <div key={slot} className="flex min-w-[220px] flex-1 flex-col gap-1">
              <span className="eh-caption text-muted-foreground">
                {slot === 0 ? t("compare.slots.a") : t("compare.slots.b")}
              </span>
              <Select
                value={slots[slot] || undefined}
                onValueChange={(value) => setSlot(slot, value)}
              >
                <SelectTrigger
                  size="sm"
                  aria-label={
                    slot === 0 ? t("compare.slots.a") : t("compare.slots.b")
                  }
                >
                  <SelectValue placeholder={t("compare.slots.placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  {recordOptions.map((record) => (
                    <SelectItem
                      key={record.id}
                      value={record.id}
                      disabled={slots[slot === 0 ? 1 : 0] === record.id}
                    >
                      {formatDateTime(record.recordedAt, locale)} ·{" "}
                      {t(`recordStatus.${record.analysisStatus}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}
          <span className="eh-caption max-w-[36ch] text-muted-foreground">
            {t("compare.hint")}
          </span>
        </CardContent>
      </Card>

      {!hasBoth ? (
        <EmptyState
          icon={GitCompare}
          title={
            ids.length === 0
              ? t("compare.pickTwoTitle")
              : t("compare.needTwoTitle")
          }
          description={t("compare.needTwoDesc")}
        >
          {backButton}
        </EmptyState>
      ) : null}

      {hasBoth && compareQuery.isLoading ? (
        <div className="grid gap-4 desk:grid-cols-2">
          {[0, 1].map((slot) => (
            <Card key={slot}>
              <CardContent className="space-y-3">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-[220px] w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      {hasBoth && compareQuery.isError ? (
        <EmptyState
          icon={RefreshCw}
          title={t("compare.errorTitle")}
          description={t("compare.errorDesc")}
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => void compareQuery.refetch()}
          >
            <RefreshCw data-icon="inline-start" />
            {t("common.retry")}
          </Button>
        </EmptyState>
      ) : null}

      {hasBoth && !compareQuery.isLoading && !compareQuery.isError ? (
        <div className="space-y-4">
          <div className="grid gap-4 desk:grid-cols-2">
            {records.map((record, index) => {
              const analysis = analysisFor(record.id);
              return (
                <Card key={record.id}>
                  <CardHeader>
                    <CardTitle className="eh-h3">
                      {index === 0 ? t("compare.recordA") : t("compare.recordB")}
                    </CardTitle>
                    <CardDescription>
                      {formatDateTime(record.capturedAt, locale)} ·{" "}
                      {record.leads.join(" / ") || "—"}
                      {analysis?.completedAt
                        ? ` · ${t("compare.analysisOn", {
                            time: formatDateTime(analysis.completedAt, locale),
                          })}`
                        : null}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="eh-caption text-muted-foreground">
                      {t("compare.waveformTitle")}
                    </p>
                    {record.signalIds.length > 0 ? (
                      <WaveformViewer
                        recordId={record.id}
                        leads={record.leads}
                        analysis={analysis}
                        height={200}
                        compact
                      />
                    ) : (
                      <p className="rounded-lg border border-dashed border-border px-3 py-10 text-center text-sm text-muted-foreground">
                        {t("waveform.empty")}
                      </p>
                    )}
                    {analysis ? null : (
                      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium">
                            {t("compare.noAnalysisTitle")}
                          </p>
                          <p className="eh-caption text-muted-foreground">
                            {t("compare.noAnalysisDesc")}
                          </p>
                        </div>
                        <Button variant="outline" size="xs" asChild>
                          <Link to={`/records/${record.id}`}>
                            <FileSearch data-icon="inline-start" />
                            {t("compare.openRecord")}
                          </Link>
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {anyAnalysis ? (
            <Card>
              <CardHeader>
                <CardTitle className="eh-h3">
                  {t("compare.metricsTitle")}
                </CardTitle>
                <CardDescription>{t("compare.disclaimer")}</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground">
                      <th scope="col" className="py-1.5 pr-3 font-normal">
                        {t("compare.metric")}
                      </th>
                      {records.map((record, index) => (
                        <th
                          key={record.id}
                          scope="col"
                          className="py-1.5 pr-3 font-normal"
                        >
                          {index === 0
                            ? t("compare.recordA")
                            : t("compare.recordB")}{" "}
                          · {formatDate(record.capturedAt, locale)}
                        </th>
                      ))}
                      <th scope="col" className="py-1.5 font-normal">
                        {t("compare.diff")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {METRIC_ROWS.map((row) => {
                      const [left = null, right = null] = records.map(
                        (record) => byCodeFor(analysisFor(record.id)).get(row.key)?.value ?? null,
                      );
                      const different =
                        left !== null &&
                        right !== null &&
                        Math.abs(left - right) > EPSILON;
                      return (
                        <tr
                          key={row.key}
                          className={cn(
                            "border-t border-border",
                            different && "bg-subtle/50",
                          )}
                        >
                          <th scope="row" className="py-2 pr-3 font-normal">
                            {t(`measurements.codes.${row.key}`, {
                              defaultValue: row.key,
                            })}
                          </th>
                          <td className="eh-num py-2 pr-3">
                            {formatValue(left ?? null, row.unit)}
                          </td>
                          <td className="eh-num py-2 pr-3">
                            {formatValue(right ?? null, row.unit)}
                          </td>
                          <td className="py-2 text-xs text-muted-foreground">
                            {left === null || right === null ? (
                              t("compare.onlyOne")
                            ) : different ? (
                              <Badge
                                variant="outline"
                                className="gap-1 font-normal text-muted-foreground"
                              >
                                <CircleDot className="size-3" aria-hidden="true" />
                                ±
                                {formatNumber(
                                  Math.abs((left ?? 0) - (right ?? 0)),
                                  locale,
                                  { maximumFractionDigits: 1 },
                                )}{" "}
                                {row.unit}
                              </Badge>
                            ) : (
                              t("compare.same")
                            )}
                          </td>
                        </tr>
                      );
                    })}

                    {extraRows.map((row) => {
                      const [left = null, right = null] = row.values;
                      const different =
                        left !== null &&
                        right !== null &&
                        Math.abs(left - right) > EPSILON;
                      const render = (value: number | null) => {
                        if (value === null) return t("compare.noData");
                        if (row.unit === "duration") {
                          return formatDuration(value, locale);
                        }
                        return `${formatNumber(value, locale, {
                          maximumFractionDigits: 1,
                        })} %`;
                      };
                      return (
                        <tr
                          key={row.key}
                          className={cn(
                            "border-t border-border",
                            different && "bg-subtle/50",
                          )}
                        >
                          <th scope="row" className="py-2 pr-3 font-normal">
                            {row.label}
                          </th>
                          <td className="eh-num py-2 pr-3">{render(left)}</td>
                          <td className="eh-num py-2 pr-3">{render(right)}</td>
                          <td className="py-2 text-xs text-muted-foreground">
                            {left === null || right === null ? (
                              t("compare.onlyOne")
                            ) : different ? (
                              <Badge
                                variant="outline"
                                className="gap-1 font-normal text-muted-foreground"
                              >
                                <CircleDot
                                  className="size-3"
                                  aria-hidden="true"
                                />
                                ±
                                {row.unit === "duration"
                                  ? formatDuration(
                                      Math.abs((left ?? 0) - (right ?? 0)),
                                      locale,
                                    )
                                  : `${formatNumber(
                                      Math.abs((left ?? 0) - (right ?? 0)),
                                      locale,
                                      { maximumFractionDigits: 1 },
                                    )} %`}
                              </Badge>
                            ) : (
                              t("compare.same")
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
