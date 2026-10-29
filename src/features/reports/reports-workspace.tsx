import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/common/page-header";
import { ApiError } from "@/lib/api/error";
import { useRecords } from "@/lib/api/queries";
import { generateReport, listReports, reportHistoryKey } from "./api";
import { RecordPicker } from "./record-picker";
import { ReportHistory } from "./report-history";
import { ReportResult } from "./report-result";
import { ReportSettings } from "./report-settings";
import type { ReportFormat, ReportSummary, ReportTemplate } from "./types";

const ERROR_KEYS: Record<string, string> = {
  analysis_required: "reports.errors.analysisRequired",
  unknown_template: "reports.errors.unknownTemplate",
  unsupported_format: "reports.errors.unsupportedFormat",
  report_font_missing: "reports.errors.fontMissing",
  network_error: "reports.errors.network",
  timeout: "reports.errors.timeout",
  validation_error: "reports.errors.validation",
};

function errorText(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    const key = ERROR_KEYS[error.code];
    if (key) return t(key);
    return error.message || t("reports.composer.errorUnknown");
  }
  return t("reports.composer.errorUnknown");
}

export function ReportsWorkspace() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [template, setTemplate] = useState<ReportTemplate>("detailed");
  const [redact, setRedact] = useState(true);
  const [lastReport, setLastReport] = useState<ReportSummary | null>(null);

  const recordsQuery = useRecords({
    limit: 50,
    recordType: "org.eclipsehealth.ecg",
  });
  const records = recordsQuery.data?.items ?? [];
  const total = recordsQuery.data?.total ?? 0;

  useEffect(() => {
    if (records.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !records.some((record) => record.id === selectedId)) {
      setSelectedId(records[0].id);
    }
  }, [records, selectedId]);

  const selected = records.find((record) => record.id === selectedId) ?? null;

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return records;
    return records.filter((record) => {
      const haystack = [
        record.recordedAt,
        record.device.model,
        record.id,
        record.leads.join(" "),
        record.tags.join(" "),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [records, search]);

  const historyQuery = useQuery({
    queryKey: reportHistoryKey(selectedId ?? ""),
    queryFn: () => listReports(selectedId ?? ""),
    enabled: Boolean(selectedId),
    retry: 1,
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      generateReport(selectedId ?? "", { format, template, redact }),
    onSuccess: (report) => {
      setLastReport(report);
      if (selectedId) {
        void queryClient.invalidateQueries({
          queryKey: reportHistoryKey(selectedId),
        });
      }
    },
  });

  useEffect(() => {
    setLastReport(null);
    generateMutation.reset();
    // generateMutation 是稳定的 mutation 对象，只需在选中记录变化时清空状态。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const status = selected?.analysisStatus ?? "none";
  const canGenerate =
    Boolean(selectedId) &&
    status !== "none" &&
    status !== "queued" &&
    status !== "running";

  return (
    <>
      <PageHeader
        eyebrow={t("reports.composer.pageEyebrow")}
        title={t("reports.title")}
        description={t("reports.description")}
        actions={
          <Badge variant="outline" className="font-normal text-muted-foreground">
            PDF · PNG · {t("common.localOnly")}
          </Badge>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-start">
        <div className="space-y-4">
          <Card>
            <CardHeader className="gap-1">
              <CardTitle>{t("reports.composer.title")}</CardTitle>
              <CardDescription>{t("reports.composer.description")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <RecordPicker
                records={filtered}
                total={total}
                selectedId={selectedId}
                onSelect={setSelectedId}
                search={search}
                onSearch={setSearch}
                isLoading={recordsQuery.isLoading}
                isError={recordsQuery.isError}
                onRetry={() => void recordsQuery.refetch()}
              />
              <ReportSettings
                record={selected}
                format={format}
                template={template}
                redact={redact}
                onFormatChange={setFormat}
                onTemplateChange={setTemplate}
                onRedactChange={setRedact}
                onGenerate={() => generateMutation.mutate()}
                isGenerating={generateMutation.isPending}
                canGenerate={canGenerate}
                errorText={
                  generateMutation.isError
                    ? errorText(generateMutation.error, t)
                    : null
                }
              />
            </CardContent>
          </Card>

          {lastReport ? <ReportResult report={lastReport} /> : null}
        </div>

        <ReportHistory
          record={selected}
          reports={historyQuery.data?.items ?? []}
          isLoading={historyQuery.isLoading}
          isError={historyQuery.isError}
          onRetry={() => void historyQuery.refetch()}
          onDeleted={(reportId) => {
            if (lastReport?.reportId === reportId) setLastReport(null);
          }}
        />
      </div>
    </>
  );
}
