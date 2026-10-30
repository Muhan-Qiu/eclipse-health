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
import { PageHeader } from "@/components/common/page-header";
import { RecordListSkeleton } from "@/components/common/loading";
import { Sparkline } from "@/components/common/sparkline";
import { WaveformViewer } from "@/components/records/waveform-viewer";
import { RecordRow } from "@/components/records/record-row";
import { useImport } from "@/components/import/import-provider";
import { measurementsByCode } from "@/components/records/measurement-list";
import { WidgetGrid } from "@/features/modules/widgets/widget-grid";
import {
  useAnalysis,
  useImportSample,
  useRecentAnalyses,
  useRecords,
} from "@/lib/api/queries";
import type { AnalysisResult, RecordSummary } from "@/lib/api/types";
import { formatFullDate, formatNumber, greetingKey } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";

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
    <Card className="gap-0 p-5">
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
  children,
}: {
  label: string;
  value: string;
  unit: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-4 border-b border-border pb-3 last:border-0 last:pb-0">
      <div>
        <p className="eh-caption text-muted-foreground">{label}</p>
        <p className="mt-1 flex items-baseline gap-1.5">
          <span className="eh-num text-3xl leading-9 font-medium">{value}</span>
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
    <div className="divide-y divide-border">
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
    <Card className="desk:col-span-3 xl:col-span-5">
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
              value={
                heartRate === null
                  ? "—"
                  : formatNumber(heartRate, locale, { maximumFractionDigits: 0 })
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
              value={
                rmssd === null
                  ? "—"
                  : formatNumber(rmssd, locale, { maximumFractionDigits: 1 })
              }
              unit={t("dashboard.metrics.ms")}
            />
            <MetricRow
              label={t("dashboard.metrics.abnormal")}
              value={formatNumber(abnormal, locale, { maximumFractionDigits: 1 })}
              unit={t("dashboard.metrics.percent")}
            />
            <MetricRow
              label={t("dashboard.metrics.quality")}
              value={
                quality === null
                  ? "—"
                  : formatNumber(quality * 100, locale, {
                      maximumFractionDigits: 0,
                    })
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

  const recentQuery = useRecords({
    limit: 5,
    recordType: "org.eclipsehealth.ecg",
  });
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
      <PageHeader
        eyebrow={t("dashboard.eyebrow")}
        title={t(greetingKey(now))}
        description={t("dashboard.description")}
        actions={
          <p className="eh-caption text-muted-foreground">
            {formatFullDate(now, locale)}
          </p>
        }
      />

      <section className="grid gap-4 md:grid-cols-3" aria-label={t("dashboard.eyebrow")}>
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

      <WidgetGrid />

      <div className="eh-grid mt-6">
        <Card className="desk:col-span-5 xl:col-span-7">
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

        <Card className="desk:col-span-8 xl:col-span-12">
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
