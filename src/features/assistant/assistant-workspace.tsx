import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, ShieldCheck } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/page-header";
import { errorMessage } from "@/lib/api/error";
import { assistantApi } from "./api";
import { ChatPanel } from "./chat-panel";
import { PrivacyDialog } from "./privacy-dialog";
import { ProviderCard } from "./provider-card";
import { SessionList } from "./session-list";
import { TransparencySheet } from "./transparency-sheet";
import type {
  AssistantStyle,
  ChatMessage,
  SendMessageBody,
  StreamEvent,
  Transparency,
} from "./types";
import { useAssistantData } from "./use-assistant-data";

const PRIVACY_KEY = "eh.assistant.privacy.";

function privacyAcknowledged(providerId: string): boolean {
  try {
    return localStorage.getItem(`${PRIVACY_KEY}${providerId}`) === "1";
  } catch {
    return false;
  }
}

function rememberPrivacy(providerId: string): void {
  try {
    localStorage.setItem(`${PRIVACY_KEY}${providerId}`, "1");
  } catch {
    // 隐私模式或存储被禁用时，本次会话仍然尊重用户刚刚的确认
  }
}

function localId(prefix: string): string {
  return `local-${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function applyEvent(message: ChatMessage, event: StreamEvent): ChatMessage {
  switch (event.event) {
    case "start":
      return {
        ...message,
        serverId: event.data.assistantMessageId,
        model: event.data.provider.model,
        providerId: event.data.provider.id,
      };
    case "token":
      return { ...message, content: message.content + event.data.text };
    case "tool_call":
      return {
        ...message,
        toolCalls: [
          ...message.toolCalls,
          {
            id: event.data.id,
            name: event.data.name,
            args: event.data.args,
            resultSummary: "",
            ok: true,
            durationMs: 0,
            pending: true,
          },
        ],
      };
    case "tool_result":
      return {
        ...message,
        toolCalls: message.toolCalls.map((call) =>
          call.id === event.data.id
            ? {
                ...call,
                ok: event.data.ok,
                durationMs: event.data.durationMs,
                resultSummary: event.data.resultSummary,
                pending: false,
              }
            : call,
        ),
      };
    case "citation":
      return message.citations.some(
        (item) => item.kind === event.data.kind && item.id === event.data.id,
      )
        ? message
        : { ...message, citations: [...message.citations, event.data] };
    case "done":
      return {
        ...message,
        content: event.data.content || message.content,
        citations: event.data.citations ?? message.citations,
        transparency: event.data.transparency ?? message.transparency,
        usage: event.data.usage ?? message.usage,
        durationMs: event.data.durationMs ?? message.durationMs,
        status: event.data.cancelled ? "cancelled" : "completed",
      };
    case "error":
      return { ...message, status: "error", error: event.data };
    default:
      return message;
  }
}

export function AssistantWorkspace() {
  const { t } = useTranslation();
  const data = useAssistantData();
  const [activeProviderId, setActiveProviderId] = useState<string | null>(null);
  const [style, setStyle] = useState<AssistantStyle>("brief");
  const [recordId, setRecordId] = useState<string | null>(null);
  const [includeNotes, setIncludeNotes] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingSend, setPendingSend] = useState<SendMessageBody | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [transparency, setTransparency] = useState<Transparency | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const abortFallbackRef = useRef<number | null>(null);
  const activeServerIdRef = useRef<string | null>(null);
  const appliedSessionRef = useRef<string | null>(null);

  const { providers, sessions, records, messages, activeSessionId } = data;
  const activeProvider = useMemo(
    () => providers.find((provider) => provider.id === activeProviderId) ?? null,
    [providers, activeProviderId],
  );
  const hasLocalProvider = providers.some(
    (provider) => provider.isLocal && provider.enabled,
  );

  // provider 列表变化时保持一个可用的选择
  useEffect(() => {
    setActiveProviderId((current) => {
      if (current && providers.some((item) => item.id === current && item.enabled)) {
        return current;
      }
      return providers.find((item) => item.enabled)?.id ?? providers[0]?.id ?? null;
    });
  }, [providers]);

  // 首次进入或切换会话时，套用会话保存的风格/记录/provider
  useEffect(() => {
    if (!activeSessionId || appliedSessionRef.current === activeSessionId) return;
    const session = sessions.find((item) => item.id === activeSessionId);
    if (!session) return;
    appliedSessionRef.current = activeSessionId;
    setStyle(session.style);
    setRecordId(session.recordId);
    setIncludeNotes(session.hasNotes);
    if (
      session.providerId &&
      providers.some((item) => item.id === session.providerId && item.enabled)
    ) {
      setActiveProviderId(session.providerId);
    }
  }, [activeSessionId, sessions, providers]);

  const selectSession = useCallback(
    (id: string) => {
      appliedSessionRef.current = id;
      const session = sessions.find((item) => item.id === id);
      data.setActiveSessionId(id);
      if (session) {
        setStyle(session.style);
        setRecordId(session.recordId);
        setIncludeNotes(session.hasNotes);
        if (session.providerId) setActiveProviderId(session.providerId);
      }
    },
    [data, sessions],
  );

  const createSession = useCallback(async () => {
    const created = await data.createSession({
      providerId: activeProviderId,
      style,
      recordId,
    });
    if (created) {
      appliedSessionRef.current = created.id;
      setRecordId(created.recordId);
    }
  }, [activeProviderId, data, recordId, style]);

  const openTransparency = useCallback(async (message: ChatMessage) => {
    if (message.transparency) {
      setTransparency(message.transparency);
      setSheetOpen(true);
      return;
    }
    if (message.id.startsWith("local-")) return;
    try {
      const fetched = await assistantApi.messages.transparency(message.id);
      setTransparency(fetched);
      setSheetOpen(true);
    } catch (cause) {
      setActionError(errorMessage(cause));
    }
  }, []);

  const sendNow = useCallback(
    async (body: SendMessageBody) => {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const created = await data.createSession({
          providerId: body.providerId,
          style: body.style,
          recordId: body.recordId ?? null,
        });
        if (!created) return;
        sessionId = created.id;
      }

      const timestamp = new Date().toISOString();
      const userMessage: ChatMessage = {
        id: localId("user"),
        sessionId,
        role: "user",
        content: body.content,
        status: "completed",
        citations: [],
        toolCalls: [],
        createdAt: timestamp,
      };
      const assistantId = localId("assistant");
      const assistantMessage: ChatMessage = {
        id: assistantId,
        sessionId,
        role: "assistant",
        content: "",
        status: "streaming",
        citations: [],
        toolCalls: [],
        createdAt: timestamp,
      };
      data.setMessages((current) => [...current, userMessage, assistantMessage]);
      setActionError(null);
      setStreaming(true);
      activeServerIdRef.current = null;

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await assistantApi.stream(sessionId, body, controller.signal, (event) => {
          // start 事件带回服务端消息 ID，取消按钮据此调用取消 API。
          if (event.event === "start") {
            activeServerIdRef.current = event.data.assistantMessageId;
          }
          data.setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? applyEvent(message, event) : message,
            ),
          );
        });
      } catch (cause) {
        if (controller.signal.aborted) {
          data.setMessages((current) =>
            current.map((message) =>
              message.id === assistantId && message.status === "streaming"
                ? { ...message, status: "cancelled" }
                : message,
            ),
          );
        } else {
          const message = errorMessage(cause);
          setActionError(message);
          data.setMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    status: "error",
                    error: { code: "send_failed", message },
                  }
                : item,
            ),
          );
        }
      } finally {
        if (abortFallbackRef.current !== null) {
          window.clearTimeout(abortFallbackRef.current);
          abortFallbackRef.current = null;
        }
        activeServerIdRef.current = null;
        abortRef.current = null;
        setStreaming(false);
        // 用服务端记录对齐真实 ID、工具调用与透明面板
        await data.reloadMessages(sessionId);
        await data.reloadSessions();
      }
    },
    [activeSessionId, data],
  );

  const handleSend = useCallback(
    (input: {
      content: string;
      style: AssistantStyle;
      recordId?: string;
      includeNotes: boolean;
    }) => {
      if (!activeProvider) return;
      const body: SendMessageBody = {
        content: input.content,
        style: input.style,
        providerId: activeProvider.id,
        includeNotes: input.includeNotes,
      };
      if (input.recordId) body.recordId = input.recordId;
      if (!activeProvider.isLocal && !privacyAcknowledged(activeProvider.id)) {
        setPendingSend(body);
        return;
      }
      void sendNow(body);
    },
    [activeProvider, sendNow],
  );

  const stop = useCallback(() => {
    const serverId = activeServerIdRef.current;
    if (!serverId) {
      abortRef.current?.abort();
      return;
    }
    // 先让服务端停下并落库；5 秒内没有收到 done 再断开连接兜底。
    void assistantApi.messages.cancel(serverId).catch(() => {
      abortRef.current?.abort();
    });
    if (abortFallbackRef.current !== null) {
      window.clearTimeout(abortFallbackRef.current);
    }
    abortFallbackRef.current = window.setTimeout(() => {
      abortRef.current?.abort();
    }, 5_000);
  }, []);

  const confirmPrivacy = useCallback(() => {
    if (!pendingSend) return;
    rememberPrivacy(pendingSend.providerId);
    const body = pendingSend;
    setPendingSend(null);
    void sendNow(body);
  }, [pendingSend, sendNow]);

  const useLocalProvider = useCallback(() => {
    const local = providers.find((provider) => provider.isLocal && provider.enabled);
    if (!local) {
      setPendingSend(null);
      return;
    }
    setActiveProviderId(local.id);
    const body = pendingSend ? { ...pendingSend, providerId: local.id } : null;
    setPendingSend(null);
    if (body) void sendNow(body);
  }, [pendingSend, providers, sendNow]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
      if (abortFallbackRef.current !== null) {
        window.clearTimeout(abortFallbackRef.current);
      }
    },
    [],
  );

  return (
    <>
      <PageHeader
        eyebrow={t("assistant.eyebrow")}
        title={t("assistant.title")}
        description={t("assistant.description")}
        actions={
          activeProvider ? (
            <Badge variant="outline" className="gap-1.5 font-normal">
              <Bot className="size-3" aria-hidden="true" />
              {activeProvider.label}
              {activeProvider.isLocal ? ` · ${t("assistant.providers.localBadge")}` : ""}
            </Badge>
          ) : (
            <Badge variant="outline" className="font-normal text-muted-foreground">
              {t("assistant.chat.noProviderTitle")}
            </Badge>
          )
        }
      />

      <Alert className="mb-4">
        <ShieldCheck aria-hidden="true" />
        <AlertDescription className="eh-caption">
          {t("assistant.disclaimer")}
        </AlertDescription>
      </Alert>

      <div className="eh-grid">
        <div className="space-y-4 desk:col-span-3 xl:col-span-4">
          <ProviderCard
            providers={providers}
            activeId={activeProviderId}
            onActiveChange={setActiveProviderId}
            onProvidersChanged={async () => {
              await data.reloadProviders();
            }}
            onError={setActionError}
          />
          <SessionList
            sessions={sessions}
            activeId={activeSessionId}
            query={data.sessionQuery}
            onCreate={() => void createSession()}
            onSelect={selectSession}
            onDelete={(id) => void data.deleteSession(id)}
            onRename={(id, title) => void data.renameSession(id, title)}
            onExport={(id) => void data.exportSession(id)}
            onSearch={(query) => void data.searchSessions(query)}
          />
        </div>

        <div className="desk:col-span-5 xl:col-span-8">
          <ChatPanel
            messages={messages}
            streaming={streaming}
            providers={providers}
            activeProviderId={activeProviderId}
            records={records}
            recordsError={data.recordsError}
            error={actionError ?? data.error}
            onDismissError={() => setActionError(null)}
            onSend={handleSend}
            onStop={stop}
            onOpenTransparency={(message) => void openTransparency(message)}
            style={style}
            onStyleChange={setStyle}
            recordId={recordId}
            onRecordIdChange={setRecordId}
            includeNotes={includeNotes}
            onIncludeNotesChange={setIncludeNotes}
            hasMoreMessages={data.hasMoreMessages}
            loadingEarlier={data.loadingEarlier}
            messageTotal={data.messageTotal}
            onLoadEarlier={() => void data.loadEarlierMessages()}
          />
        </div>
      </div>

      <TransparencySheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        transparency={transparency}
      />

      <PrivacyDialog
        open={Boolean(pendingSend)}
        provider={
          providers.find((provider) => provider.id === pendingSend?.providerId) ?? null
        }
        includeNotes={pendingSend?.includeNotes ?? false}
        hasLocalProvider={hasLocalProvider}
        onCancel={() => setPendingSend(null)}
        onConfirm={confirmPrivacy}
        onUseLocal={useLocalProvider}
      />
    </>
  );
}
