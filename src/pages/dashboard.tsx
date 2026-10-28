import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight,
  BookOpen,
  FilePlus2,
  FlaskConical,
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
import { DemoBadge } from "@/components/common/demo-badge";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { RecordListSkeleton } from "@/components/common/loading";
import { Sparkline } from "@/components/common/sparkline";
import { WaveThumbnail } from "@/components/common/wave-thumbnail";
import { RecordRow } from "@/components/records/record-row";
import { api } from "@/lib/api/client";
import {
  formatFullDate,
  formatNumber,
  greetingKey,
} from "@/lib/format";
import { intlLocale } from "@/lib/i18n";

/** 界面演示用合成指标，非真实记录、非诊断结论。 */
const DEMO_METRICS = {
  heartRateBpm: 62,
  hrvRmssdMs: 42,
  abnormalBeatRatio: 0.004,
  heartRateSeries: [58, 61, 60, 63, 59, 62, 62],
};

const FORMAT_GROUPS = [
  { key: "standard", items: ["wfdb", "csv", "float32"] },
  { key: "wearable", items: ["apple", "samsung", "huawei"] },
  { key: "hospital", items: ["scp"] },
] as const;

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
      <p className="eh-small mt-1.5 flex-1 text-muted-foreground">
        {description}
      </p>
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
  const { data, isLoading, isError } = useQuery({
    queryKey: ["records", "recent"],
    queryFn: () => api.records.list({ limit: 3 }),
  });

  if (isLoading) return <RecordListSkeleton rows={3} />;
  if (isError) {
    return (
      <p className="eh-small px-5 py-8 text-center text-muted-foreground">
        {t("common.loadError")}
      </p>
    );
  }
  if (!data || data.length === 0) {
    return (
      <div className="px-5 py-6">
        <EmptyState
          icon={FilePlus2}
          title={t("dashboard.recent.emptyTitle")}
          description={t("dashboard.recent.emptyDesc")}
          className="border-0 bg-transparent py-6"
        >
          <Button
            size="sm"
            onClick={() => toast(t("dashboard.guide.importPending"))}
          >
            {t("dashboard.recent.emptyAction")}
          </Button>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="divide-y divide-border">
      {data.map((record) => (
        <RecordRow key={record.id} record={record} />
      ))}
    </div>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [formatsOpen, setFormatsOpen] = useState(false);
  const now = new Date();

  const notifyImportPending = () =>
    toast(t("dashboard.guide.importPending"));

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

      <section
        className="grid gap-4 md:grid-cols-3"
        aria-label={t("dashboard.eyebrow")}
      >
        <GuideCard
          icon={FilePlus2}
          title={t("dashboard.guide.importTitle")}
          description={t("dashboard.guide.importDesc")}
        >
          <Button size="sm" onClick={notifyImportPending}>
            {t("dashboard.guide.importAction")}
            <ArrowRight data-icon="inline-end" />
          </Button>
        </GuideCard>

        <GuideCard
          icon={BookOpen}
          title={t("dashboard.guide.exampleTitle")}
          description={t("dashboard.guide.exampleDesc")}
        >
          <Button variant="ghost" size="sm" className="-ml-2.5" asChild>
            <Link to="/records">
              {t("dashboard.guide.exampleAction")}
              <ArrowRight data-icon="inline-end" />
            </Link>
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

      <div className="eh-grid mt-6">
        <Card className="desk:col-span-5 xl:col-span-7">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("dashboard.recent.title")}
            </CardTitle>
            <CardDescription>
              {t("dashboard.recent.description")}
            </CardDescription>
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

        <Card className="desk:col-span-3 xl:col-span-5">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("dashboard.metrics.title")}
            </CardTitle>
            <CardDescription>{t("dashboard.metrics.range")}</CardDescription>
            <CardAction>
              <DemoBadge />
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-4">
            <MetricRow
              label={t("dashboard.metrics.heartRate")}
              value={formatNumber(DEMO_METRICS.heartRateBpm, locale)}
              unit={t("dashboard.metrics.bpm")}
            >
              <Sparkline
                values={DEMO_METRICS.heartRateSeries}
                ariaLabel={t("common.demoNote")}
              />
            </MetricRow>
            <MetricRow
              label={t("dashboard.metrics.hrv")}
              value={formatNumber(DEMO_METRICS.hrvRmssdMs, locale)}
              unit={t("dashboard.metrics.ms")}
            />
            <MetricRow
              label={t("dashboard.metrics.abnormal")}
              value={formatNumber(DEMO_METRICS.abnormalBeatRatio * 100, locale, {
                maximumFractionDigits: 1,
              })}
              unit={t("dashboard.metrics.percent")}
            />
            <p className="eh-caption text-muted-foreground">
              {t("dashboard.metrics.note")}
            </p>
          </CardContent>
        </Card>

        <Card className="desk:col-span-8 xl:col-span-12">
          <CardHeader>
            <CardTitle className="eh-h3">
              {t("dashboard.waveform.title")}
            </CardTitle>
            <CardDescription>
              {t("dashboard.waveform.subtitle")}
            </CardDescription>
            <CardAction>
              <DemoBadge />
            </CardAction>
          </CardHeader>
          <CardContent>
            <WaveThumbnail
              ariaLabel={t("dashboard.waveform.aria")}
              className="h-40"
            />
          </CardContent>
        </Card>
      </div>

      <Dialog open={formatsOpen} onOpenChange={setFormatsOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("dashboard.formats.title")}</DialogTitle>
            <DialogDescription>
              {t("dashboard.formats.description")}
            </DialogDescription>
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
                      key={item}
                      className="flex items-center justify-between gap-3 text-sm"
                    >
                      <span>{t(`dashboard.formats.items.${item}`)}</span>
                      <Badge
                        variant="outline"
                        className="shrink-0 font-normal text-muted-foreground"
                      >
                        {t("common.planned")}
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
