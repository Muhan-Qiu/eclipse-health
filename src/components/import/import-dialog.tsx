import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  FilePlus2,
  FileUp,
  FolderOpen,
  Info,
  Loader2,
  RotateCcw,
  Sparkles,
  Square,
  StopCircle,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/error";
import { useMembers } from "@/lib/api/queries";
import type {
  ImportCommitBody,
  ImportPreview,
  ImportWarning,
} from "@/lib/api/types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { useTagLabel } from "@/lib/tags";
import { formatSeconds } from "@/lib/waveform";
import {
  VENDOR_GUIDES,
  VENDOR_GUIDES_VERSION_NOTE,
} from "@/lib/vendor-import-guides";
import {
  COUNT_ORDER,
  type HealthImportCommitResult,
  type ImportRecordCounts,
  type ImportSourceKind,
} from "./health-import-api";
import type { AgentProposal } from "./import-agent-api";
import type { AgentView } from "./import-provider";

const KNOWN_TAGS = ["morning", "resting", "postExercise", "evening"] as const;
const LEAD_SUGGESTIONS = ["MLII", "I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"];

export interface AgentEventItem {
  id: string;
  kind: "status" | "tool" | "result" | "error";
  name: string;
  detail?: string;
  ok?: boolean;
}

function toLocalInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function warningText(warning: ImportWarning, t: (key: string, options?: Record<string, unknown>) => string): string {
  return t(`imports.warningCodes.${warning.code}`, {
    defaultValue: warning.message || warning.code,
  });
}

function PreviewSignal({ samples }: { samples: number[] }) {
  const path = useMemo(() => {
    if (samples.length < 2) return "";
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const value of samples) {
      if (value < min) min = value;
      if (value > max) max = value;
    }
    const range = max - min || 1;
    const width = 640;
    const height = 120;
    return samples
      .map((value, index) => {
        const x = (index / (samples.length - 1)) * width;
        const y = height - 8 - ((value - min) / range) * (height - 16);
        return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [samples]);

  if (!path) {
    return (
      <div className="flex h-28 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
        —
      </div>
    );
  }

  return (
    <svg
      viewBox="0 0 640 120"
      preserveAspectRatio="none"
      role="img"
      aria-label="preview"
      className="eh-wave-grid h-28 w-full rounded-lg border border-border bg-surface"
    >
      {Array.from({ length: 9 }, (_, index) => (
        <line key={`x-${index}`} x1={index * 80} y1={0} x2={index * 80} y2={120} />
      ))}
      {Array.from({ length: 4 }, (_, index) => (
        <line key={`y-${index}`} x1={0} y1={index * 40} x2={640} y2={index * 40} />
      ))}
      <path
        d={path}
        fill="none"
        stroke="var(--eh-signal)"
        strokeWidth={1.4}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function AgentValue({
  proposal,
  locale,
  t,
}: {
  proposal: AgentProposal;
  locale: string;
  t: (key: string) => string;
}) {
  const value = proposal.value;
  if (proposal.kind === "blood-pressure" && value && typeof value === "object") {
    const pair = value as { systolic?: number; diastolic?: number };
    return (
      <span className="eh-num">
        {formatNumber(pair.systolic ?? 0, locale)}/{formatNumber(pair.diastolic ?? 0, locale)}
      </span>
    );
  }
  if (proposal.kind === "workout" && value && typeof value === "object") {
    const item = value as {
      activity?: string;
      durationSec?: number;
      distanceM?: number;
      energyKcal?: number;
      avgHeartRate?: number;
    };
    return (
      <span className="eh-num">
        {item.activity || t("imports.agent.activity")}
        {item.durationSec ? ` · ${formatSeconds(item.durationSec)}` : ""}
        {item.distanceM ? ` · ${formatNumber(item.distanceM / 1000, locale, { maximumFractionDigits: 2 })} km` : ""}
        {item.energyKcal ? ` · ${formatNumber(item.energyKcal, locale)} kcal` : ""}
        {item.avgHeartRate ? ` · ${formatNumber(item.avgHeartRate, locale)} bpm` : ""}
      </span>
    );
  }
  if (proposal.kind === "hrv" && value && typeof value === "object") {
    const item = value as { metric?: string; value?: number };
    return (
      <span className="eh-num">
        {item.metric || "hrv"} {formatNumber(item.value ?? 0, locale)}
      </span>
    );
  }
  if (typeof value === "number") {
    return <span className="eh-num">{formatNumber(value, locale, { maximumFractionDigits: 2 })}</span>;
  }
  if (typeof value === "string") {
    return <span>{t(`healthData.sleepStages.${value}`) ?? value}</span>;
  }
  return <span>—</span>;
}

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: ImportPreview | null;
  error: ApiError | null;
  busy: boolean;
  committing: boolean;
  commitError: ApiError | null;
  source: ImportSourceKind;
  recordCounts: ImportRecordCounts;
  totalRecords: number;
  result: HealthImportCommitResult | null;
  hasSelection: boolean;
  selectedFiles: string[];
  agent: AgentView | null;
  agentBusy: boolean;
  agentCommitting: boolean;
  onPickSource: (source: ImportSourceKind) => void;
  onChooseFiles: () => void;
  onChooseFilesForAgent: () => void;
  onChooseFolder: () => void;
  onOpenDialog: () => void;
  onStartAgent: () => void;
  onRunAgent: () => void;
  onStopAgent: () => void;
  onToggleAgentKind: (kind: string) => void;
  onSetAgentKinds: (kinds: string[]) => void;
  onCommitAgent: (memberId: string) => void;
  onDone: () => void;
  onCommit: (body: ImportCommitBody) => void;
  onPickAnother: () => void;
}

export function ImportDialog(props: ImportDialogProps) {
  const {
    open,
    onOpenChange,
    preview,
    error,
    busy,
    committing,
    commitError,
    recordCounts,
    totalRecords,
    result,
    hasSelection,
    selectedFiles,
    agent,
    agentBusy,
    agentCommitting,
    onChooseFiles,
    onChooseFilesForAgent,
    onChooseFolder,
    onStartAgent,
    onRunAgent,
    onStopAgent,
    onToggleAgentKind,
    onSetAgentKinds,
    onCommitAgent,
    onDone,
    onCommit,
    onPickAnother,
  } = props;
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const isZh = i18n.language.toLowerCase().startsWith("zh");
  const tagLabel = useTagLabel();
  const membersQuery = useMembers();
  const memberId = membersQuery.data?.[0]?.id ?? "";
  const [samplingRate, setSamplingRate] = useState("");
  const [lead, setLead] = useState("");
  const [unit, setUnit] = useState("mV");
  const [polarity, setPolarity] = useState<"normal" | "inverted">("normal");
  const [capturedAt, setCapturedAt] = useState(() => toLocalInput(new Date()));
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [showGuides, setShowGuides] = useState(
    () =>
      import.meta.env.DEV &&
      new URLSearchParams(window.location.search).get("import") === "guides",
  );

  useEffect(() => {
    if (!preview) return;
    setSamplingRate(preview.samplingRate ? String(preview.samplingRate) : "");
    setLead(preview.leads[0] ?? "");
    setUnit(preview.unit || "mV");
    setPolarity("normal");
    setCapturedAt(toLocalInput(new Date()));
    setTags([]);
    setTagInput("");
    setNotes("");
    setFormError(null);
  }, [preview]);

  const addTag = (value: string) => {
    const cleaned = value.trim().slice(0, 32);
    if (!cleaned) return;
    setTags((current) =>
      current.includes(cleaned) || current.length >= 32
        ? current
        : [...current, cleaned],
    );
    setTagInput("");
  };

  const submit = () => {
    if (!preview) return;
    if (!memberId) {
      setFormError(t("imports.noMember"));
      return;
    }
    const isHealthBundle = totalRecords > 0;
    const rate = Number(samplingRate);
    if (!isHealthBundle && (!Number.isFinite(rate) || rate <= 0)) {
      setFormError(t("imports.errors.invalidSamplingRate"));
      return;
    }
    if (!isHealthBundle && !lead.trim()) {
      setFormError(t("imports.errors.leadRequired"));
      return;
    }
    const captured = new Date(capturedAt);
    if (Number.isNaN(captured.getTime())) {
      setFormError(t("imports.errors.invalidCapturedAt"));
      return;
    }
    setFormError(null);
    onCommit({
      memberId,
      capturedAt: captured.toISOString(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      tags,
      notes: notes.slice(0, 4000),
      parameters: isHealthBundle
        ? {}
        : {
            samplingRate: rate,
            lead: lead.trim(),
            unit,
            polarity,
          },
    });
  };

  const requires = preview?.requires;
  const isHealthBundle = totalRecords > 0;
  const commitDisabled = committing || busy || !preview || !memberId;
  const showPicker =
    !agent && !busy && !error && !preview && !result;
  const createdKinds = COUNT_ORDER.filter(
    (key) => (result?.recordCounts[key] ?? 0) > 0,
  );

  const groups = useMemo(() => {
    const map = new Map<string, AgentProposal[]>();
    for (const item of agent?.proposals ?? []) {
      const list = map.get(item.kind) ?? [];
      list.push(item);
      map.set(item.kind, list);
    }
    return Array.from(map.entries()).sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }, [agent?.proposals]);
  const allKinds = groups.map(([kind]) => kind);
  const allSelected =
    allKinds.length > 0 &&
    allKinds.every((kind) => agent?.selectedKinds.includes(kind));
  const visibleRows = (agent?.proposals ?? []).slice(0, 200);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && (committing || agent?.status === "running")) return;
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto overflow-x-hidden sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("imports.title")}</DialogTitle>
          <DialogDescription>{t("imports.description")}</DialogDescription>
        </DialogHeader>

        {/* ---------------- 选择文件（唯一主入口） ---------------- */}
        {showPicker ? (
          <section aria-labelledby="import-picker-title" className="space-y-4">
            <div className="rounded-xl border border-border bg-subtle/40 px-4 py-5 text-center">
              <div className="mx-auto flex size-11 items-center justify-center rounded-full bg-accent-soft text-primary">
                <FileUp className="size-5" aria-hidden="true" />
              </div>
              <h3 id="import-picker-title" className="eh-h3 mt-3">
                {t("imports.picker.title")}
              </h3>
              <p className="eh-small mx-auto mt-1 max-w-lg text-muted-foreground">
                {t("imports.picker.desc")}
              </p>
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                <Button onClick={onChooseFilesForAgent} disabled={agentBusy}>
                  {agentBusy ? (
                    <Loader2 className="animate-spin" data-icon="inline-start" />
                  ) : (
                    <Sparkles data-icon="inline-start" />
                  )}
                  {t("imports.picker.chooseFilesAi")}
                </Button>
                <Button variant="outline" onClick={onChooseFiles}>
                  <FilePlus2 data-icon="inline-start" />
                  {t("imports.picker.chooseFiles")}
                </Button>
                <Button variant="outline" onClick={onChooseFolder}>
                  <FolderOpen data-icon="inline-start" />
                  {t("imports.picker.chooseFolder")}
                </Button>
              </div>
              <p className="eh-caption mt-3 text-muted-foreground">
                {t("imports.picker.formats")}
              </p>
              <p className="eh-caption mt-1 text-muted-foreground">
                {t("imports.picker.drag")}
              </p>
            </div>

            <div className="rounded-xl border border-border px-4 py-3">
              <div className="flex items-start gap-2.5">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                <div className="min-w-0">
                  <p className="eh-small font-medium">{t("imports.picker.aiTitle")}</p>
                  <p className="eh-caption mt-0.5 text-muted-foreground">
                    {t("imports.picker.aiDesc")}
                  </p>
                </div>
              </div>
              {hasSelection ? (
                <div className="mt-2 flex flex-wrap items-center gap-2 pl-7">
                  <span className="eh-caption text-muted-foreground">
                    {t("imports.picker.selected", {
                      count: formatNumber(selectedFiles.length, locale),
                    })}
                  </span>
                  <Button size="sm" variant="outline" onClick={onStartAgent} disabled={agentBusy}>
                    {agentBusy ? (
                      <Loader2 className="animate-spin" data-icon="inline-start" />
                    ) : (
                      <Sparkles data-icon="inline-start" />
                    )}
                    {t("imports.agent.startParse")}
                  </Button>
                </div>
              ) : null}
            </div>

            <section aria-label={t("imports.guides.title")}>
              <button
                type="button"
                aria-expanded={showGuides}
                onClick={() => setShowGuides((value) => !value)}
                className="flex w-full items-center justify-between rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <span className="font-medium">{t("imports.guides.title")}</span>
                <ChevronDown
                  className={showGuides ? "size-4 rotate-180 transition-transform" : "size-4 transition-transform"}
                  aria-hidden="true"
                />
              </button>
              {showGuides ? (
                <div className="mt-2 space-y-2">
                  <p className="eh-caption text-muted-foreground">
                    {t("imports.guides.desc")}
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {VENDOR_GUIDES.map((guide) => (
                      <details
                        key={guide.id}
                        className="group rounded-lg border border-border px-3 py-2 open:bg-subtle/40"
                      >
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-medium">
                          {isZh ? guide.name.zh : guide.name.en}
                          <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
                        </summary>
                        <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs text-muted-foreground">
                          {(isZh ? guide.steps.zh : guide.steps.en).map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ol>
                        <dl className="mt-2 space-y-1 border-t border-border pt-2 text-xs">
                          <div className="flex gap-1.5">
                            <dt className="shrink-0 text-muted-foreground">{t("imports.guides.format")}</dt>
                            <dd>{guide.formats}</dd>
                          </div>
                          <div className="flex gap-1.5">
                            <dt className="shrink-0 text-muted-foreground">{t("imports.guides.includes")}</dt>
                            <dd>{isZh ? guide.includes.zh : guide.includes.en}</dd>
                          </div>
                        </dl>
                        {guide.versionNote ? (
                          <p className="mt-1.5 text-xs text-muted-foreground">
                            {isZh ? guide.versionNote.zh : guide.versionNote.en}
                          </p>
                        ) : null}
                        <a
                          href={guide.helpUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-block text-xs text-primary underline underline-offset-2"
                        >
                          {t("imports.guides.help")}
                        </a>
                      </details>
                    ))}
                  </div>
                  <p className="eh-caption text-muted-foreground">
                    {isZh ? VENDOR_GUIDES_VERSION_NOTE.zh : VENDOR_GUIDES_VERSION_NOTE.en}
                  </p>
                </div>
              ) : null}
            </section>

            <p className="eh-caption text-muted-foreground">
              {t("imports.picker.privacy")}
            </p>
          </section>
        ) : null}

        {/* ---------------- 标准导入结果 ---------------- */}
        {result && !agent ? (
          <section className="space-y-3">
            <Alert>
              <CheckCircle2 />
              <AlertTitle>{t("imports.health.doneTitle")}</AlertTitle>
              <AlertDescription>
                {result.duplicateFile
                  ? t("imports.health.duplicateFile")
                  : t("imports.health.doneDesc")}
              </AlertDescription>
            </Alert>
            <dl className="grid grid-cols-3 gap-2">
              {(
                [
                  ["created", result.created],
                  ["skipped", result.skipped],
                  ["failed", result.failed],
                ] as const
              ).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg border border-border px-2.5 py-2 text-center"
                >
                  <dt className="eh-caption text-muted-foreground">
                    {t(`imports.health.${key}`)}
                  </dt>
                  <dd className="eh-num text-lg">{formatNumber(value, locale)}</dd>
                </div>
              ))}
            </dl>
            {createdKinds.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {createdKinds.map((key) => (
                  <li
                    key={key}
                    className="rounded-full border border-border px-2.5 py-0.5 text-xs"
                  >
                    {t(`imports.health.kinds.${key}`)} ·{" "}
                    {formatNumber(result.recordCounts[key], locale)}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}

        {busy && !agent ? (
          <div className="flex items-center gap-3 rounded-lg border border-border bg-subtle/50 px-4 py-6">
            <Loader2 className="size-5 animate-spin text-accent" aria-hidden="true" />
            <div>
              <p className="eh-small font-medium">{t("imports.reading")}</p>
              <p className="eh-caption text-muted-foreground">
                {t("imports.readingDesc")}
              </p>
            </div>
          </div>
        ) : null}

        {!busy && error && !agent ? (
          <div className="space-y-3">
            <Alert variant="destructive">
              <AlertTriangle />
              <AlertTitle>{t("imports.failedTitle")}</AlertTitle>
              <AlertDescription>
                <p>
                  {t(`imports.errors.${error.code}`, {
                    defaultValue: error.message || t("imports.errors.unknown"),
                  })}
                </p>
                <code className="eh-num mt-2 inline-block rounded bg-subtle px-1.5 py-0.5 text-xs">
                  {error.code}
                </code>
              </AlertDescription>
            </Alert>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={onPickAnother}>
                <FileUp data-icon="inline-start" />
                {t("imports.chooseAnother")}
              </Button>
              {hasSelection ? (
                <Button size="sm" onClick={onStartAgent} disabled={agentBusy}>
                  {agentBusy ? (
                    <Loader2 className="animate-spin" data-icon="inline-start" />
                  ) : (
                    <Sparkles data-icon="inline-start" />
                  )}
                  {t("imports.agent.askAi")}
                </Button>
              ) : null}
            </div>
            {hasSelection ? (
              <p className="eh-caption text-muted-foreground">
                {t("imports.agent.askAiHint")}
              </p>
            ) : null}
          </div>
        ) : null}

        {!busy && preview && !agent ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{preview.format.toUpperCase()}</Badge>
              <span className="eh-caption text-muted-foreground">
                {preview.adapterId}
              </span>
              <span className="eh-caption ml-auto text-muted-foreground">
                {t("imports.nSamples", {
                  value: formatNumber(preview.preview.nSamples, locale),
                })}
                {preview.hasAnnotations
                  ? ` · ${t("imports.annotations", { value: preview.annotationCount ?? 0 })}`
                  : ""}
              </span>
            </div>

            {isHealthBundle ? (
              <section className="space-y-2 rounded-lg border border-border bg-subtle/40 px-3 py-2.5">
                <p className="eh-small font-medium">
                  {t("imports.health.summaryTitle", {
                    total: formatNumber(totalRecords, locale),
                  })}
                </p>
                <ul className="flex flex-wrap gap-1.5">
                  {COUNT_ORDER.filter((key) => recordCounts[key] > 0).map((key) => (
                    <li
                      key={key}
                      className="rounded-full border border-border px-2.5 py-0.5 text-xs"
                    >
                      {t(`imports.health.kinds.${key}`)} ·{" "}
                      {formatNumber(recordCounts[key], locale)}
                    </li>
                  ))}
                </ul>
                <p className="eh-caption text-muted-foreground">
                  {t("imports.health.noParams")}
                </p>
              </section>
            ) : null}

            {!isHealthBundle || preview.preview.samples.length > 0 ? (
              <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div className="rounded-lg border border-border px-2.5 py-2">
                  <dt className="eh-caption text-muted-foreground">{t("imports.fs")}</dt>
                  <dd className="eh-num text-sm">
                    {preview.samplingRate
                      ? `${formatNumber(preview.samplingRate, locale)} Hz`
                      : "—"}
                  </dd>
                </div>
                <div className="rounded-lg border border-border px-2.5 py-2">
                  <dt className="eh-caption text-muted-foreground">{t("imports.leads")}</dt>
                  <dd className="eh-num text-sm">{preview.leads.join(" / ") || "—"}</dd>
                </div>
                <div className="rounded-lg border border-border px-2.5 py-2">
                  <dt className="eh-caption text-muted-foreground">{t("imports.duration")}</dt>
                  <dd className="eh-num text-sm">
                    {preview.durationSec === null
                      ? "—"
                      : formatSeconds(preview.durationSec)}
                  </dd>
                </div>
                <div className="rounded-lg border border-border px-2.5 py-2">
                  <dt className="eh-caption text-muted-foreground">{t("imports.unit")}</dt>
                  <dd className="eh-num text-sm">{preview.unit || "—"}</dd>
                </div>
              </dl>
            ) : null}

            {!isHealthBundle || preview.preview.samples.length > 0 ? (
              <PreviewSignal samples={preview.preview.samples} />
            ) : null}

            {requires &&
            (requires.samplingRate || requires.lead || requires.unit) ? (
              <Alert>
                <Info />
                <AlertTitle>{t("imports.requiresTitle")}</AlertTitle>
                <AlertDescription>
                  <div className="flex flex-wrap gap-1.5">
                    {requires.samplingRate ? (
                      <Badge variant="outline">{t("imports.requires.samplingRate")}</Badge>
                    ) : null}
                    {requires.lead ? (
                      <Badge variant="outline">{t("imports.requires.lead")}</Badge>
                    ) : null}
                    {requires.unit ? (
                      <Badge variant="outline">{t("imports.requires.unit")}</Badge>
                    ) : null}
                  </div>
                </AlertDescription>
              </Alert>
            ) : null}

            {preview.warnings.length ? (
              <ul className="space-y-1.5">
                {preview.warnings.map((warning, index) => (
                  <li
                    key={`${warning.code}-${index}`}
                    className="flex items-start gap-2 text-sm"
                  >
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
                    <span>{warningText(warning, t)}</span>
                  </li>
                ))}
              </ul>
            ) : null}

            {!isHealthBundle ? (
              <section aria-labelledby="import-params-title" className="space-y-3">
                <div>
                  <h3 id="import-params-title" className="eh-h3">
                    {t("imports.paramsTitle")}
                  </h3>
                  <p className="eh-caption mt-0.5 text-muted-foreground">
                    {t("imports.paramsDesc")}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="import-fs">
                      {t("imports.fields.samplingRate")}
                      {requires?.samplingRate ? (
                        <span className="text-danger" aria-hidden="true">*</span>
                      ) : null}
                    </Label>
                    <Input
                      id="import-fs"
                      type="number"
                      inputMode="decimal"
                      min={1}
                      max={1_000_000}
                      step="any"
                      value={samplingRate}
                      onChange={(event) => setSamplingRate(event.target.value)}
                      aria-required={requires?.samplingRate ?? false}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="import-lead">
                      {t("imports.fields.lead")}
                      <span className="text-danger" aria-hidden="true">*</span>
                    </Label>
                    <Input
                      id="import-lead"
                      list="import-lead-options"
                      value={lead}
                      maxLength={16}
                      onChange={(event) => setLead(event.target.value)}
                      aria-required
                    />
                    <datalist id="import-lead-options">
                      {LEAD_SUGGESTIONS.map((item) => (
                        <option key={item} value={item} />
                      ))}
                    </datalist>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="import-unit">{t("imports.fields.unit")}</Label>
                    <Select value={unit} onValueChange={setUnit}>
                      <SelectTrigger id="import-unit" className="w-full" aria-label={t("imports.fields.unit")}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="mV">mV</SelectItem>
                        <SelectItem value="uV">uV</SelectItem>
                        <SelectItem value="V">V</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label>{t("imports.fields.polarity")}</Label>
                    <div
                      className="flex h-8 items-center gap-1 rounded-lg border border-input p-0.5"
                      role="group"
                      aria-label={t("imports.fields.polarity")}
                    >
                      {(["normal", "inverted"] as const).map((option) => (
                        <Button
                          key={option}
                          type="button"
                          size="xs"
                          variant={polarity === option ? "secondary" : "ghost"}
                          aria-pressed={polarity === option}
                          className="flex-1"
                          onClick={() => setPolarity(option)}
                        >
                          {polarity === option ? (
                            <Check className="size-3" aria-hidden="true" />
                          ) : null}
                          {t(`imports.polarity.${option}`)}
                        </Button>
                      ))}
                    </div>
                    <p className="eh-caption text-muted-foreground">
                      {t("imports.fields.polarityHint")}
                    </p>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="import-captured">{t("imports.fields.capturedAt")}</Label>
                    <Input
                      id="import-captured"
                      type="datetime-local"
                      value={capturedAt}
                      onChange={(event) => setCapturedAt(event.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="import-tags">{t("imports.fields.tags")}</Label>
                    <div className="flex gap-1.5">
                      <Input
                        id="import-tags"
                        value={tagInput}
                        maxLength={32}
                        placeholder={t("imports.fields.tagsPlaceholder")}
                        onChange={(event) => setTagInput(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === ",") {
                            event.preventDefault();
                            addTag(tagInput);
                          }
                        }}
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => addTag(tagInput)}
                      >
                        {t("imports.fields.addTag")}
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {KNOWN_TAGS.map((tag) => {
                        const selected = tags.includes(tag);
                        return (
                          <button
                            key={tag}
                            type="button"
                            aria-pressed={selected}
                            onClick={() =>
                              setTags((current) =>
                                current.includes(tag)
                                  ? current.filter((item) => item !== tag)
                                  : [...current, tag],
                              )
                            }
                            className={
                              selected
                                ? "rounded-full border border-primary bg-accent-soft px-2.5 py-0.5 text-xs"
                                : "rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground hover:bg-accent"
                            }
                          >
                            {tagLabel(tag)}
                          </button>
                        );
                      })}
                      {tags
                        .filter((tag) => !KNOWN_TAGS.includes(tag as (typeof KNOWN_TAGS)[number]))
                        .map((tag) => (
                          <Badge key={tag} variant="outline">
                            {tag}
                          </Badge>
                        ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="import-notes">{t("imports.fields.notes")}</Label>
                  <Textarea
                    id="import-notes"
                    value={notes}
                    maxLength={4000}
                    rows={2}
                    placeholder={t("imports.fields.notesPlaceholder")}
                    onChange={(event) => setNotes(event.target.value)}
                  />
                </div>
              </section>
            ) : null}

            {membersQuery.isError ? (
              <Alert variant="destructive">
                <AlertTriangle />
                <AlertTitle>{t("imports.noMemberTitle")}</AlertTitle>
                <AlertDescription>{t("imports.noMember")}</AlertDescription>
              </Alert>
            ) : null}

            {formError ? (
              <p className="eh-small text-danger" role="alert">
                {formError}
              </p>
            ) : null}

            {commitError ? (
              <Alert variant="destructive">
                <AlertTriangle />
                <AlertTitle>{t("imports.commitFailedTitle")}</AlertTitle>
                <AlertDescription>
                  {t(`imports.errors.${commitError.code}`, {
                    defaultValue: commitError.message,
                  })}
                </AlertDescription>
              </Alert>
            ) : null}
          </div>
        ) : null}

        {/* ---------------- Agent 导入 ---------------- */}
        {agent ? (
          <section className="space-y-3" aria-labelledby="agent-import-title">
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="size-4 text-primary" aria-hidden="true" />
              <h3 id="agent-import-title" className="eh-h3">
                {t("imports.agent.title")}
              </h3>
              <Badge variant="secondary" className="ml-auto">
                {t(`imports.agent.status.${agent.status}`)}
              </Badge>
            </div>

            {agent.status === "created" ? (
              <>
                <div className="rounded-lg border border-border px-3 py-2.5">
                  <p className="eh-small font-medium">
                    {t("imports.agent.filesTitle", { count: agent.session.files.length })}
                  </p>
                  <ul className="mt-1.5 space-y-1">
                    {agent.session.files.slice(0, 20).map((file) => (
                      <li
                        key={`${file.name}-${file.size}`}
                        className="flex items-center justify-between gap-2 text-xs"
                      >
                        <span className="truncate">{file.name}</span>
                        <span className="eh-num shrink-0 text-muted-foreground">
                          {Math.max(1, Math.round(file.size / 1024))} KB
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
                <Alert>
                  <Info />
                  <AlertTitle>{t("imports.agent.privacyTitle")}</AlertTitle>
                  <AlertDescription>{t("imports.agent.privacyDesc")}</AlertDescription>
                </Alert>
                <p className="eh-caption text-muted-foreground">
                  {t("imports.agent.runHint")}
                </p>
              </>
            ) : null}

            {agent.status === "running" ? (
              <>
                <div
                  className="flex items-center gap-3 rounded-lg border border-border bg-subtle/50 px-4 py-4"
                  aria-live="polite"
                  aria-busy="true"
                >
                  <Loader2 className="size-5 animate-spin text-accent" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="eh-small font-medium">{t("imports.agent.running")}</p>
                    <p className="eh-caption text-muted-foreground">
                      {t("imports.agent.toolCalls", { count: agent.toolCalls })}
                    </p>
                  </div>
                </div>
                {agent.thought ? (
                  <p className="max-h-20 overflow-y-auto rounded-lg bg-subtle/60 px-3 py-2 text-xs text-muted-foreground">
                    {agent.thought}
                  </p>
                ) : null}
                <ol
                  className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border px-3 py-2 text-xs"
                  aria-label={t("imports.agent.events")}
                >
                  {agent.events.map((event) => (
                    <li key={event.id} className="flex items-start gap-2">
                      <span
                        className={
                          event.kind === "error"
                            ? "mt-1 size-1.5 shrink-0 rounded-full bg-danger"
                            : event.kind === "result" && event.ok === false
                              ? "mt-1 size-1.5 shrink-0 rounded-full bg-warning"
                              : "mt-1 size-1.5 shrink-0 rounded-full bg-accent"
                        }
                        aria-hidden="true"
                      />
                      <span className="min-w-0">
                        <span className="eh-num">{event.name}</span>
                        {event.detail ? (
                          <span className="text-muted-foreground"> · {event.detail}</span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ol>
              </>
            ) : null}

            {agent.error ? (
              <Alert variant="destructive">
                <AlertTriangle />
                <AlertTitle>{t("imports.agent.failedTitle")}</AlertTitle>
                <AlertDescription>
                  {t(`imports.agent.errors.${agent.error.code}`, {
                    defaultValue: agent.error.message,
                  })}
                </AlertDescription>
              </Alert>
            ) : null}

            {agent.status === "ready" || agent.status === "committed" ? (
              <>
                {agent.summary ? (
                  <div className="rounded-lg border border-border bg-subtle/40 px-3 py-2">
                    <p className="eh-small font-medium">{t("imports.agent.summary")}</p>
                    <p className="eh-caption mt-0.5 text-muted-foreground">
                      {agent.summary}
                    </p>
                    <p className="eh-caption mt-1 text-muted-foreground">
                      {t("imports.agent.proposalCount", {
                        count: formatNumber(agent.session.proposalCount || agent.proposals.length, locale),
                      })}
                    </p>
                  </div>
                ) : null}

                {agent.status === "committed" && agent.commit ? (
                  <Alert>
                    <CheckCircle2 />
                    <AlertTitle>{t("imports.agent.doneTitle")}</AlertTitle>
                    <AlertDescription>
                      {t("imports.agent.doneDesc")}
                    </AlertDescription>
                  </Alert>
                ) : null}

                {agent.status === "committed" && agent.commit ? (
                  <dl className="grid grid-cols-3 gap-2">
                    {(
                      [
                        ["created", agent.commit.created],
                        ["skipped", agent.commit.skipped],
                        ["failed", agent.commit.failed],
                      ] as const
                    ).map(([key, value]) => (
                      <div
                        key={key}
                        className="rounded-lg border border-border px-2.5 py-2 text-center"
                      >
                        <dt className="eh-caption text-muted-foreground">
                          {t(`imports.agent.${key}`)}
                        </dt>
                        <dd className="eh-num text-lg">{formatNumber(value, locale)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}

                {groups.length ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="eh-small font-medium">
                        {t("imports.agent.selectTitle")}
                      </span>
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        onClick={() => onSetAgentKinds(allSelected ? [] : allKinds)}
                        disabled={agent.status === "committed"}
                      >
                        {allSelected ? t("imports.agent.clearAll") : t("imports.agent.selectAll")}
                      </Button>
                    </div>
                    <ul className="flex flex-wrap gap-1.5">
                      {groups.map(([kind, items]) => {
                        const selected = agent.selectedKinds.includes(kind);
                        return (
                          <li key={kind}>
                            <button
                              type="button"
                              aria-pressed={selected}
                              onClick={() => onToggleAgentKind(kind)}
                              disabled={agent.status === "committed"}
                              className={
                                selected
                                  ? "inline-flex items-center gap-1.5 rounded-full border border-primary bg-accent-soft px-2.5 py-1 text-xs"
                                  : "inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground"
                              }
                            >
                              {selected ? (
                                <Check className="size-3" aria-hidden="true" />
                              ) : (
                                <Square className="size-3" aria-hidden="true" />
                              )}
                              {t(`imports.agent.kinds.${kind}`, { defaultValue: kind })} ·{" "}
                              {formatNumber(items.length, locale)}
                            </button>
                          </li>
                        );
                      })}
                    </ul>

                    <div className="overflow-x-auto rounded-lg border border-border">
                      <table className="w-full min-w-[640px] text-left text-xs">
                        <thead className="bg-subtle/60 text-muted-foreground">
                          <tr>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.time")}</th>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.kind")}</th>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.value")}</th>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.unit")}</th>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.source")}</th>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.confidence")}</th>
                            <th scope="col" className="px-2.5 py-2 font-medium">{t("imports.agent.columns.evidence")}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {visibleRows.map((item) => (
                            <tr key={item.id} className={agent.selectedKinds.includes(item.kind) ? "" : "opacity-50"}>
                              <td className="eh-num whitespace-nowrap px-2.5 py-1.5">
                                {formatDateTime(item.startAt, locale)}
                              </td>
                              <td className="whitespace-nowrap px-2.5 py-1.5">
                                {t(`healthData.kinds.${item.kind}`, { defaultValue: item.kind })}
                              </td>
                              <td className="px-2.5 py-1.5">
                                <AgentValue proposal={item} locale={locale} t={t} />
                              </td>
                              <td className="eh-num whitespace-nowrap px-2.5 py-1.5">{item.unit}</td>
                              <td className="max-w-[10rem] truncate px-2.5 py-1.5">
                                {item.source.app || item.source.device || item.source.manufacturer || "—"}
                              </td>
                              <td className="eh-num whitespace-nowrap px-2.5 py-1.5">
                                {Math.round(item.confidence * 100)}%
                              </td>
                              <td className="max-w-[14rem] truncate px-2.5 py-1.5 text-muted-foreground">
                                {item.evidence.file}
                                {item.evidence.locator ? ` · ${item.evidence.locator}` : ""}
                                {item.evidence.page ? ` · p.${item.evidence.page}` : ""}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {agent.proposals.length > visibleRows.length ? (
                      <p className="eh-caption text-muted-foreground">
                        {t("imports.agent.tableTruncated", {
                          shown: visibleRows.length,
                          total: agent.proposals.length,
                        })}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <Alert>
                    <Info />
                    <AlertTitle>{t("imports.agent.noProposalsTitle")}</AlertTitle>
                    <AlertDescription>{t("imports.agent.noProposalsDesc")}</AlertDescription>
                  </Alert>
                )}

                {membersQuery.isError ? (
                  <Alert variant="destructive">
                    <AlertTriangle />
                    <AlertTitle>{t("imports.noMemberTitle")}</AlertTitle>
                    <AlertDescription>{t("imports.noMember")}</AlertDescription>
                  </Alert>
                ) : null}
              </>
            ) : null}
          </section>
        ) : null}

        <DialogFooter className="flex-wrap gap-2">
          {agent ? (
            <>
              {agent.status === "created" ? (
                <>
                  <Button variant="ghost" onClick={() => onOpenChange(false)}>
                    {t("common.cancel")}
                  </Button>
                  <Button onClick={onRunAgent} disabled={agentBusy}>
                    {agentBusy ? (
                      <Loader2 className="animate-spin" data-icon="inline-start" />
                    ) : (
                      <Sparkles data-icon="inline-start" />
                    )}
                    {t("imports.agent.startParse")}
                  </Button>
                </>
              ) : null}
              {agent.status === "running" ? (
                <Button variant="outline" onClick={onStopAgent}>
                  <StopCircle data-icon="inline-start" />
                  {t("imports.agent.stop")}
                </Button>
              ) : null}
              {agent.status === "error" ? (
                <>
                  <Button variant="outline" onClick={onPickAnother}>
                    <RotateCcw data-icon="inline-start" />
                    {t("imports.chooseAnother")}
                  </Button>
                  <Button onClick={onRunAgent}>{t("imports.agent.retry")}</Button>
                </>
              ) : null}
              {agent.status === "ready" ? (
                <>
                  <Button variant="ghost" onClick={() => onOpenChange(false)}>
                    {t("common.cancel")}
                  </Button>
                  <Button
                    onClick={() => onCommitAgent(memberId)}
                    disabled={
                      agentCommitting ||
                      !memberId ||
                      agent.selectedKinds.length === 0
                    }
                  >
                    {agentCommitting ? (
                      <Loader2 className="animate-spin" data-icon="inline-start" />
                    ) : (
                      <Check data-icon="inline-start" />
                    )}
                    {agentCommitting ? t("imports.agent.committing") : t("imports.agent.commit")}
                  </Button>
                </>
              ) : null}
              {agent.status === "committed" ? (
                <Button onClick={onDone}>{t("imports.health.viewRecords")}</Button>
              ) : null}
            </>
          ) : result ? (
            <Button onClick={onDone}>{t("imports.health.viewRecords")}</Button>
          ) : (
            <>
              {preview && !busy ? (
                <Button
                  variant="outline"
                  onClick={() => onPickAnother()}
                  disabled={committing}
                >
                  <RotateCcw data-icon="inline-start" />
                  {t("imports.chooseAnother")}
                </Button>
              ) : null}
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={committing}
              >
                {t("common.cancel")}
              </Button>
              {preview ? (
                <Button onClick={submit} disabled={commitDisabled}>
                  {committing ? (
                    <Loader2 className="animate-spin" data-icon="inline-start" />
                  ) : (
                    <FileUp data-icon="inline-start" />
                  )}
                  {committing ? t("imports.committing") : t("imports.commit")}
                </Button>
              ) : null}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
