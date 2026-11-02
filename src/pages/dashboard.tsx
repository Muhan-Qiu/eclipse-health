import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  BookOpen,
  FilePlus2,
  FlaskConical,
  LayoutGrid as LayoutGridIcon,
  LoaderCircle,
  Plus,
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
import { WidgetCard } from "@/features/modules/widgets/widget-card";
import { useModuleWidgets } from "@/features/modules/widgets/use-widgets";
import { CardFormDialog } from "@/features/dashboard-cards/card-form-dialog";
import { CardDraftCard } from "@/features/dashboard-cards/draft-card";
import { CustomCard } from "@/features/dashboard-cards/custom-card";
import {
  useCardDrafts,
  useCardTemplates,
  useConfirmCardDraft,
  useCreateDashboardCard,
  useDashboardCards,
  useDeleteDashboardCard,
  useDiscardCardDraft,
} from "@/features/dashboard-cards/use-dashboard-cards";
import { autoCardTitle } from "@/features/dashboard-cards/types";
import type {
  CardFields,
  DashboardCard,
} from "@/features/dashboard-cards/types";
import {
  LayoutGrid,
  LayoutToolbar,
} from "@/features/layout/layout-editor";
import {
  customCardLayoutId,
  customCardWidth,
  defaultLayout,
  exportLayoutJson,
  importLayoutJson,
  isCoreCardId,
  LayoutError,
  loadLayout,
  mergeLayout,
  saveLayout,
  widgetLayoutId,
  widgetSizeWidth,
  type CoreCardId,
  type LayoutItem,
} from "@/features/layout/layout";
import { HealthScoreGrid } from "@/features/scores/health-score-grid";
import { SuggestionCard } from "@/features/scores/suggestion-card";
import { HealthSummaryCard } from "@/features/scores/health-summary-card";
import {
  useAnalysis,
  useHealthScores,
  useHealthSuggestions,
  useImportSample,
  useMembers,
  useRecentAnalyses,
  useRecords,
} from "@/lib/api/queries";
import { ApiError, useMock } from "@/lib/api/client";
import { cn } from "cn";
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

const CORE_TITLE_KEYS: Record<CoreCardId, string> = {
  scores: "dashboard.scores.title",
  suggestions: "dashboard.suggestions.title",
  "health-summary": "dashboard.healthSummary.title",
  recent: "dashboard.recent.title",
  metrics: "dashboard.metrics.title",
  waveform: "dashboard.waveform.title",
};

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
    <Card className="eh-lift h-full gap-0 p-5">
      <div
        className="flex size-9 items-center justify-center rounded-lg bg-accent-soft text-primary"
        aria-hidden="true"
      >
        <Icon className="size-4" />
      </div>
      <h2 className="eh-h3 mt-4">{title}</h2>
      <p className="eh-small mt-1.5 flex-1 text-muted-foreground">{description}</p>
      <div className="mt-auto pt-4">{children}</div>
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
    <Card className="eh-lift">
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

  const widgetsQuery = useModuleWidgets();
  const membersQuery = useMembers();
  const memberId = membersQuery.data?.[0]?.id;
  const cardsQuery = useDashboardCards(memberId);
  const templatesQuery = useCardTemplates();
  const draftsQuery = useCardDrafts(memberId);
  const createCard = useCreateDashboardCard(memberId);
  const deleteCard = useDeleteDashboardCard(memberId);
  const confirmDraft = useConfirmCardDraft(memberId);
  const discardDraft = useDiscardCardDraft(memberId);
  const [cardFormOpen, setCardFormOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DashboardCard | null>(null);
  const [savedLayout, setSavedLayout] = useState<LayoutItem[]>(() => loadLayout());
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<LayoutItem[]>([]);
  const [layoutError, setLayoutError] = useState<string | null>(null);

  const widgetInputs = useMemo(
    () =>
      widgetsQuery.widgets.map((widget) => ({
        id: widgetLayoutId(widget.moduleId, widget.id),
        title: widget.title,
        width: widgetSizeWidth(widget.size),
      })),
    [widgetsQuery.widgets],
  );

  const widgetById = useMemo(() => {
    const map = new Map<string, (typeof widgetsQuery.widgets)[number]>();
    for (const widget of widgetsQuery.widgets) {
      map.set(widgetLayoutId(widget.moduleId, widget.id), widget);
    }
    return map;
  }, [widgetsQuery.widgets]);

  const customInputs = useMemo(
    () =>
      cardsQuery.cards.map((card) => ({
        id: customCardLayoutId(card.id),
        title: card.title,
        width: customCardWidth(card.view),
      })),
    [cardsQuery.cards],
  );

  const cardById = useMemo(() => {
    const map = new Map<string, DashboardCard>();
    for (const card of cardsQuery.cards) {
      map.set(customCardLayoutId(card.id), card);
    }
    return map;
  }, [cardsQuery.cards]);

  // 任一列表未就绪时保留对应的已保存卡片顺序，就绪后再清理已删除的卡片。
  const layout = useMemo(
    () =>
      mergeLayout(savedLayout, widgetInputs, customInputs, {
        widgetsReady: widgetsQuery.isSuccess,
        customCardsReady: cardsQuery.isSuccess,
      }),
    [
      savedLayout,
      widgetInputs,
      customInputs,
      widgetsQuery.isSuccess,
      cardsQuery.isSuccess,
    ],
  );

  const startEditing = () => {
    setDraft(layout);
    setLayoutError(null);
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setDraft([]);
    setLayoutError(null);
  };

  const saveDraft = () => {
    saveLayout(draft);
    setSavedLayout(draft);
    setEditing(false);
    setLayoutError(null);
  };

  const resetDraft = () => {
    const next = mergeLayout(defaultLayout(), widgetInputs, customInputs, {
      widgetsReady: widgetsQuery.isSuccess,
      customCardsReady: cardsQuery.isSuccess,
    });
    saveLayout(next);
    setSavedLayout(next);
    setDraft(next);
    setLayoutError(null);
  };

  const exportDraft = () => {
    const blob = new Blob([exportLayoutJson(draft)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "eh-dashboard-layout.json";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const importDraft = (file: File) => {
    void file
      .text()
      .then((text) => {
        try {
          const parsed = importLayoutJson(text);
          const next = mergeLayout(parsed, widgetInputs, customInputs, {
            widgetsReady: widgetsQuery.isSuccess,
            customCardsReady: cardsQuery.isSuccess,
          });
          setDraft(next);
          setLayoutError(null);
        } catch (error) {
          const code = error instanceof LayoutError ? error.code : "invalid_shape";
          setLayoutError(t(`dashboard.layout.errors.${code}`));
        }
      })
      .catch(() => {
        setLayoutError(t("dashboard.layout.errors.invalid_json"));
      });
  };

  const titleFor = (item: LayoutItem) => {
    if (item.kind === "core-card" && isCoreCardId(item.id)) {
      return t(CORE_TITLE_KEYS[item.id]);
    }
    if (item.kind === "custom-card") {
      return cardById.get(item.id)?.title ?? item.title;
    }
    return widgetById.get(item.id)?.title ?? item.title;
  };

  const askAssistantForCard = (fields: CardFields) => {
    setCardFormOpen(false);
    const prompt = t("dashboard.customCards.assistantPrompt", {
      kind: t(`dashboard.customCards.kinds.${fields.kind}`),
      aggregation: t(
        `dashboard.customCards.aggregations.${fields.aggregation}`,
      ),
      view: t(`dashboard.customCards.views.${fields.view}`),
      days: fields.windowDays,
      title:
        fields.title ||
        autoCardTitle(fields.kind, fields.aggregation, t),
    });
    navigate(`/assistant?prompt=${encodeURIComponent(prompt)}&new=1`);
  };

  const submitCard = (fields: CardFields) => {
    createCard.mutate(fields, { onSuccess: () => setCardFormOpen(false) });
  };

  const cardFormError =
    createCard.error instanceof ApiError
      ? createCard.error.message
      : createCard.error
        ? t("dashboard.customCards.createFailed")
        : null;

  const requestDeleteCard = (card: DashboardCard) => setDeleteTarget(card);

  const confirmDeleteCard = () => {
    if (!deleteTarget) return;
    deleteCard.mutate(deleteTarget.id, {
      onSuccess: () => setDeleteTarget(null),
    });
  };

  const renderRecentCard = () => (
    <Card className="eh-lift">
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
  );

  const renderWaveformCard = () => (
    <Card className="eh-lift">
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
  );

  const renderLayoutItem = (item: LayoutItem): ReactNode => {
    if (item.kind === "module-widget") {
      const widget = widgetById.get(item.id);
      return widget ? (
        <WidgetCard widget={widget} animate={!editing} />
      ) : null;
    }
    if (item.kind === "custom-card") {
      const card = cardById.get(item.id);
      if (!card) return null;
      return (
        <CustomCard
          card={card}
          data={card.data}
          loading={cardsQuery.isLoading}
          error={cardsQuery.isError}
          onRetry={() => void cardsQuery.refetch()}
          onDelete={() => requestDeleteCard(card)}
        />
      );
    }
    if (!isCoreCardId(item.id)) return null;
    switch (item.id) {
      case "scores":
        return (
          <HealthScoreGrid
            scores={scoresQuery.data}
            loading={scoresQuery.isLoading}
            error={scoresQuery.isError}
          />
        );
      case "suggestions":
        return (
          <SuggestionCard
            suggestions={suggestionsQuery.data}
            loading={suggestionsQuery.isLoading}
            error={suggestionsQuery.isError}
          />
        );
      case "health-summary":
        return <HealthSummaryCard />;
      case "recent":
        return renderRecentCard();
      case "metrics":
        return (
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
        );
      case "waveform":
        return renderWaveformCard();
    }
  };

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
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setCardFormOpen(true)}
            disabled={editing}
          >
            <Plus data-icon="inline-start" />
            {t("dashboard.customCards.add")}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={startEditing}
            disabled={editing}
            aria-pressed={editing}
          >
            <LayoutGridIcon data-icon="inline-start" />
            {t("dashboard.layout.edit")}
          </Button>
        </div>
      </header>

      {draftsQuery.drafts.length > 0 && !editing ? (
        <section
          aria-label={t("dashboard.customCards.draftsTitle")}
          className="mt-6"
        >
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="eh-h3">{t("dashboard.customCards.draftsTitle")}</h2>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void draftsQuery.refetch()}
            >
              <RefreshCw data-icon="inline-start" />
              {t("common.retry")}
            </Button>
          </div>
          <div className="eh-grid">
            {draftsQuery.drafts.map((item) => (
              <div
                key={item.id}
                className={cn(
                  "min-w-0",
                  item.card.view === "line" || item.card.view === "bar"
                    ? "desk:col-span-4 xl:col-span-6"
                    : "desk:col-span-2 xl:col-span-3",
                )}
              >
                <CardDraftCard
                  draft={item}
                  confirming={
                    confirmDraft.isPending && confirmDraft.variables === item.id
                  }
                  discarding={
                    discardDraft.isPending && discardDraft.variables === item.id
                  }
                  onConfirm={() => confirmDraft.mutate(item.id)}
                  onDiscard={() => discardDraft.mutate(item.id)}
                />
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/* 评分/建议/指标/波形、模块卡片与自定义卡片统一进 12 列布局。 */}
      <section aria-label={t("dashboard.layout.aria")} className="mt-6">
        {editing ? (
          <LayoutToolbar
            onSave={saveDraft}
            onCancel={cancelEditing}
            onReset={resetDraft}
            onExport={exportDraft}
            onImport={importDraft}
            error={layoutError}
          />
        ) : null}
        <LayoutGrid
          items={editing ? draft : layout}
          editing={editing}
          onChange={setDraft}
          renderItem={renderLayoutItem}
          titleFor={titleFor}
          className={cn(!editing ? "eh-stagger" : "mt-4")}
        />
        {widgetsQuery.isError && !useMock ? (
          <Card className="mt-4">
            <CardContent className="flex flex-wrap items-center justify-between gap-3 px-4">
              <div className="flex min-w-0 items-start gap-2">
                <RefreshCw
                  className="mt-0.5 size-4 shrink-0 text-destructive"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    {t("moduleUi.widgets.loadError")}
                  </p>
                  <p className="eh-caption text-muted-foreground">
                    {t("moduleUi.widgets.loadErrorDesc")}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={widgetsQuery.refetch}
              >
                <RefreshCw data-icon="inline-start" />
                {t("common.retry")}
              </Button>
            </CardContent>
          </Card>
        ) : null}
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

      <CardFormDialog
        open={cardFormOpen}
        onOpenChange={setCardFormOpen}
        templates={templatesQuery.templates}
        submitting={createCard.isPending}
        error={cardFormError}
        onSubmit={submitCard}
        onAskAssistant={askAssistantForCard}
      />

      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("dashboard.customCards.deleteTitle")}</DialogTitle>
            <DialogDescription>
              {t("dashboard.customCards.deleteDesc", {
                title: deleteTarget?.title ?? "",
              })}
            </DialogDescription>
          </DialogHeader>
          {deleteCard.error ? (
            <p className="eh-caption text-destructive" role="alert">
              {deleteCard.error instanceof ApiError
                ? deleteCard.error.message
                : t("dashboard.customCards.deleteFailed")}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDeleteTarget(null)}
            >
              {t("dashboard.customCards.cancel")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmDeleteCard}
              disabled={deleteCard.isPending}
            >
              {deleteCard.isPending
                ? t("dashboard.customCards.deleting")
                : t("dashboard.customCards.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
