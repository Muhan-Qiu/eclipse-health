import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Check,
  FileUp,
  Info,
  Loader2,
  RotateCcw,
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
import { formatNumber } from "@/lib/format";
import { intlLocale } from "@/lib/i18n";
import { useTagLabel } from "@/lib/tags";
import { formatSeconds } from "@/lib/waveform";

const KNOWN_TAGS = ["morning", "resting", "postExercise", "evening"] as const;
const LEAD_SUGGESTIONS = ["MLII", "I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"];

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

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: ImportPreview | null;
  error: ApiError | null;
  busy: boolean;
  committing: boolean;
  commitError: ApiError | null;
  onCommit: (body: ImportCommitBody) => void;
  onPickAnother: () => void;
}

export function ImportDialog({
  open,
  onOpenChange,
  preview,
  error,
  busy,
  committing,
  commitError,
  onCommit,
  onPickAnother,
}: ImportDialogProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
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
    const rate = Number(samplingRate);
    if (!Number.isFinite(rate) || rate <= 0) {
      setFormError(t("imports.errors.invalidSamplingRate"));
      return;
    }
    if (!lead.trim()) {
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
      parameters: {
        samplingRate: rate,
        lead: lead.trim(),
        unit,
        polarity,
      },
    });
  };

  const requires = preview?.requires;
  const commitDisabled = committing || busy || !preview || !memberId;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && committing) return;
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("imports.title")}</DialogTitle>
          <DialogDescription>{t("imports.description")}</DialogDescription>
        </DialogHeader>

        {busy ? (
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

        {!busy && error ? (
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
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={onPickAnother}>
                <FileUp data-icon="inline-start" />
                {t("imports.chooseAnother")}
              </Button>
            </div>
          </div>
        ) : null}

        {!busy && preview ? (
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

            <PreviewSignal samples={preview.preview.samples} />

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

        <DialogFooter>
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
          <Button
            onClick={submit}
            disabled={commitDisabled}
          >
            {committing ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : (
              <FileUp data-icon="inline-start" />
            )}
            {committing ? t("imports.committing") : t("imports.commit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
