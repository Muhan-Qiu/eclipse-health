import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  ChevronUp,
  CircleAlert,
  CloudSun,
  Droplets,
  FileText,
  LoaderCircle,
  MessageSquare,
  Send,
  ShieldCheck,
  Square,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import { MarkdownText } from "@/components/common/markdown";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "cn";
import { intlLocale } from "@/lib/i18n";
import type { HealthRecord } from "@/lib/api/types";
import { ToolTrace } from "./tool-trace";
import type {
  AssistantMode,
  AssistantProvider,
  AssistantStyle,
  ChatMessage,
  CoachWeather,
} from "./types";

const STYLES: AssistantStyle[] = ["brief", "detailed", "doctor"];
const COACH_PRESETS = ["sleep", "heart", "exercise", "stress", "weight"] as const;

function weatherKey(code: number | null): string {
  if (code === null) return "unknown";
  if (code === 0) return "clear";
  if (code <= 3) return "cloudy";
  if (code === 45 || code === 48) return "fog";
  if (code >= 51 && code <= 57) return "drizzle";
  if (code >= 61 && code <= 67) return "rain";
  if (code >= 71 && code <= 77) return "snow";
  if (code >= 80 && code <= 82) return "showers";
  if (code === 85 || code === 86) return "snow";
  if (code >= 95) return "thunderstorm";
  return "unknown";
}

function recordLabel(record: HealthRecord, locale: string): string {
  const when = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(record.capturedAt));
  const seconds = record.durationSec ? `${Math.round(record.durationSec)}s` : "";
  return [when, seconds, record.leads.join("/")].filter(Boolean).join(" · ");
}

function WeatherSummary({
  city,
  weather,
  loading,
}: {
  city: string;
  weather: CoachWeather | null;
  loading: boolean;
}) {
  const { t } = useTranslation();
  if (!city.trim()) {
    return (
      <p className="eh-caption text-muted-foreground">
        {t("assistant.coach.weather.hint")}
      </p>
    );
  }
  if (loading) {
    return (
      <span className="eh-caption inline-flex items-center gap-1.5 text-muted-foreground">
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
        {t("assistant.coach.weather.loading")}
      </span>
    );
  }
  const today = weather?.days?.[0];
  if (!weather || !today) {
    return (
      <p className="eh-caption text-muted-foreground">
        {t("assistant.coach.weather.unavailable")}
      </p>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border/70 bg-muted/30 px-2.5 py-1 text-xs text-muted-foreground">
      <CloudSun className="size-3.5 text-foreground/70" aria-hidden="true" />
      <span className="font-medium text-foreground">{weather.city}</span>
      <span>{t(`assistant.coach.weather.codes.${weatherKey(today.weatherCode)}`)}</span>
      <span className="inline-flex items-center gap-1">
        {today.tempMin ?? "—"}–{today.tempMax ?? "—"}°C
      </span>
      {today.precipitationProbability !== null ? (
        <span className="inline-flex items-center gap-1">
          <Droplets className="size-3" aria-hidden="true" />
          {t("assistant.coach.weather.precipitation", {
            value: today.precipitationProbability,
          })}
        </span>
      ) : null}
    </span>
  );
}

function CitationChips({ message }: { message: ChatMessage }) {
  if (message.citations.length === 0) return null;
  return (
    <div className="mt-2.5 flex flex-wrap gap-1.5">
      {message.citations.map((citation) => {
        const content = (
          <>
            <FileText className="size-3" aria-hidden="true" />
            <span className="max-w-52 truncate">{citation.label ?? citation.id}</span>
          </>
        );
        const className =
          "inline-flex items-center gap-1 rounded-full border border-border/70 bg-background px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground";
        return citation.recordId ? (
          <Link
            key={`${citation.kind}-${citation.id}`}
            to={`/records/${citation.recordId}`}
            className={className}
            title={citation.id}
          >
            {content}
            <ArrowUpRight className="size-2.5" aria-hidden="true" />
          </Link>
        ) : (
          <span key={`${citation.kind}-${citation.id}`} className={className} title={citation.id}>
            {content}
          </span>
        );
      })}
    </div>
  );
}

function MessageMeta({ message }: { message: ChatMessage }) {
  const { t } = useTranslation();
  const parts: string[] = [];
  if (message.model) parts.push(message.model);
  if (typeof message.durationMs === "number") {
    parts.push(t("assistant.chat.metaLatency", { ms: message.durationMs }));
  }
  const usage = message.usage;
  if (usage && (usage.promptTokens !== null || usage.completionTokens !== null)) {
    parts.push(
      t("assistant.chat.metaTokens", {
        prompt: usage.promptTokens ?? "—",
        completion: usage.completionTokens ?? "—",
        source: t(`assistant.chat.usageSource.${usage.source}`, {
          defaultValue: usage.source,
        }),
      }),
    );
  }
  if (parts.length === 0) return null;
  return (
    <p className="eh-caption mt-2 text-muted-foreground">
      {parts.join(" · ")}
    </p>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
  onOpenTransparency: (message: ChatMessage) => void;
}

function MessageBubble({ message, onOpenTransparency }: MessageBubbleProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-2xl rounded-br-md border border-primary/20 bg-accent-soft px-4 py-2.5">
          <p className="text-sm leading-6 whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  const showStreamingPlaceholder =
    message.status === "streaming" && message.content.length === 0;

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[94%] rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3">
        {showStreamingPlaceholder ? (
          <p className="eh-small flex items-center gap-2 text-muted-foreground">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
            {t("assistant.chat.streaming")}
          </p>
        ) : (
          <MarkdownText
            content={message.content}
            streaming={message.status === "streaming"}
            className="text-sm leading-6"
          />
        )}

        {message.status === "cancelled" ? (
          <Badge variant="outline" className="mt-2 font-normal text-muted-foreground">
            {t("assistant.chat.cancelled")}
          </Badge>
        ) : null}

        {message.status === "error" ? (
          <div className="mt-2 flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-2.5 py-2 text-xs text-destructive">
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>
              {t("assistant.chat.errorTitle")}
              {message.error?.message ? `：${message.error.message}` : ""}
            </span>
          </div>
        ) : null}

        <ToolTrace calls={message.toolCalls} />
        <CitationChips message={message} />
        <MessageMeta message={message} />

        <div className="mt-3 flex items-center gap-1">
          <Button
            variant="ghost"
            size="xs"
            className="-ml-1.5 text-muted-foreground"
            onClick={() => onOpenTransparency(message)}
          >
            <ShieldCheck data-icon="inline-start" />
            {t("assistant.transparency.title")}
          </Button>
        </div>
      </div>
    </div>
  );
}

export interface ChatPanelProps {
  messages: ChatMessage[];
  streaming: boolean;
  providers: AssistantProvider[];
  activeProviderId: string | null;
  records: HealthRecord[];
  recordsError: string | null;
  error: string | null;
  onDismissError: () => void;
  onSend: (input: {
    content: string;
    style: AssistantStyle;
    recordId?: string;
    includeNotes: boolean;
    mode: AssistantMode;
    city?: string;
  }) => void;
  onStop: () => void;
  onOpenTransparency: (message: ChatMessage) => void;
  style: AssistantStyle;
  onStyleChange: (style: AssistantStyle) => void;
  recordId: string | null;
  onRecordIdChange: (id: string | null) => void;
  includeNotes: boolean;
  onIncludeNotesChange: (value: boolean) => void;
  hasMoreMessages: boolean;
  loadingEarlier: boolean;
  messageTotal: number;
  onLoadEarlier: () => void;
  mode: AssistantMode;
  onModeChange: (mode: AssistantMode) => void;
  seedPrompt: string | null;
  city: string;
  onCityChange: (city: string) => void;
  weather: CoachWeather | null;
  weatherLoading: boolean;
}

export function ChatPanel({
  messages,
  streaming,
  providers,
  activeProviderId,
  records,
  recordsError,
  error,
  onDismissError,
  onSend,
  onStop,
  onOpenTransparency,
  style,
  onStyleChange,
  recordId,
  onRecordIdChange,
  includeNotes,
  onIncludeNotesChange,
  hasMoreMessages,
  loadingEarlier,
  messageTotal,
  onLoadEarlier,
  mode,
  onModeChange,
  seedPrompt,
  city,
  onCityChange,
  weather,
  weatherLoading,
}: ChatPanelProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const [content, setContent] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeProvider =
    providers.find((provider) => provider.id === activeProviderId) ?? null;
  const canSend =
    Boolean(activeProvider) && !streaming && content.trim().length > 0;

  useEffect(() => {
    if (seedPrompt && seedPrompt.trim()) setContent(seedPrompt);
  }, [seedPrompt]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, streaming]);

  const submit = () => {
    const text = content.trim();
    if (!text || !activeProvider || streaming) return;
    onSend({
      content: text,
      style,
      recordId: recordId ?? undefined,
      includeNotes,
      mode,
      city: mode === "coach" && city.trim() ? city.trim() : undefined,
    });
    setContent("");
  };

  const presets =
    mode === "coach"
      ? COACH_PRESETS.map((key) => ({
          key,
          label: t(`assistant.coach.presets.${key}.label`),
          prompt: t(`assistant.coach.presets.${key}.prompt`),
        }))
      : [
          { key: "abnormal", label: t("assistant.chat.presets.abnormal"), prompt: t("assistant.chat.presets.abnormal") },
          { key: "care", label: t("assistant.chat.presets.care"), prompt: t("assistant.chat.presets.care") },
          { key: "hrv", label: t("assistant.chat.presets.hrv"), prompt: t("assistant.chat.presets.hrv") },
          { key: "compare", label: t("assistant.chat.presets.compare"), prompt: t("assistant.chat.presets.compare") },
        ];

  return (
    <Card className="flex h-full min-h-[560px] flex-col">
      <CardHeader>
        <CardTitle className="eh-h3">
          {mode === "coach" ? t("assistant.coach.title") : t("assistant.chat.title")}
        </CardTitle>
        <CardDescription>
          {mode === "coach"
            ? t("assistant.coach.description")
            : t("assistant.chat.description")}
        </CardDescription>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div
            className="inline-flex rounded-lg border border-border p-0.5"
            role="group"
            aria-label={t("assistant.coach.modeLabel")}
          >
            {(["chat", "coach"] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => onModeChange(item)}
                aria-pressed={mode === item}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs transition-colors",
                  mode === item
                    ? "bg-accent-soft font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                {t(`assistant.coach.modes.${item}`)}
              </button>
            ))}
          </div>
          {mode === "coach" ? (
            <p className="eh-caption text-muted-foreground">
              {t("assistant.coach.disclaimer")}
            </p>
          ) : null}
        </div>

        {mode === "coach" ? (
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={city}
              onChange={(event) => onCityChange(event.target.value)}
              placeholder={t("assistant.coach.cityPlaceholder")}
              aria-label={t("assistant.coach.cityLabel")}
              maxLength={80}
              className="h-8 max-w-56"
            />
            <WeatherSummary city={city} weather={weather} loading={weatherLoading} />
          </div>
        ) : null}

        {!activeProvider ? (
          <EmptyState
            icon={MessageSquare}
            title={t("assistant.chat.noProviderTitle")}
            description={t("assistant.chat.noProviderDesc")}
            className="my-auto"
          />
        ) : (
          <>
            <div
              ref={scrollRef}
              className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1"
              aria-live="polite"
              aria-relevant="additions text"
            >
              {hasMoreMessages ? (
                <div className="flex justify-center pb-1">
                  <Button
                    variant="ghost"
                    size="xs"
                    className="text-muted-foreground"
                    onClick={onLoadEarlier}
                    disabled={loadingEarlier}
                  >
                    {loadingEarlier ? (
                      <LoaderCircle className="animate-spin" data-icon="inline-start" />
                    ) : (
                      <ChevronUp data-icon="inline-start" />
                    )}
                    {t("assistant.chat.loadEarlier", { count: messageTotal })}
                  </Button>
                </div>
              ) : null}
              {messages.length === 0 ? (
                <EmptyState
                  icon={MessageSquare}
                  title={t("assistant.chat.emptyTitle")}
                  description={t("assistant.chat.emptyDesc")}
                  className="border-0 bg-transparent py-6"
                />
              ) : (
                messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    onOpenTransparency={onOpenTransparency}
                  />
                ))
              )}
            </div>

            {error ? (
              <div className="flex items-start justify-between gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                <span className="flex items-start gap-2">
                  <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  {error}
                </span>
                <Button variant="ghost" size="xs" onClick={onDismissError}>
                  {t("assistant.chat.dismiss")}
                </Button>
              </div>
            ) : null}

            <div className="space-y-2 border-t border-border pt-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="eh-caption mr-1 text-muted-foreground">
                  {mode === "coach"
                    ? t("assistant.coach.presetsLabel")
                    : t("assistant.chat.presetLabel")}
                </span>
                {presets.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => setContent(preset.prompt)}
                    className="rounded-full border border-border/70 bg-background px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>

              <Textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
                placeholder={
                  mode === "coach"
                    ? t("assistant.coach.placeholder")
                    : t("assistant.chat.placeholder")
                }
                rows={3}
                maxLength={8000}
                aria-label={
                  mode === "coach" ? t("assistant.coach.title") : t("assistant.chat.title")
                }
              />

              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <div
                  className="inline-flex rounded-lg border border-border p-0.5"
                  role="group"
                  aria-label={t("assistant.chat.styleLabel")}
                >
                  {STYLES.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => onStyleChange(item)}
                      aria-pressed={style === item}
                      className={cn(
                        "rounded-md px-2.5 py-1 text-xs transition-colors",
                        style === item
                          ? "bg-accent-soft font-medium text-foreground"
                          : "text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {t(`assistant.chat.styles.${item}`)}
                    </button>
                  ))}
                </div>

                <Select
                  value={recordId ?? "none"}
                  onValueChange={(value) => onRecordIdChange(value === "none" ? null : value)}
                >
                  <SelectTrigger
                    size="sm"
                    className="min-w-48"
                    aria-label={t("assistant.chat.recordLabel")}
                  >
                    <SelectValue placeholder={t("assistant.chat.recordNone")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t("assistant.chat.recordNone")}</SelectItem>
                    {records.map((record) => (
                      <SelectItem key={record.id} value={record.id}>
                        {recordLabel(record, locale)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Switch
                    checked={includeNotes}
                    onCheckedChange={onIncludeNotesChange}
                    aria-label={t("assistant.chat.includeNotes")}
                  />
                  {t("assistant.chat.includeNotes")}
                </label>

                <span className="ml-auto flex items-center gap-2">
                  {streaming ? (
                    <Button variant="outline" size="sm" onClick={onStop}>
                      <Square data-icon="inline-start" />
                      {t("assistant.chat.stop")}
                    </Button>
                  ) : null}
                  <Button size="sm" onClick={submit} disabled={!canSend}>
                    <Send data-icon="inline-start" />
                    {t("assistant.chat.send")}
                  </Button>
                </span>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="eh-caption text-muted-foreground">
                  {recordsError
                    ? t("assistant.records.error")
                    : t("assistant.chat.disclaimerShort")}
                </p>
                <p className="eh-caption text-muted-foreground">
                  {t("assistant.chat.sendHint")}
                </p>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
