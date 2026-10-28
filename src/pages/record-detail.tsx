import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, FileSearch, ShieldAlert, Trash2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AnalysisPanel } from "@/components/records/analysis-panel";
import { BeatDetails } from "@/components/records/beat-details";
import { WaveformViewer } from "@/components/records/waveform-viewer";
import { DemoBadge } from "@/components/common/demo-badge";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import type { Beat } from "@/lib/api/types";
import {
  queryKeys,
  useAnalysis,
  useDeleteRecord,
  useEngineStatus,
  useRecord,
  useRecordAnalyses,
  useStartAnalysis,
} from "@/lib/api/queries";
import { toRecordSummary } from "@/lib/api/adapters";
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
} from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { useTagLabel } from "@/lib/tags";

export function RecordDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const tagLabel = useTagLabel();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const recordQuery = useRecord(id);
  const analysesQuery = useRecordAnalyses(id);
  const engineQuery = useEngineStatus();
  const startMutation = useStartAnalysis(id);
  const deleteMutation = useDeleteRecord(id);

  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [selectedBeat, setSelectedBeat] = useState<Beat | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const latest = analysesQuery.data?.items[0] ?? null;
  const analysisId = selectedAnalysisId ?? latest?.id;
  const analysisQuery = useAnalysis(analysisId, Boolean(analysisId));

  useEffect(() => {
    setSelectedBeat(null);
  }, [analysisId]);

  useEffect(() => {
    if (analysisQuery.data?.status === "completed" && id) {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.recordAnalyses(id),
      });
    }
  }, [analysisQuery.data?.status, id, queryClient]);

  const record = recordQuery.data;
  const summary = useMemo(
    () => (record ? toRecordSummary(record) : null),
    [record],
  );
  const completedAnalysis = useMemo(
    () => (analysisQuery.data?.status === "completed" ? analysisQuery.data : null),
    [analysisQuery.data],
  );

  const backButton = (
    <Button variant="outline" size="sm" asChild>
      <Link to="/records">
        <ArrowLeft data-icon="inline-start" />
        {t("recordDetail.backToRecords")}
      </Link>
    </Button>
  );

  if (recordQuery.isLoading) {
    return (
      <>
        <PageHeader
          eyebrow={t("recordDetail.eyebrow")}
          title={t("common.loading")}
          actions={backButton}
        />
        <div className="eh-grid">
          <Card className="desk:col-span-5 xl:col-span-8">
            <CardContent className="space-y-3">
              <Skeleton className="h-72 w-full" />
            </CardContent>
          </Card>
          <Card className="desk:col-span-3 xl:col-span-4">
            <CardContent className="space-y-4">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-10 w-24" />
              <Skeleton className="h-4 w-40" />
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  if (recordQuery.isError || !record || !summary) {
    return (
      <>
        <PageHeader
          eyebrow={t("recordDetail.eyebrow")}
          title={t("recordDetail.notFound")}
          actions={backButton}
        />
        <EmptyState
          icon={FileSearch}
          title={t("recordDetail.notFound")}
          description={t("recordDetail.notFoundDesc")}
        >
          {backButton}
        </EmptyState>
      </>
    );
  }

  const removeRecord = () =>
    deleteMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success(t("recordDetail.deleted"));
        navigate("/records");
      },
      onError: (error) => {
        toast.error(t("recordDetail.deleteFailed"), {
          description: error instanceof Error ? error.message : undefined,
        });
      },
    });

  const startAnalysis = () =>
    startMutation.mutate(
      {
        engine: "cardia",
        options: {
          allowShortRecord: (record.durationSec ?? 0) < 60,
        },
      },
      {
        onSuccess: (response) => {
          setSelectedAnalysisId(response.analysisId);
          setSelectedBeat(null);
        },
      },
    );

  return (
    <>
      <PageHeader
        eyebrow={t("recordDetail.eyebrow")}
        title={formatDate(record.capturedAt, locale)}
        description={[
          summary.device.model || t("records.localFile"),
          formatDateTime(record.capturedAt, locale),
          formatDuration(summary.durationSec, locale),
        ].join(" · ")}
        actions={
          <>
            {backButton}
            <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm">
                  <Trash2 data-icon="inline-start" />
                  {t("recordDetail.delete")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t("recordDetail.deleteTitle")}</AlertDialogTitle>
                  <AlertDialogDescription>
                    {t("recordDetail.deleteDesc")}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
                  <AlertDialogAction
                    variant="destructive"
                    onClick={(event) => {
                      event.preventDefault();
                      removeRecord();
                    }}
                    disabled={deleteMutation.isPending}
                  >
                    {deleteMutation.isPending
                      ? t("recordDetail.deleting")
                      : t("recordDetail.delete")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {summary.isDemo ? <DemoBadge /> : null}
        {record.leads.map((lead) => (
          <Badge key={lead} variant="outline" className="font-normal">
            {lead}
          </Badge>
        ))}
        <Badge variant="secondary" className="font-normal">
          {formatNumber(record.samplingRate ?? 0, locale)} Hz
        </Badge>
        <Badge variant="secondary" className="font-normal">
          {formatDuration(summary.durationSec, locale)}
        </Badge>
        {record.tags.map((tag) => (
          <Badge key={tag} variant="outline" className="font-normal">
            {tagLabel(tag)}
          </Badge>
        ))}
        {record.notes ? (
          <span className="eh-small text-muted-foreground">{record.notes}</span>
        ) : null}
      </div>

      <div className="eh-grid">
        <section className="desk:col-span-5 xl:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle className="eh-h3">{t("waveform.title")}</CardTitle>
              <CardDescription>
                {record.leads.join(" / ")} ·{" "}
                {formatNumber(record.samplingRate ?? 0, locale)} Hz ·{" "}
                {formatDuration(summary.durationSec, locale)}
              </CardDescription>
              <CardAction>
                {summary.isDemo ? <DemoBadge /> : null}
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-3">
              <WaveformViewer
                recordId={record.id}
                leads={record.leads}
                analysis={completedAnalysis}
                selectedBeatIndex={selectedBeat?.index ?? null}
                onBeatSelect={setSelectedBeat}
                height={320}
              />
              <p className="eh-caption flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
                <span>{t("waveform.legend.rPeak")}</span>
                <span>{t("waveform.legend.abnormal")}</span>
                <span>{t("waveform.legend.quality")}</span>
              </p>
              {selectedBeat ? (
                <BeatDetails
                  beat={selectedBeat}
                  fs={record.samplingRate ?? 360}
                  onClose={() => setSelectedBeat(null)}
                />
              ) : (
                <p className="eh-caption text-muted-foreground">
                  {completedAnalysis?.beats.length
                    ? t("waveform.beatHint")
                    : t("waveform.beatHintDisabled")}
                </p>
              )}
            </CardContent>
          </Card>

          <p className="eh-caption mt-3 flex items-start gap-1.5 text-muted-foreground">
            <ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            {t("recordDetail.privacyNote")}
          </p>
        </section>

        <div className="desk:col-span-3 xl:col-span-4">
          <AnalysisPanel
            record={record}
            latest={latest}
            analysis={analysisQuery.data ?? null}
            analysesLoading={analysesQuery.isLoading}
            analysesError={analysesQuery.error}
            analysisLoading={analysisQuery.isLoading}
            analysisError={analysisQuery.error}
            onRetry={() => {
              void analysesQuery.refetch();
              void analysisQuery.refetch();
            }}
            onStart={startAnalysis}
            startPending={startMutation.isPending}
            startError={startMutation.error}
            engine={engineQuery.data}
            engineLoading={engineQuery.isLoading}
            engineError={engineQuery.error}
            onRetryEngine={() => {
              void engineQuery.refetch();
            }}
          />
        </div>
      </div>
    </>
  );
}
