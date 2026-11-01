import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { errorMessage } from "@/lib/api/error";
import type { HealthRecord } from "@/lib/api/types";
import { assistantApi } from "./api";
import type { AssistantProvider, AssistantSession, ChatMessage } from "./types";

const MESSAGE_PAGE_SIZE = 100;

export interface AssistantData {
  providers: AssistantProvider[];
  sessions: AssistantSession[];
  records: HealthRecord[];
  messages: ChatMessage[];
  activeSessionId: string | null;
  sessionQuery: string;
  loading: boolean;
  messagesLoading: boolean;
  loadingEarlier: boolean;
  hasMoreMessages: boolean;
  messageTotal: number;
  error: string | null;
  recordsError: string | null;
  setActiveSessionId: (id: string | null) => void;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  reloadProviders: () => Promise<AssistantProvider[]>;
  reloadSessions: () => Promise<AssistantSession[]>;
  searchSessions: (query: string) => Promise<void>;
  reloadRecords: () => Promise<void>;
  reloadMessages: (sessionId: string) => Promise<void>;
  loadEarlierMessages: () => Promise<void>;
  createSession: (input: {
    providerId?: string | null;
    style?: string;
    recordId?: string | null;
  }) => Promise<AssistantSession | null>;
  renameSession: (id: string, title: string) => Promise<boolean>;
  deleteSession: (id: string) => Promise<void>;
  exportSession: (id: string, includeToolArgs?: boolean) => Promise<boolean>;
}

function downloadMarkdown(text: string, filename: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // 立刻 revoke 在部分 WebView 会取消下载，延迟释放。
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function useAssistantData(): AssistantData {
  const [providers, setProviders] = useState<AssistantProvider[]>([]);
  const [sessions, setSessions] = useState<AssistantSession[]>([]);
  const [records, setRecords] = useState<HealthRecord[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(null);
  const [sessionQuery, setSessionQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [messageTotal, setMessageTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const activeRef = useRef<string | null>(null);
  const queryRef = useRef("");

  const setActiveSessionId = useCallback((id: string | null) => {
    activeRef.current = id;
    setActiveSessionIdState(id);
    if (id === null) {
      setMessages([]);
      setHasMoreMessages(false);
      setMessageTotal(0);
    }
  }, []);

  const reloadProviders = useCallback(async () => {
    const items = await assistantApi.providers.list();
    setProviders(items);
    return items;
  }, []);

  const reloadSessions = useCallback(async () => {
    const items = await assistantApi.sessions.list({ q: queryRef.current });
    setSessions(items);
    return items;
  }, []);

  const searchSessions = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      queryRef.current = trimmed;
      setSessionQuery(query);
      try {
        const items = await assistantApi.sessions.list({ q: trimmed });
        setSessions(items);
      } catch (cause) {
        setError(errorMessage(cause));
      }
    },
    [],
  );

  const reloadRecords = useCallback(async () => {
    try {
      const page = await assistantApi.records.list();
      setRecords(Array.isArray(page.items) ? page.items : []);
      setRecordsError(null);
    } catch (cause) {
      setRecords([]);
      setRecordsError(errorMessage(cause));
    }
  }, []);

  const reloadMessages = useCallback(async (sessionId: string) => {
    setMessagesLoading(true);
    try {
      // 后端按插入顺序返回；先取最新一页再翻转为正序，长会话首屏不会停在旧消息。
      const page = await assistantApi.sessions.messages(sessionId, {
        limit: MESSAGE_PAGE_SIZE,
        order: "desc",
      });
      // 会话已切换时丢弃过期响应
      if (activeRef.current !== sessionId) return;
      setMessages([...page.items].reverse());
      setHasMoreMessages(page.hasMore);
      setMessageTotal(page.total);
    } catch (cause) {
      if (activeRef.current === sessionId) setError(errorMessage(cause));
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const loadEarlierMessages = useCallback(async () => {
    const sessionId = activeRef.current;
    if (!sessionId || loadingEarlier || !hasMoreMessages) return;
    setLoadingEarlier(true);
    try {
      const offset = messages.length;
      const page = await assistantApi.sessions.messages(sessionId, {
        limit: MESSAGE_PAGE_SIZE,
        offset,
        order: "desc",
      });
      if (activeRef.current !== sessionId) return;
      setMessages((current) => [...[...page.items].reverse(), ...current]);
      setHasMoreMessages(page.hasMore);
      setMessageTotal(page.total);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoadingEarlier(false);
    }
  }, [hasMoreMessages, loadingEarlier, messages.length]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [providerItems, sessionItems] = await Promise.all([
          assistantApi.providers.list(),
          assistantApi.sessions.list({}),
        ]);
        if (cancelled) return;
        setProviders(providerItems);
        setSessions(sessionItems);
        const first = sessionItems[0]?.id ?? null;
        if (first) {
          activeRef.current = first;
          setActiveSessionIdState(first);
        }
      } catch (cause) {
        if (!cancelled) setError(errorMessage(cause));
      } finally {
        if (!cancelled) setLoading(false);
      }
      await reloadRecords();
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadRecords]);

  useEffect(() => {
    if (!activeSessionId) return;
    void reloadMessages(activeSessionId);
  }, [activeSessionId, reloadMessages]);

  const createSession = useCallback(
    async (input: {
      providerId?: string | null;
      style?: string;
      recordId?: string | null;
    }) => {
      try {
        const created = await assistantApi.sessions.create(input);
        await reloadSessions();
        setActiveSessionId(created.id);
        setMessages([]);
        setHasMoreMessages(false);
        setMessageTotal(0);
        return created;
      } catch (cause) {
        setError(errorMessage(cause));
        return null;
      }
    },
    [reloadSessions, setActiveSessionId],
  );

  const renameSession = useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return false;
      try {
        const updated = await assistantApi.sessions.rename(id, trimmed);
        setSessions((current) =>
          current.map((item) => (item.id === id ? { ...item, ...updated } : item)),
        );
        return true;
      } catch (cause) {
        setError(errorMessage(cause));
        return false;
      }
    },
    [],
  );

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await assistantApi.sessions.remove(id);
        const items = await reloadSessions();
        if (activeRef.current === id) {
          const next = items[0]?.id ?? null;
          setActiveSessionId(next);
        }
      } catch (cause) {
        setError(errorMessage(cause));
      }
    },
    [reloadSessions, setActiveSessionId],
  );

  const exportSession = useCallback(
    async (id: string, includeToolArgs = false) => {
      try {
        const { text, filename } = await assistantApi.sessions.exportMarkdown(id, {
          includeToolArgs,
        });
        downloadMarkdown(text, filename);
        return true;
      } catch (cause) {
        setError(errorMessage(cause));
        return false;
      }
    },
    [],
  );

  return useMemo(
    () => ({
      providers,
      sessions,
      records,
      messages,
      activeSessionId,
      sessionQuery,
      loading,
      messagesLoading,
      loadingEarlier,
      hasMoreMessages,
      messageTotal,
      error,
      recordsError,
      setActiveSessionId,
      setMessages,
      reloadProviders,
      reloadSessions,
      searchSessions,
      reloadRecords,
      reloadMessages,
      loadEarlierMessages,
      createSession,
      renameSession,
      deleteSession,
      exportSession,
    }),
    [
      providers,
      sessions,
      records,
      messages,
      activeSessionId,
      sessionQuery,
      loading,
      messagesLoading,
      loadingEarlier,
      hasMoreMessages,
      messageTotal,
      error,
      recordsError,
      setActiveSessionId,
      reloadProviders,
      reloadSessions,
      searchSessions,
      reloadRecords,
      reloadMessages,
      loadEarlierMessages,
      createSession,
      renameSession,
      deleteSession,
      exportSession,
    ],
  );
}
