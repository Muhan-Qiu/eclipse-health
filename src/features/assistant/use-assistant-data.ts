import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { errorMessage } from "@/lib/api/error";
import type { HealthRecord } from "@/lib/api/types";
import { assistantApi } from "./api";
import type { AssistantProvider, AssistantSession, ChatMessage } from "./types";

export interface AssistantData {
  providers: AssistantProvider[];
  sessions: AssistantSession[];
  records: HealthRecord[];
  messages: ChatMessage[];
  activeSessionId: string | null;
  loading: boolean;
  messagesLoading: boolean;
  error: string | null;
  recordsError: string | null;
  setActiveSessionId: (id: string | null) => void;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  reloadProviders: () => Promise<AssistantProvider[]>;
  reloadSessions: () => Promise<AssistantSession[]>;
  reloadRecords: () => Promise<void>;
  reloadMessages: (sessionId: string) => Promise<void>;
  createSession: (input: {
    providerId?: string | null;
    style?: string;
    recordId?: string | null;
  }) => Promise<AssistantSession | null>;
  deleteSession: (id: string) => Promise<void>;
}

export function useAssistantData(): AssistantData {
  const [providers, setProviders] = useState<AssistantProvider[]>([]);
  const [sessions, setSessions] = useState<AssistantSession[]>([]);
  const [records, setRecords] = useState<HealthRecord[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const activeRef = useRef<string | null>(null);

  const setActiveSessionId = useCallback((id: string | null) => {
    activeRef.current = id;
    setActiveSessionIdState(id);
    if (id === null) setMessages([]);
  }, []);

  const reloadProviders = useCallback(async () => {
    const items = await assistantApi.providers.list();
    setProviders(items);
    return items;
  }, []);

  const reloadSessions = useCallback(async () => {
    const items = await assistantApi.sessions.list();
    setSessions(items);
    return items;
  }, []);

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
      const items = await assistantApi.sessions.messages(sessionId);
      // 会话已切换时丢弃过期响应
      if (activeRef.current === sessionId) setMessages(items);
    } catch (cause) {
      if (activeRef.current === sessionId) setError(errorMessage(cause));
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [providerItems, sessionItems] = await Promise.all([
          assistantApi.providers.list(),
          assistantApi.sessions.list(),
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
        return created;
      } catch (cause) {
        setError(errorMessage(cause));
        return null;
      }
    },
    [reloadSessions, setActiveSessionId],
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

  return useMemo(
    () => ({
      providers,
      sessions,
      records,
      messages,
      activeSessionId,
      loading,
      messagesLoading,
      error,
      recordsError,
      setActiveSessionId,
      setMessages,
      reloadProviders,
      reloadSessions,
      reloadRecords,
      reloadMessages,
      createSession,
      deleteSession,
    }),
    [
      providers,
      sessions,
      records,
      messages,
      activeSessionId,
      loading,
      messagesLoading,
      error,
      recordsError,
      setActiveSessionId,
      reloadProviders,
      reloadSessions,
      reloadRecords,
      reloadMessages,
      createSession,
      deleteSession,
    ],
  );
}
