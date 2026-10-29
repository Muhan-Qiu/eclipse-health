import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  CircleAlert,
  FileText,
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
import type { AssistantProvider, AssistantStyle, ChatMessage } from "./types";

const STYLES: AssistantStyle[] = ["brief", "detailed", "doctor"];

function recordLabel(record: HealthRecord, locale: string): string {
  const when = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(record.capturedAt));
  const seconds = record.durationSec ? `${Math.round(record.durationSec)}s` : "";
  return [when, seconds, record.leads.join("/")].filter(Boolean).join(" · ");
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
          <p className="text-sm leading-6 whitespace-pre-wrap">
            {message.content}
            {message.status === "streaming" ? (
              <span
                className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-foreground align-text-bottom"
                aria-hidden="true"
              />
            ) : null}
          </p>
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
  }) => void;
  onStop: () => void;
  onOpenTransparency: (message: ChatMessage) => void;
  style: AssistantStyle;
  onStyleChange: (style: AssistantStyle) => void;
  recordId: string | null;
  onRecordIdChange: (id: string | null) => void;
  includeNotes: boolean;
  onIncludeNotesChange: (value: boolean) => void;
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
    });
    setContent("");
  };

  const presets = [
    t("assistant.chat.presets.abnormal"),
    t("assistant.chat.presets.care"),
    t("assistant.chat.presets.hrv"),
    t("assistant.chat.presets.compare"),
  ];

  return (
    <Card className="flex h-full min-h-[560px] flex-col">
      <CardHeader>
        <CardTitle className="eh-h3">{t("assistant.chat.title")}</CardTitle>
        <CardDescription>{t("assistant.chat.description")}</CardDescription>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
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
                  {t("assistant.privacy.cancel")}
                </Button>
              </div>
            ) : null}

            <div className="space-y-2 border-t border-border pt-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="eh-caption mr-1 text-muted-foreground">
                  {t("assistant.chat.presetLabel")}
                </span>
                {presets.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setContent(preset)}
                    className="rounded-full border border-border/70 bg-background px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {preset}
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
                placeholder={t("assistant.chat.placeholder")}
                rows={3}
                maxLength={8000}
                aria-label={t("assistant.chat.title")}
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
