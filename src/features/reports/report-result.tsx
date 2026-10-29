import { useTranslation } from "react-i18next";
import { CheckCircle2, Download, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatBytes, reportFileUrl } from "./api";
import type { ReportSummary } from "./types";

interface ReportResultProps {
  report: ReportSummary;
}

export function ReportResult({ report }: ReportResultProps) {
  const { t } = useTranslation();
  const url = reportFileUrl(report.downloadUrl);
  const isPdf = report.format === "pdf";
  const templateLabel = t(`reports.composer.templates.${report.template}`, {
    defaultValue: String(report.template),
  });

  return (
    <Card size="sm" className="border-success/30">
      <CardContent className="space-y-3 py-1">
        <div className="flex items-start gap-2.5">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-sm font-medium">{t("reports.composer.successTitle")}</p>
            <p className="eh-caption break-all text-muted-foreground">
              {t("reports.composer.successDesc", {
                fileName: report.fileName,
                size: formatBytes(report.size),
                template: templateLabel,
              })}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <a href={url} download={report.fileName}>
              <Download data-icon="inline-start" />
              {t("reports.composer.download")}
            </a>
          </Button>
          {isPdf ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => window.open(url, "_blank", "noopener,noreferrer")}
            >
              <ExternalLink data-icon="inline-start" />
              {t("reports.composer.openPdf")}
            </Button>
          ) : null}
        </div>

        {!isPdf ? (
          <img
            src={url}
            alt={t("reports.composer.previewAlt")}
            className="mx-auto max-h-[420px] w-auto max-w-full rounded-lg border border-border"
            loading="lazy"
          />
        ) : null}
      </CardContent>
    </Card>
  );
}
