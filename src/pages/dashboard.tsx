import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  BookOpen,
  FilePlus2,
  FlaskConical,
  LoaderCircle,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { DemoBadge } from "@/components/common/demo-badge";
import { EmptyState } from "@/components/common/empty-state";
import { AnimatedNumber } from "@/components/common/animated-number";
import { RecordListSkeleton } from "@/components/common/loading";
import { Sparkline } from "@/components/common/sparkline";
import { WaveformViewer } from "@/components/records/waveform-viewer";
import { RecordRow } from "@/components/records/record-row";
import { useImport } from "@/components/import/import-provider";
import { measurementsByCode } from "@/components/records/measurement-list";
import { WidgetGrid } from "@/features/modules/widgets/widget-grid";
import { HealthScoreGrid } from "@/features/scores/health-score-grid";
import { SuggestionCard } from "@/features/scores/suggestion-card";
import { HealthSummaryCard } from "@/features/scores/health-summary-card";
import {
  useAnalysis,
  useHealthScores,
  useHealthSuggestions,
  useImportSample,
  useRecentAnalyses,
  useRecords,
} from "@/lib/api/queries";
import type { AnalysisResult, RecordSummary } from "@/lib/api/types";
import { formatFullDate, formatNumber, greetingKey } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { quoteOfDay } from "@/lib/quotes";

const FORMAT_GROUPS = [
  {
    key: "standard",
    items: [
      { id: "wfdb", status: "supported" },
      { id: "csv", status: "supported" },
      { id: "float32", status: "supported" },
    ],
  },
  {
    key: "wearable",
    items: [
      { id: "apple", status: "pending" },
      { id: "samsung", status: "pending" },
      { id: "huawei", status: "pending" },
    ],
  },
  { key: "hospital", items: [{ id: "scp", status: "planned" }] },
] as const;

interface Candidate {
  record: RecordSummary;
  analysis: AnalysisResult;
}

function GuideCard({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Card className="eh-lift gap-0 p-5">
      <div
        className="flex size-9 items-center justify-center rounded-lg bg-accent-soft text-primary"
        aria-hidden="true"
      >
        <Icon className="size-4" />
      </div>
      <h2 className="eh-h3 mt-4">{title}</h2>
      <p className="eh-small mt-1.5 flex-1 text-muted-foreground">{description}</p>
      <div className="mt-4">{children}</div>
    </Card>
  );
}

function MetricRow({
  label,
  value,
  unit,
  format,
  children,
}: {
  label: string;
  value: number | null;
  unit: string;
  format: (value: number) => string;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-4 border-b border-border pb-3 last:border-0 last:pb-0">
      <div>
        <p className="eh-caption text-muted-foreground">{label}</p>
        <p className="mt-1 flex items-baseline gap-1.5">
          <span className="eh-num text-3xl leading-9 font-medium">
            <AnimatedNumber value={value} format={format} />
          </span>
          <span className="eh-caption text-muted-foreground">{unit}</span>
        </p>
      </div>
      {children}
    </div>
  );
}

function RecentRecords() {
  const { t } = useTranslation();
  const { openPicker } = useImport();
  const query = useRecords({
    limit: 3,
    recordType: "org.eclipsehealth.ecg",
  });

  if (query.isLoading) return <RecordListSkeleton rows={3} />;
  if (query.isError) {
    return (
      <EmptyState
        icon={RefreshCw}
        title={t("common.loadError")}
        description={t("dashboard.recent.errorDesc")}
        className="border-0 bg-transparent py-6"
      >
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          <RefreshCw data-icon="inline-start" />
          {t("common.retry")}
        </Button>
      </EmptyState>
    );
  }
  const records = query.data?.items ?? [];
  if (records.length === 0) {
    return (
      <div className="px-5 py-6">
        <EmptyState
          icon={FilePlus2}
          title={t("dashboard.recent.emptyTitle")}
          description={t("dashboard.recent.emptyDesc")}
          className="border-0 bg-transparent py-6"
        >
          <Button size="sm" onClick={openPicker}>
            {t("dashboard.recent.emptyAction")}
          </Button>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="divide-y divide-border eh-stagger">
      {records.map((record) => (
        <RecordRow key={record.id} record={record} />
      ))}
    </div>
  );
}

function MetricsCard({
  candidates,
  loading,
  hasRecords,
  latestRecord,
  openPicker,
}: {
  candidates: Candidate[];
  loading: boolean;
  hasRecords: boolean;
  latestRecord: RecordSummary | undefined;
  openPicker: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);

  const selected = useMemo(() => {
    return [...candidates].sort((a, b) => {
      const left = a.analysis.completedAt ?? a.analysis.startedAt ?? "";
      const right = b.analysis.completedAt ?? b.analysis.startedAt ?? "";
      return new Date(right).getTime() - new Date(left).getTime();
    })[0];
  }, [candidates]);

  const detailQuery = useAnalysis(selected?.analysis.id, Boolean(selected));
  const analysis = detailQuery.data ?? selected?.analysis ?? null;
  const measurements = analysis?.measurements ?? [];
  const byCode = measurementsByCode(measurements);
  const heartRate = byCode.get("heart_rate_mean")?.value ?? null;
  const rmssd = byCode.get("rmssd")?.value ?? null;
  const abnormal =
    (byCode.get("svb_ratio")?.value ?? 0) +
    (byCode.get("veb_ratio")?.value ?? 0) +
    (byCode.get("f_ratio")?.value ?? 0);
  const quality = analysis?.quality.score ?? null;

  const series = useMemo(() => {
    const ordered = [...candidates].sort(
      (a, b) =>
        new Date(a.record.recordedAt).getTime() -
        new Date(b.record.recordedAt).getTime(),
    );
    return ordered
      .map((item) => {
        const value = measurementsByCode(item.analysis.measurements)
          .get("heart_rate_mean")
          ?.value;
        return typeof value === "number" ? value : null;
      })
      .filter((value): value is number => value !== null);
  }, [candidates]);

  return (
    <Card className="eh-lift desk:col-span-3 xl:col-span-5">
      <CardHeader>
        <CardTitle className="eh-h3">{t("dashboard.metrics.title")}</CardTitle>
        <CardDescription>
          {analysis
            ? t("dashboard.metrics.fromAnalysis", {
                date: analysis.completedAt
                  ? new Intl.DateTimeFormat(locale, {
                      dateStyle: "medium",
                    }).format(new Date(analysis.completedAt))
                  : "—",
              })
            : t("dashboard.metrics.description")}
        </CardDescription>
        <CardAction>
          {selected?.record.isDemo ? <DemoBadge /> : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="space-y-3" aria-hidden="true">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : !analysis ? (
          <EmptyState
            icon={FlaskConical}
            title={t("dashboard.metrics.emptyTitle")}
            description={
              hasRecords
                ? t("dashboard.metrics.emptyDesc")
                : t("dashboard.metrics.emptyNoRecords")
            }
            className="border-0 bg-transparent px-2 py-4"
          >
            {hasRecords && latestRecord ? (
              <Button size="sm" asChild>
                <Link to={`/records/${latestRecord.id}`}>
                  {t("dashboard.metrics.openLatest")}
                  <ArrowRight data-icon="inline-end" />
                </Link>
              </Button>
            ) : (
              <Button size="sm" onClick={openPicker}>
                {t("dashboard.recent.emptyAction")}
              </Button>
            )}
          </EmptyState>
        ) : (
          <>
            <MetricRow
              label={t("dashboard.metrics.heartRate")}
              value={heartRate}
              format={(value) =>
                formatNumber(value, locale, { maximumFractionDigits: 0 })
              }
              unit={t("dashboard.metrics.bpm")}
            >
              {series.length >= 2 ? (
                <Sparkline
                  values={series}
                  ariaLabel={t("dashboard.metrics.sparklineAria")}
                />
              ) : null}
            </MetricRow>
            <MetricRow
              label={t("dashboard.metrics.hrv")}
              value={rmssd}
              format={(value) =>
                formatNumber(value, locale, { maximumFractionDigits: 1 })
              }
              unit={t("dashboard.metrics.ms")}
            />
            <MetricRow
              label={t("dashboard.metrics.abnormal")}
              value={abnormal}
              format={(value) =>
                formatNumber(value, locale, { maximumFractionDigits: 1 })
              }
              unit={t("dashboard.metrics.percent")}
            />
            <MetricRow
              label={t("dashboard.metrics.quality")}
              value={quality === null ? null : quality * 100}
              format={(value) =>
                formatNumber(value, locale, { maximumFractionDigits: 0 })
              }
              unit={t("dashboard.metrics.percent")}
            />
            <p className="eh-caption text-muted-foreground">
              {t("dashboard.metrics.note")}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const { openPicker } = useImport();
  const navigate = useNavigate();
  const importSample = useImportSample();
  const [formatsOpen, setFormatsOpen] = useState(false);
  const now = new Date();
  // 同一天内多次渲染取到同一句；跨天（本地日期变化）自动轮换。
  const quote = quoteOfDay(now);
  const english = i18n.language.startsWith("en");
  const quoteText = english ? quote.en : quote.zh;
  const quoteAuthor = english ? quote.authorEn : quote.author;

  const recentQuery = useRecords({
    limit: 5,
    recordType: "org.eclipsehealth.ecg",
  });
  const scoresQuery = useHealthScores();
  const suggestionsQuery = useHealthSuggestions();
  const recent = recentQuery.data?.items ?? [];
  const analysesQueries = useRecentAnalyses(recent);
  const sampleRecord = recent.find((record) => record.isSample);

  const loadSample = () => {
    if (sampleRecord) {
      navigate(`/records/${sampleRecord.id}`);
      return;
    }
    importSample.mutate(undefined, {
      onSuccess: (result) => navigate(`/records/${result.recordId}`),
    });
  };

  const candidates = useMemo<Candidate[]>(() => {
    const found: Candidate[] = [];
    analysesQueries.forEach((query, index) => {
      const record = recent[index];
      if (!record || !query.data) return;
      for (const analysis of query.data.items) {
        if (analysis.status === "completed") found.push({ record, analysis });
      }
    });
    return found;
  }, [analysesQueries, recent]);

  const latestRecord = recent[0];
  const latestCompleted = useMemo(() => {
    if (!latestRecord) return null;
    return (
      candidates.find((candidate) => candidate.record.id === latestRecord.id)
        ?.analysis ?? null
    );
  }, [candidates, latestRecord]);

  return (
    <>
      <header className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <p className="eh-caption tracking-[0.14em] text-muted-foreground uppercase">
            {t("dashboard.eyebrow")}
          </p>
          <h1 className="eh-h1 mt-1">{t(greetingKey(now))}</h1>
          <figure className="mt-2 max-w-[72ch]">
            <blockquote className="eh-small text-foreground">
              “{quoteText}”
            </blockquote>
            <figcaption className="eh-caption mt-1 text-muted-foreground">
              {t("dashboard.quote.attribution", { author: quoteAuthor })}
            </figcaption>
          </figure>
          <p className="eh-caption mt-1 text-muted-foreground">
            {t("dashboard.description")}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <p className="eh-caption text-muted-foreground">
            {formatFullDate(now, locale)}
          </p>
        </div>
      </header>

      {/* 健康评分/建议放在首屏最前，ECG 引导与波形整体下移。 */}
      <section
        className="eh-stagger grid gap-4 desk:grid-cols-3"
        aria-label={t("dashboard.scores.title")}
      >
        <HealthScoreGrid
          className="desk:col-span-2"
          scores={scoresQuery.data}
          loading={scoresQuery.isLoading}
          error={scoresQuery.isError}
        />
        <SuggestionCard
          className="desk:col-span-1"
          suggestions={suggestionsQuery.data}
          loading={suggestionsQuery.isLoading}
          error={suggestionsQuery.isError}
        />
        <HealthSummaryCard className="desk:col-span-3" />
      </section>

      <section
        className="eh-stagger mt-6 grid gap-4 md:grid-cols-3"
        aria-label={t("dashboard.guide.importTitle")}
      >
        <GuideCard
          icon={FilePlus2}
          title={t("dashboard.guide.importTitle")}
          description={t("dashboard.guide.importDesc")}
        >
          <Button size="sm" onClick={openPicker}>
            {t("dashboard.guide.importAction")}
            <ArrowRight data-icon="inline-end" />
          </Button>
        </GuideCard>

        <GuideCard
          icon={BookOpen}
          title={t("dashboard.guide.sampleTitle")}
          description={t("dashboard.guide.sampleDesc")}
        >
          <Button
            variant={sampleRecord ? "ghost" : "secondary"}
            size="sm"
            className={sampleRecord ? "-ml-2.5" : undefined}
            onClick={loadSample}
            disabled={importSample.isPending}
          >
            {importSample.isPending ? (
              <LoaderCircle data-icon="inline-start" className="animate-spin" />
            ) : (
              <FlaskConical data-icon="inline-start" />
            )}
            {sampleRecord
              ? t("dashboard.guide.sampleOpen")
              : importSample.isPending
                ? t("dashboard.guide.sampleLoading")
                : t("dashboard.guide.sampleAction")}
            <ArrowRight data-icon="inline-end" />
          </Button>
        </GuideCard>

        <GuideCard
          icon={FlaskConical}
          title={t("dashboard.guide.formatsTitle")}
          description={t("dashboard.guide.formatsDesc")}
        >
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2.5"
            onClick={() => setFormatsOpen(true)}
          >
            {t("dashboard.guide.formatsAction")}
            <ArrowRight data-icon="inline-end" />
          </Button>
        </GuideCard>
      </section>

      <div className="eh-widget-stagger">
        <WidgetGrid />
      </div>

      <div className="eh-grid mt-6 eh-stagger">
        {/* 记录不满 3 条时按内容高度收口，避免被右列拉高后留下大块空白。 */}
        <Card className="eh-lift self-start desk:col-span-5 xl:col-span-7">
          <CardHeader>
            <CardTitle className="eh-h3">{t("dashboard.recent.title")}</CardTitle>
            <CardDescription>{t("dashboard.recent.description")}</CardDescription>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/records">
                  {t("common.all")}
                  <ArrowRight data-icon="inline-end" />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="px-0">
            <RecentRecords />
          </CardContent>
        </Card>

        <MetricsCard
          candidates={candidates}
          loading={
            recentQuery.isLoading ||
            analysesQueries.some((query) => query.isLoading)
          }
          hasRecords={recent.length > 0}
          latestRecord={latestRecord}
          openPicker={openPicker}
        />

        <Card className="eh-lift desk:col-span-8 xl:col-span-12">
          <CardHeader>
            <CardTitle className="eh-h3">{t("dashboard.waveform.title")}</CardTitle>
            <CardDescription>
              {latestRecord
                ? t("dashboard.waveform.latest", {
                    device: latestRecord.device.model || t("records.localFile"),
                  })
                : t("dashboard.waveform.emptyDesc")}
            </CardDescription>
            <CardAction>
              <div className="flex items-center gap-2">
                {latestRecord?.isDemo ? <DemoBadge /> : null}
                {latestRecord ? (
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/records/${latestRecord.id}`}>
                      {t("dashboard.waveform.open")}
                      <ArrowRight data-icon="inline-end" />
                    </Link>
                  </Button>
                ) : null}
              </div>
            </CardAction>
          </CardHeader>
          <CardContent>
            {latestRecord ? (
              <WaveformViewer
                recordId={latestRecord.id}
                leads={latestRecord.leads}
                analysis={latestCompleted}
                height={160}
                compact
                className="eh-reveal"
              />
            ) : (
              <EmptyState
                icon={FilePlus2}
                title={t("dashboard.waveform.emptyTitle")}
                description={t("dashboard.waveform.emptyDesc")}
                className="border-0 bg-transparent py-4"
              >
                <Button size="sm" onClick={openPicker}>
                  {t("dashboard.recent.emptyAction")}
                </Button>
              </EmptyState>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={formatsOpen} onOpenChange={setFormatsOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("dashboard.formats.title")}</DialogTitle>
            <DialogDescription>{t("dashboard.formats.description")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {FORMAT_GROUPS.map((group) => (
              <section key={group.key}>
                <h3 className="eh-caption mb-2 text-muted-foreground">
                  {t(`dashboard.formats.groups.${group.key}`)}
                </h3>
                <ul className="space-y-1.5">
                  {group.items.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3 text-sm"
                    >
                      <span>{t(`dashboard.formats.items.${item.id}`)}</span>
                      <Badge
                        variant={item.status === "supported" ? "secondary" : "outline"}
                        className={
                          item.status === "supported"
                            ? "shrink-0 font-normal"
                            : "shrink-0 font-normal text-muted-foreground"
                        }
                      >
                        {t(`dashboard.formats.status.${item.status}`)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <p className="eh-caption text-muted-foreground">
            {t("dashboard.formats.note")}
          </p>
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setFormatsOpen(false)}>
              {t("common.close")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
