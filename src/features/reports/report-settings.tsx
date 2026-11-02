import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  FileText,
  Image as ImageIcon,
  Loader2,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { cn } from "cn";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { RecordSummary } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import type { ReportFormat, ReportTemplate } from "./types";

interface ReportSettingsProps {
  record: RecordSummary | null;
  format: ReportFormat;
  template: ReportTemplate;
  redact: boolean;
  onFormatChange: (format: ReportFormat) => void;
  onTemplateChange: (template: ReportTemplate) => void;
  onRedactChange: (redact: boolean) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  canGenerate: boolean;
  errorText: string | null;
}

const FORMAT_OPTIONS: { value: ReportFormat; icon: typeof FileText }[] = [
  { value: "pdf", icon: FileText },
  { value: "png", icon: ImageIcon },
];

const TEMPLATE_OPTIONS: ReportTemplate[] = ["simple", "detailed", "doctor"];

export function ReportSettings({
  record,
  format,
  template,
  redact,
  onFormatChange,
  onTemplateChange,
  onRedactChange,
  onGenerate,
  isGenerating,
  canGenerate,
  errorText,
}: ReportSettingsProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const status = record?.analysisStatus ?? "none";

  return (
    <section className="space-y-4" aria-labelledby="report-settings-heading">
      <h3 id="report-settings-heading" className="text-sm font-medium">
        {t("reports.composer.settings")}
      </h3>

      {record ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-subtle/40 px-3 py-2">
          <div className="min-w-0">
            <p className="eh-caption text-muted-foreground">
              {t("reports.composer.current")}
            </p>
            <p className="truncate text-sm font-medium">
              {formatDateTime(record.recordedAt, locale)}
              {record.device.model ? (
                <span className="font-normal text-muted-foreground">
                  {" · "}
                  {record.device.model}
                </span>
              ) : null}
            </p>
          </div>
          <Button asChild size="xs" variant="ghost">
            <Link to={`/records/${record.id}`}>
              {t("reports.composer.openRecord")}
            </Link>
          </Button>
        </div>
      ) : null}

      {record && status === "none" ? (
        <Alert>
          <ShieldAlert />
          <AlertTitle>{t("reports.composer.analysisStatus.none")}</AlertTitle>
          <AlertDescription>
            <p>{t("reports.composer.needsAnalysis")}</p>
            <Button asChild size="xs" variant="outline" className="mt-2">
              <Link to={`/records/${record.id}`}>
                {t("reports.composer.openRecord")}
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {record && (status === "queued" || status === "running") ? (
        <Alert>
          <Loader2 className="animate-spin" />
          <AlertTitle>
            {t(`reports.composer.analysisStatus.${status}`)}
          </AlertTitle>
          <AlertDescription>
            <Link to={`/records/${record.id}`} className="underline">
              {t("reports.composer.openRecord")}
            </Link>
          </AlertDescription>
        </Alert>
      ) : null}

      {record && status === "failed" ? (
        <Alert>
          <AlertTriangle className="text-warning" />
          <AlertTitle>{t("reports.composer.analysisStatus.failed")}</AlertTitle>
          <AlertDescription>{t("reports.composer.failedAnalysis")}</AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-1.5">
        <span className="eh-caption text-muted-foreground">
          {t("reports.composer.format")}
        </span>
        <div className="flex gap-1.5" role="group" aria-label={t("reports.composer.format")}>
          {FORMAT_OPTIONS.map((option) => {
            const Icon = option.icon;
            const active = format === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                onClick={() => onFormatChange(option.value)}
                className={cn(
                  "flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg border text-sm transition-colors",
                  active
                    ? "border-primary bg-accent-soft font-medium text-foreground"
                    : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <Icon className="size-4" aria-hidden="true" />
                {t(`reports.composer.formats.${option.value}`)}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-1.5">
        <span className="eh-caption text-muted-foreground">
          {t("reports.composer.template")}
        </span>
        <Select
          value={template}
          onValueChange={(value) => onTemplateChange(value as ReportTemplate)}
          disabled={format === "png"}
        >
          <SelectTrigger className="w-full" aria-label={t("reports.composer.template")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEMPLATE_OPTIONS.map((value) => (
              <SelectItem key={value} value={value}>
                {t(`reports.composer.templates.${value}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="eh-caption text-muted-foreground">
          {format === "png"
            ? t("reports.composer.pngHint")
            : t(`reports.composer.templateHints.${template}`)}
        </p>
      </div>

      <div className="flex items-start justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("reports.composer.redact")}</p>
          <p className="eh-caption text-muted-foreground">
            {t("reports.composer.redactHint")}
          </p>
        </div>
        <Switch
          checked={redact}
          onCheckedChange={onRedactChange}
          aria-label={t("reports.composer.redact")}
        />
      </div>

      {!redact ? (
        <p className="flex items-start gap-1.5 text-xs text-warning">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {t("reports.composer.redactWarning")}
        </p>
      ) : null}

      {errorText ? (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>{t("reports.composer.errorTitle")}</AlertTitle>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}

      <Button
        className="w-full"
        onClick={onGenerate}
        disabled={!canGenerate || isGenerating || !record}
      >
        {isGenerating ? (
          <Loader2 data-icon="inline-start" className="animate-spin" />
        ) : (
          <Sparkles data-icon="inline-start" />
        )}
        {isGenerating
          ? format === "pdf"
            ? t("reports.composer.generatingPdf")
            : t("reports.composer.generatingPng")
          : t("reports.composer.generate")}
      </Button>
    </section>
  );
}
