import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { EngineDescriptor } from "@/features/analysis/engine-catalog";
import { ApiError } from "@/lib/api/error";
import type {
  AnalysisResult,
  EngineStatus,
  HealthRecord,
  Measurement,
  QualityWarning,
} from "@/lib/api/types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { ClassRatioBars } from "./class-ratio-bars";
import { MeasurementList, measurementsByCode } from "./measurement-list";

interface AnalysisPanelProps {
  record: HealthRecord;
  latest: AnalysisResult | null;
  analysis: AnalysisResult | null;
  analysesLoading: boolean;
  analysesError: unknown;
  analysisLoading: boolean;
  analysisError: unknown;
  onRetry: () => void;
  onStart: () => void;
  startPending: boolean;
  startError: unknown;
  engine: EngineStatus | undefined;
  engineLoading: boolean;
  engineError: unknown;
  onRetryEngine: () => void;
  engines: EngineDescriptor[];
  selectedEngineId: string | null;
  onSelectEngine: (engineId: string) => void;
  engineCatalogLoading: boolean;
  engineCatalogError: unknown;
  engineCatalogReady: boolean;
  onRetryEngineCatalog: () => void;
}

function errorCodeOf(error: unknown): string {
  if (error instanceof ApiError) return error.code;
  return "unknown";
}

function errorMessageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "";
}

function metricValue(
  measurements: Measurement[],
  code: string,
): number | null {
  return measurementsByCode(measurements).get(code)?.value ?? null;
}

function ParamStats({ analysis }: { analysis: AnalysisResult }) {
  const { t } = useTranslation();
  const params = analysis.parameters ?? {};
  const engineVersion = String(params.engineVersion ?? "—");
  const sequence = params.sequenceLength;
  const meanConfidence = params.meanConfidence;
  const preprocess = params.preprocess ?? analysis.provenance?.preprocess ?? "—";
  const classes = Array.isArray(params.classOrder)
    ? params.classOrder.join(" · ")
    : "N · SVEB · VEB · F";

  return (
    <details className="group rounded-lg border border-border bg-surface">
      <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm font-medium">
        <span>{t("analysis.modelCard.title")}</span>
        <span className="eh-caption text-muted-foreground">
          {analysis.modelId} {analysis.modelVersion}
        </span>
      </summary>
      <dl className="grid gap-2 border-t border-border px-3 py-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="eh-caption text-muted-foreground">{t("analysis.modelCard.model")}</dt>
          <dd className="eh-num">{analysis.modelId} · {analysis.modelVersion}</dd>
        </div>
        <div>
          <dt className="eh-caption text-muted-foreground">{t("analysis.modelCard.engine")}</dt>
          <dd className="eh-num">{engineVersion}</dd>
        </div>
        <div>
          <dt className="eh-caption text-muted-foreground">{t("analysis.modelCard.preprocess")}</dt>
          <dd className="eh-num">{String(preprocess)}</dd>
        </div>
        <div>
          <dt className="eh-caption text-muted-foreground">{t("analysis.modelCard.sequence")}</dt>
          <dd className="eh-num">{sequence === undefined ? "—" : String(sequence)}</dd>
        </div>
        <div>
          <dt className="eh-caption text-muted-foreground">{t("analysis.modelCard.meanConfidence")}</dt>
          <dd className="eh-num">
            {typeof meanConfidence === "number"
              ? `${(meanConfidence * 100).toFixed(1)}%`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="eh-caption text-muted-foreground">{t("analysis.modelCard.classes")}</dt>
          <dd className="eh-num">{classes}</dd>
        </div>
      </dl>
      <p className="eh-caption border-t border-border px-3 py-2 text-muted-foreground">
        {t("analysis.modelCard.note")}
      </p>
    </details>
  );
}

function WarningRow({ warning }: { warning: QualityWarning }) {
  const { t } = useTranslation();
  const label = t(`analysis.warningCodes.${warning.code}`, {
    defaultValue: warning.message || warning.code,
  });
  const hasRange =
    warning.startSec !== null &&
    warning.startSec !== undefined &&
    warning.endSec !== null &&
    warning.endSec !== undefined;
  const Icon = warning.severity === "error" ? ShieldAlert : AlertTriangle;

  return (
    <li className="flex items-start gap-2 py-1.5">
      <Icon
        className={
          warning.severity === "error"
            ? "mt-0.5 size-4 shrink-0 text-danger"
            : warning.severity === "warning"
              ? "mt-0.5 size-4 shrink-0 text-warning"
              : "mt-0.5 size-4 shrink-0 text-info"
        }
        aria-hidden="true"
      />
      <div className="min-w-0">
        <p className="eh-small">{label}</p>
        {hasRange ? (
          <p className="eh-caption text-muted-foreground">
            {t("analysis.warnings.range", {
              start: warning.startSec?.toFixed(1),
              end: warning.endSec?.toFixed(1),
            })}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function MetricTile({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-subtle/40 px-3 py-2.5">
      <p className="eh-caption text-muted-foreground">{label}</p>
      <p className="mt-1 flex items-baseline gap-1">
        <span className="eh-num text-2xl leading-7 font-medium">{value}</span>
        <span className="eh-caption text-muted-foreground">{unit}</span>
      </p>
    </div>
  );
}

function AnalysisErrorBlock({
  title,
  description,
  code,
  onRetry,
  retryLabel,
}: {
  title: string;
  description?: string;
  code?: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  const { t } = useTranslation();
  return (
    <Alert variant="destructive">
      <CircleAlert />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="space-y-2">
        {description ? <p>{description}</p> : null}
        {code ? (
          <code className="eh-num rounded bg-subtle px-1.5 py-0.5 text-xs">
            {code}
          </code>
        ) : null}
        {onRetry ? (
          <div>
            <Button variant="outline" size="xs" onClick={onRetry}>
              <RefreshCw data-icon="inline-start" />
              {retryLabel ?? t("common.retry")}
            </Button>
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

function EngineBadge({
  engine,
  loading,
  error,
}: {
  engine: EngineStatus | undefined;
  loading: boolean;
  error: unknown;
}) {
  const { t } = useTranslation();
  if (loading) {
    return (
      <span className="eh-caption inline-flex items-center gap-1 text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        {t("analysis.engine.checking")}
      </span>
    );
  }
  if (error) {
    return (
      <span className="eh-caption inline-flex items-center gap-1 text-warning">
        <CircleAlert className="size-3.5" aria-hidden="true" />
        {t("analysis.engine.unknown")}
      </span>
    );
  }
  if (!engine) return null;
  if (engine.status === "ready") {
    return (
      <span className="eh-caption inline-flex items-center gap-1 text-success">
        <CheckCircle2 className="size-3.5" aria-hidden="true" />
        {t("analysis.engine.ready")}
      </span>
    );
  }
  if (engine.status === "warming") {
    return (
      <span className="eh-caption inline-flex items-center gap-1 text-warning">
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        {t("analysis.engine.warming")}
      </span>
    );
  }
  return (
    <span className="eh-caption inline-flex items-center gap-1 text-danger">
      <CircleAlert className="size-3.5" aria-hidden="true" />
      {t("analysis.engine.error")}
    </span>
  );
}

export function AnalysisPanel({
  record,
  latest,
  analysis,
  analysesLoading,
  analysesError,
  analysisLoading,
  analysisError,
  onRetry,
  onStart,
  startPending,
  startError,
  engine,
  engineLoading,
  engineError,
  onRetryEngine,
  engines,
  selectedEngineId,
  onSelectEngine,
  engineCatalogLoading,
  engineCatalogError,
  engineCatalogReady,
  onRetryEngineCatalog,
}: AnalysisPanelProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const current = analysis ?? latest;
  const running =
    current?.status === "queued" || current?.status === "running";
  const engineBlocked =
    engine?.status === "warming" || engine?.status === "error";
  const availableEngines = engines.filter((item) => item.available);
  const selectedEngine =
    availableEngines.find((item) => item.id === selectedEngineId) ??
    availableEngines[0] ??
    null;
  // 目录已加载且一个可用引擎都没有时，不允许发起分析。
  const noAvailableEngine =
    engineCatalogReady && availableEngines.length === 0;
  const startDisabled =
    startPending || running || engineBlocked || noAvailableEngine;
  const startLabel = current ? t("analysis.reanalyze") : t("analysis.start");
  // 后端摘要带 `engine`，但共享类型尚未声明；参数里也冗余保存了一份，优先读参数。
  const rawEngine = current?.parameters?.engine;
  const currentEngineId =
    typeof rawEngine === "string"
      ? rawEngine
      : ((current as (AnalysisResult & { engine?: string }) | null)?.engine ??
        null);
  const currentEngineLabel = current
    ? `${currentEngineId ?? "—"} · ${current.modelId} ${current.modelVersion}`.trim()
    : "";
  const canReanalyze =
    current !== null &&
    (current.status === "completed" ||
      current.status === "failed" ||
      current.status === "cancelled");

  const startErrorMessage = (() => {
    if (!startError) return null;
    const code = errorCodeOf(startError);
    return t(`analysis.errorCodes.${code}`, {
      defaultValue: errorMessageOf(startError) || t("analysis.errorCodes.unknown"),
    });
  })();

  let body: ReactNode;
  if (analysesLoading) {
    body = (
      <div className="space-y-3" aria-hidden="true">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-4 w-32" />
      </div>
    );
  } else if (analysesError) {
    body = (
      <AnalysisErrorBlock
        title={t("analysis.unavailableTitle")}
        description={t("analysis.unavailableDesc")}
        code={errorCodeOf(analysesError)}
        onRetry={onRetry}
      />
    );
  } else if (!current) {
    body = (
      <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center">
        <p className="eh-small text-muted-foreground">{t("analysis.noneDesc")}</p>
      </div>
    );
  } else if (analysisLoading && current.status === "completed") {
    body = (
      <div className="space-y-3" aria-hidden="true">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-4 w-32" />
      </div>
    );
  } else if (running) {
    body = (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="eh-small flex items-center gap-2">
            <Loader2 className="size-4 animate-spin text-accent" aria-hidden="true" />
            {current.status === "queued"
              ? t("analysis.queued")
              : t("analysis.running")}
          </p>
          <span className="eh-num text-xs text-muted-foreground">
            {Math.round(current.progress?.percent ?? 0)}%
          </span>
        </div>
        <Progress
          value={current.progress?.percent ?? 0}
          aria-label={t("analysis.progressLabel")}
        />
        <p className="eh-caption text-muted-foreground">
          {t("analysis.stage", {
            stage: t(`analysis.stages.${current.progress?.stage ?? "quality"}`, {
              defaultValue: current.progress?.stage ?? "",
            }),
          })}
        </p>
      </div>
    );
  } else if (current.status === "failed" || current.status === "cancelled") {
    const code = current.error?.code ?? "analysis_failed";
    body = (
      <div className="space-y-3">
        <AnalysisErrorBlock
          title={t("analysis.failedTitle")}
          description={t(`analysis.errorCodes.${code}`, {
            defaultValue: current.error?.message || t("analysis.failedDesc"),
          })}
          code={code}
          onRetry={onStart}
          retryLabel={t("analysis.retry")}
        />
      </div>
    );
  } else {
    const measurements = current.measurements ?? [];
    const heartRate = metricValue(measurements, "heart_rate_mean");
    const rmssd = metricValue(measurements, "rmssd");
    const svb = metricValue(measurements, "svb_ratio") ?? 0;
    const veb = metricValue(measurements, "veb_ratio") ?? 0;
    const f = metricValue(measurements, "f_ratio") ?? 0;
    const abnormal = svb + veb + f;
    const nRatio = metricValue(measurements, "n_ratio") ?? Math.max(0, 100 - abnormal);
    const summaryLine =
      heartRate === null
        ? t("analysis.summaryLineNoHr", {
            n: formatNumber(nRatio, locale, { maximumFractionDigits: 1 }),
            svb: formatNumber(svb, locale, { maximumFractionDigits: 1 }),
            veb: formatNumber(veb, locale, { maximumFractionDigits: 1 }),
            f: formatNumber(f, locale, { maximumFractionDigits: 1 }),
          })
        : t("analysis.summaryLine", {
            hr: formatNumber(heartRate, locale, { maximumFractionDigits: 0 }),
            n: formatNumber(nRatio, locale, { maximumFractionDigits: 1 }),
            svb: formatNumber(svb, locale, { maximumFractionDigits: 1 }),
            veb: formatNumber(veb, locale, { maximumFractionDigits: 1 }),
            f: formatNumber(f, locale, { maximumFractionDigits: 1 }),
          });
    const quality = current.quality?.score ?? 0;
    const warnings = [
      ...(current.quality.warnings ?? []),
      ...(current.warnings ?? []),
    ].filter(
      (warning, index, list) =>
        list.findIndex((item) => item.code === warning.code) === index,
    );
    const params = current.parameters ?? {};
    const meanConfidence =
      typeof params.meanConfidence === "number" ? params.meanConfidence : null;
    const lead = typeof params.lead === "string" ? params.lead : record.leads[0];
    const originalFs =
      typeof params.originalFs === "number" ? params.originalFs : record.samplingRate;
    const critical =
      (heartRate !== null && (heartRate > 100 || heartRate < 50)) ||
      veb >= 10 ||
      (quality !== null && quality < 0.6);

    body = (
      <div className="space-y-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="eh-small">{summaryLine}</p>
          <span className="eh-caption text-muted-foreground">
            {current.completedAt
              ? formatDateTime(current.completedAt, locale)
              : "—"}
            {current.durationMs !== null
              ? ` · ${t("analysis.duration", { ms: current.durationMs })}`
              : ""}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <MetricTile
            label={t("analysis.metrics.heartRate")}
            value={heartRate === null ? "—" : formatNumber(heartRate, locale, { maximumFractionDigits: 0 })}
            unit={t("analysis.metrics.bpm")}
          />
          <MetricTile
            label={t("analysis.metrics.hrv")}
            value={rmssd === null ? "—" : formatNumber(rmssd, locale, { maximumFractionDigits: 1 })}
            unit={t("analysis.metrics.ms")}
          />
          <MetricTile
            label={t("analysis.metrics.abnormal")}
            value={formatNumber(abnormal, locale, { maximumFractionDigits: 1 })}
            unit={t("analysis.metrics.percent")}
          />
          <MetricTile
            label={t("analysis.metrics.quality")}
            value={quality === null ? "—" : formatNumber(quality * 100, locale, { maximumFractionDigits: 0 })}
            unit={t("analysis.metrics.percent")}
          />
        </div>

        {critical ? (
          <Alert>
            <AlertTriangle />
            <AlertTitle>{t("analysis.critical.title")}</AlertTitle>
            <AlertDescription>{t("analysis.critical.body")}</AlertDescription>
          </Alert>
        ) : null}

        {meanConfidence !== null && meanConfidence < 0.8 ? (
          <Alert>
            <AlertTriangle />
            <AlertTitle>{t("analysis.domain.lowConfidenceTitle")}</AlertTitle>
            <AlertDescription>
              {t("analysis.domain.lowConfidence", {
                value: `${Math.round(meanConfidence * 100)}%`,
              })}
            </AlertDescription>
          </Alert>
        ) : null}

        {lead && lead.toUpperCase() !== "MLII" ? (
          <p className="eh-caption text-muted-foreground">
            {t("analysis.domain.lead", { lead })}
          </p>
        ) : null}

        {originalFs !== null && Math.abs(originalFs - 360) > 0.5 ? (
          <p className="eh-caption text-muted-foreground">
            {t("analysis.domain.fs", {
              fs: formatNumber(originalFs, locale, { maximumFractionDigits: 0 }),
            })}
          </p>
        ) : null}

        <ClassRatioBars measurements={measurements} />

        <section>
          <h4 className="eh-caption mb-1.5 text-muted-foreground">
            {t("analysis.warnings.title")}
          </h4>
          {warnings.length ? (
            <ul className="divide-y divide-border">
              {warnings.map((warning, index) => (
                <WarningRow key={`${warning.code}-${index}`} warning={warning} />
              ))}
            </ul>
          ) : (
            <p className="eh-small text-muted-foreground">
              {t("analysis.warnings.empty")}
            </p>
          )}
        </section>

        <section>
          <h4 className="eh-caption mb-1.5 text-muted-foreground">
            {t("analysis.measurementsTitle")}
          </h4>
          <MeasurementList measurements={measurements} />
        </section>

        <ParamStats analysis={current} />

        <p className="eh-caption border-t border-border pt-3 text-muted-foreground">
          {t("analysis.nonDiagnostic")}
        </p>
      </div>
    );
  }

  const engineMessage =
    engine?.status === "warming"
      ? engine.message || t("analysis.engine.warmingMessage")
      : engine?.status === "error"
        ? engine.message || t("analysis.engine.errorMessage")
        : null;

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="eh-h3">{t("analysis.title")}</CardTitle>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <EngineBadge engine={engine} loading={engineLoading} error={engineError} />
          {engine?.status === "ready" ? (
            <span className="eh-caption text-muted-foreground">
              {engine.modelId} · {engine.modelVersion}
            </span>
          ) : null}
          {currentEngineId ? (
            <span className="eh-caption text-muted-foreground">
              {t("analysis.engine.current", { engine: currentEngineLabel })}
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {engineMessage ? (
          <Alert>
            <CircleAlert />
            <AlertTitle>
              {engine?.status === "error"
                ? t("analysis.engine.errorTitle")
                : t("analysis.engine.warmingTitle")}
            </AlertTitle>
            <AlertDescription>
              <p>{engineMessage}</p>
              <Button variant="outline" size="xs" onClick={onRetryEngine}>
                <RefreshCw data-icon="inline-start" />
                {t("analysis.engine.retry")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {engineError ? (
          <Alert>
            <CircleAlert />
            <AlertTitle>{t("analysis.engine.unknownTitle")}</AlertTitle>
            <AlertDescription>
              <p>{t("analysis.engine.unknownDesc")}</p>
              <Button variant="outline" size="xs" onClick={onRetryEngine}>
                <RefreshCw data-icon="inline-start" />
                {t("common.retry")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="space-y-1.5">
          <p className="eh-caption text-muted-foreground">
            {t("analysis.engine.selectLabel")}
          </p>
          {engineCatalogLoading ? (
            <p className="eh-small inline-flex items-center gap-1 text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              {t("analysis.engine.loading")}
            </p>
          ) : engineCatalogError ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="eh-small text-warning">
                {t("analysis.engine.catalogError")}
              </p>
              <Button variant="ghost" size="xs" onClick={onRetryEngineCatalog}>
                <RefreshCw data-icon="inline-start" />
                {t("common.retry")}
              </Button>
            </div>
          ) : availableEngines.length > 1 && selectedEngine ? (
            <Select value={selectedEngine.id} onValueChange={onSelectEngine}>
              <SelectTrigger
                className="w-full"
                aria-label={t("analysis.engine.selectLabel")}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableEngines.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {t("analysis.engine.option", {
                      name: item.name,
                      version: `${item.modelId} ${item.modelVersion}`.trim(),
                    })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : selectedEngine ? (
            <div>
              <p className="eh-small">
                {t("analysis.engine.single", {
                  name: selectedEngine.name,
                  version: `${selectedEngine.modelId} ${selectedEngine.modelVersion}`.trim(),
                })}
              </p>
              <p className="eh-caption mt-0.5 text-muted-foreground">
                {t("analysis.engine.moreHint")}
              </p>
            </div>
          ) : (
            <p className="eh-small text-warning">
              {t("analysis.engine.noAvailable")}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={onStart}
            disabled={startDisabled}
            title={
              engine?.status === "warming"
                ? t("analysis.engine.warmingMessage")
                : undefined
            }
          >
            {startPending ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : current ? (
              <RefreshCw data-icon="inline-start" />
            ) : (
              <Play data-icon="inline-start" />
            )}
            {startPending ? t("analysis.starting") : startLabel}
          </Button>
          {current?.status === "completed" ? (
            <Badge variant="secondary">{t("analysis.completed")}</Badge>
          ) : null}
          {running ? <Badge variant="outline">{t("analysis.inProgress")}</Badge> : null}
        </div>

        {canReanalyze ? (
          <p className="eh-caption text-muted-foreground">
            {t("recordDetail.reanalyzeHint")}
          </p>
        ) : null}

        {startErrorMessage ? (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertTitle>{t("analysis.startFailed")}</AlertTitle>
            <AlertDescription>{startErrorMessage}</AlertDescription>
          </Alert>
        ) : null}

        {analysisError && !running ? (
          <p className="eh-caption text-warning">
            {t("analysis.detailLoadFailed", {
              code: errorCodeOf(analysisError),
            })}
          </p>
        ) : null}

        {analysisLoading && !current ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          body
        )}
      </CardContent>
    </Card>
  );
}
