import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileUp } from "lucide-react";
import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/error";
import type { ImportCommitBody, ImportPreview } from "@/lib/api/types";
import {
  commitHealthImport,
  previewHealthImport,
  type HealthImportCommitResult,
  type ImportRecordCounts,
  type ImportSourceKind,
} from "./health-import-api";
import {
  collectDroppedFiles,
  prepareImportSource,
  validateDroppedFiles,
  type DroppedFile,
} from "@/lib/zip";
import {
  commitAgentSession,
  createAgentSession,
  discardAgentSession,
  fetchAllAgentProposals,
  runAgentSession,
  type AgentCommitResult,
  type AgentProposal,
  type AgentSession,
} from "./import-agent-api";
import { ImportDialog, type AgentEventItem } from "./import-dialog";

interface ImportContextValue {
  openPicker: () => void;
}

const ImportContext = createContext<ImportContextValue | null>(null);

const EMPTY_COUNTS: ImportRecordCounts = {
  steps: 0,
  heartRate: 0,
  sleep: 0,
  bodyMass: 0,
  bloodPressure: 0,
  ecg: 0,
};

const MAX_AGENT_FILES = 20;

export interface AgentView {
  session: AgentSession;
  status: "created" | "running" | "ready" | "error" | "committed";
  events: AgentEventItem[];
  thought: string;
  proposals: AgentProposal[];
  selectedKinds: string[];
  error: ApiError | null;
  summary: string | null;
  toolCalls: number;
  commit: AgentCommitResult | null;
}

function localError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  const code = error instanceof Error ? error.message : "import_failed";
  const known = new Set([
    "empty_selection",
    "too_many_files",
    "archive_too_large",
    "file_too_large",
  ]);
  return new ApiError(code, {
    code: known.has(code) ? code : "import_failed",
    status: known.has(code) ? 413 : undefined,
  });
}

function countsOf(proposals: AgentProposal[]): ImportRecordCounts {
  const next = { ...EMPTY_COUNTS };
  for (const item of proposals) {
    if (item.kind === "steps") next.steps += 1;
    else if (item.kind === "heart-rate" || item.kind === "resting-heart-rate") {
      next.heartRate += 1;
    } else if (item.kind === "sleep") next.sleep += 1;
    else if (item.kind === "body-mass") next.bodyMass += 1;
    else if (item.kind === "blood-pressure") next.bloodPressure += 1;
    else if (item.kind === "ecg") next.ecg += 1;
  }
  return next;
}

function DropOverlay({ visible }: { visible: boolean }) {
  const { t } = useTranslation();
  if (!visible) return null;
  return (
    <div
      className="pointer-events-none fixed inset-0 z-[70] flex items-center justify-center bg-background/60 p-8 backdrop-blur-sm"
      aria-hidden="true"
    >
      <div className="flex w-full max-w-md flex-col items-center rounded-2xl border-2 border-dashed border-primary bg-surface px-8 py-12 text-center shadow-card">
        <div className="flex size-12 items-center justify-center rounded-full bg-accent-soft text-primary">
          <FileUp className="size-6" />
        </div>
        <p className="eh-h3 mt-4">{t("imports.dropTitle")}</p>
        <p className="eh-small mt-1.5 text-muted-foreground">
          {t("imports.dropDesc")}
        </p>
      </div>
    </div>
  );
}

export function ImportProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dirInputRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const previewRef = useRef<ImportPreview | null>(null);
  const sourceRef = useRef<ImportSourceKind>("auto");
  const filesRef = useRef<DroppedFile[] | null>(null);
  const agentRef = useRef<AgentView | null>(null);
  const agentAbortRef = useRef<AbortController | null>(null);
  const demoStartedRef = useRef(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [commitError, setCommitError] = useState<ApiError | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [source, setSource] = useState<ImportSourceKind>("auto");
  const [recordCounts, setRecordCounts] =
    useState<ImportRecordCounts>(EMPTY_COUNTS);
  const [totalRecords, setTotalRecords] = useState(0);
  const [commitResult, setCommitResult] =
    useState<HealthImportCommitResult | null>(null);
  const [hasSelection, setHasSelection] = useState(false);
  const [agent, setAgent] = useState<AgentView | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentCommitting, setAgentCommitting] = useState(false);

  useEffect(() => {
    previewRef.current = preview;
  }, [preview]);
  useEffect(() => {
    agentRef.current = agent;
  }, [agent]);

  const updateAgent = useCallback((patch: Partial<AgentView>) => {
    setAgent((current) => (current ? { ...current, ...patch } : current));
  }, []);

  const discardStandard = useCallback(async () => {
    const current = previewRef.current;
    previewRef.current = null;
    setPreview(null);
    setCommitError(null);
    setRecordCounts({ ...EMPTY_COUNTS });
    setTotalRecords(0);
    if (current) {
      try {
        await api.imports.discard(current.importId);
      } catch {
        // 临时目录由后端 TTL 兜底，这里不打扰用户
      }
    }
  }, []);

  const discardAgent = useCallback(async () => {
    const current = agentRef.current;
    agentAbortRef.current?.abort();
    agentAbortRef.current = null;
    agentRef.current = null;
    setAgent(null);
    if (current && current.status !== "committed") {
      try {
        await discardAgentSession(current.session.sessionId);
      } catch {
        // TTL 兜底
      }
    }
  }, []);

  const startFiles = useCallback(
    async (dropped: DroppedFile[]) => {
      if (busyRef.current) return;
      busyRef.current = true;
      filesRef.current = dropped;
      setHasSelection(dropped.length > 0);
      const previous = previewRef.current;
      previewRef.current = null;
      if (previous) {
        void api.imports.discard(previous.importId).catch(() => undefined);
      }
      setDialogOpen(true);
      setBusy(true);
      setPreview(null);
      setError(null);
      setCommitError(null);
      setCommitResult(null);
      setRecordCounts({ ...EMPTY_COUNTS });
      setTotalRecords(0);
      setDragActive(false);
      try {
        validateDroppedFiles(dropped);
        const file = await prepareImportSource(dropped);
        const result = await previewHealthImport(file, sourceRef.current);
        setPreview(result);
        setRecordCounts(result.recordCounts);
        setTotalRecords(result.totalRecords);
      } catch (caught) {
        setError(localError(caught));
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [],
  );

  const openPicker = useCallback(() => {
    setCommitResult(null);
    setError(null);
    setPreview(null);
    void discardAgent();
    setDialogOpen(true);
    window.setTimeout(() => fileInputRef.current?.click(), 0);
  }, [discardAgent]);

  const openDialog = useCallback(() => {
    setCommitResult(null);
    setError(null);
    setPreview(null);
    setDialogOpen(true);
  }, []);

  const chooseFiles = useCallback(() => {
    setCommitResult(null);
    setError(null);
    setPreview(null);
    window.setTimeout(() => fileInputRef.current?.click(), 0);
  }, []);

  const chooseFolder = useCallback(() => {
    setCommitResult(null);
    setError(null);
    setPreview(null);
    window.setTimeout(() => dirInputRef.current?.click(), 0);
  }, []);

  const pickAnother = useCallback(() => {
    void discardCurrentAll();
    setError(null);
    setDialogOpen(true);
    window.setTimeout(() => fileInputRef.current?.click(), 0);
  }, []);

  const discardCurrentAll = useCallback(async () => {
    agentAbortRef.current?.abort();
    agentAbortRef.current = null;
    agentRef.current = null;
    setAgent(null);
    await discardStandard();
  }, [discardStandard]);

  const closeDialog = useCallback(() => {
    setDialogOpen(false);
    setError(null);
    setCommitResult(null);
    filesRef.current = null;
    setHasSelection(false);
    void discardCurrentAll();
  }, [discardCurrentAll]);

  const finishBundle = useCallback(() => {
    setDialogOpen(false);
    setCommitResult(null);
    setHasSelection(false);
    filesRef.current = null;
    navigate("/records");
  }, [navigate]);

  // 导入提交不经过 react-query，主动让健康数据/记录/趋势/卡片重新取数。
  const refreshImportedData = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["health-records"] });
    void queryClient.invalidateQueries({ queryKey: ["records"] });
    void queryClient.invalidateQueries({ queryKey: ["trends"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard", "cards"] });
  }, [queryClient]);

  const commit = useCallback(
    async (body: ImportCommitBody) => {
      const current = previewRef.current;
      if (!current || committing) return;
      setCommitting(true);
      setCommitError(null);
      try {
        const result = await commitHealthImport(current.importId, body);
        refreshImportedData();
        previewRef.current = null;
        setPreview(null);
        if (totalRecords > 0) {
          // 健康数据包：留在对话框里显示成功/跳过/失败计数。
          setCommitResult(result);
          toast.success(t("imports.success"));
          return;
        }
        setDialogOpen(false);
        toast.success(t("imports.success"));
        navigate(`/records/${encodeURIComponent(result.recordId)}`);
      } catch (caught) {
        setCommitError(localError(caught));
      } finally {
        setCommitting(false);
      }
    },
    [committing, navigate, refreshImportedData, t, totalRecords],
  );

  /* ---------------- Agent 流程 ---------------- */

  const startAgentSession = useCallback(async () => {
    const files = filesRef.current;
    if (!files?.length || agentBusy) return;
    if (files.length > MAX_AGENT_FILES) {
      setError(
        new ApiError(t("imports.agent.errors.tooManyFiles", { max: MAX_AGENT_FILES }), {
          code: "too_many_files",
          status: 413,
        }),
      );
      return;
    }
    setAgentBusy(true);
    setError(null);
    try {
      const session = await createAgentSession(files.map((item) => item.file));
      setAgent({
        session,
        status: "created",
        events: [],
        thought: "",
        proposals: [],
        selectedKinds: [],
        error: null,
        summary: null,
        toolCalls: 0,
        commit: null,
      });
    } catch (caught) {
      setError(localError(caught));
    } finally {
      setAgentBusy(false);
    }
  }, [agentBusy, t]);

  const runAgent = useCallback(async () => {
    const current = agentRef.current;
    if (!current || current.status === "running") return;
    const controller = new AbortController();
    agentAbortRef.current = controller;
    const sessionId = current.session.sessionId;
    let thought = "";
    const pushEvent = (item: Omit<AgentEventItem, "id">) => {
      setAgent((value) =>
        value
          ? {
              ...value,
              events: [
                ...value.events.slice(-79),
                { ...item, id: `${Date.now()}-${value.events.length}` },
              ],
            }
          : value,
      );
    };
    updateAgent({ status: "running", error: null, commit: null, events: [] });

    await runAgentSession(sessionId, {
      signal: controller.signal,
      onStatus: (event) => {
        updateAgent({ toolCalls: event.toolCalls ?? 0 });
        pushEvent({
          kind: "status",
          name: event.phase,
          detail: event.provider,
        });
      },
      onToken: (text) => {
        thought = `${thought}${text}`.slice(-600);
        updateAgent({ thought });
      },
      onToolCall: (event) => {
        pushEvent({ kind: "tool", name: event.name });
      },
      onToolResult: (event) => {
        pushEvent({
          kind: "result",
          name: event.name,
          ok: event.ok,
          detail: event.resultSummary || event.error,
        });
      },
      onPreview: (event) => {
        pushEvent({
          kind: "status",
          name: "preview",
          detail: `${event.count}/${event.total}`,
        });
      },
      onError: (event) => {
        updateAgent({
          status: "error",
          error: new ApiError(event.message, { code: event.code }),
        });
        pushEvent({ kind: "error", name: event.code, detail: event.message, ok: false });
      },
      onDone: async (event) => {
        updateAgent({
          status: "ready",
          summary: event.summary ?? null,
          toolCalls: event.toolCalls ?? 0,
        });
        try {
          const proposals = await fetchAllAgentProposals(sessionId);
          const kinds = Array.from(new Set(proposals.map((item) => item.kind)));
          setAgent((value) =>
            value
              ? {
                  ...value,
                  status: "ready",
                  proposals,
                  selectedKinds: kinds,
                  summary: event.summary ?? value.summary,
                  toolCalls: event.toolCalls ?? value.toolCalls,
                }
              : value,
          );
          setRecordCounts(countsOf(proposals));
          setTotalRecords(proposals.length);
        } catch (caught) {
          updateAgent({
            status: "error",
            error: localError(caught),
          });
        }
      },
    });
  }, [updateAgent]);

  const stopAgent = useCallback(() => {
    agentAbortRef.current?.abort();
  }, []);

  const toggleAgentKind = useCallback((kind: string) => {
    setAgent((value) => {
      if (!value) return value;
      const selected = value.selectedKinds.includes(kind)
        ? value.selectedKinds.filter((item) => item !== kind)
        : [...value.selectedKinds, kind];
      return { ...value, selectedKinds: selected };
    });
  }, []);

  const setAgentKinds = useCallback((kinds: string[]) => {
    setAgent((value) => (value ? { ...value, selectedKinds: kinds } : value));
  }, []);

  const commitAgent = useCallback(
    async (memberId: string) => {
      const current = agentRef.current;
      if (!current || agentCommitting) return;
      setAgentCommitting(true);
      try {
        const allKinds = Array.from(
          new Set(current.proposals.map((item) => item.kind)),
        );
        const allSelected = allKinds.every((kind) =>
          current.selectedKinds.includes(kind),
        );
        const records = allSelected
          ? undefined
          : current.proposals
              .filter((item) => current.selectedKinds.includes(item.kind))
              .map((item) => item.id);
        const result = await commitAgentSession(current.session.sessionId, {
          records,
          memberId: memberId || undefined,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        });
        updateAgent({ status: "committed", commit: result });
        refreshImportedData();
        toast.success(t("imports.agent.doneTitle"));
      } catch (caught) {
        updateAgent({ error: localError(caught) });
      } finally {
        setAgentCommitting(false);
      }
    },
    [agentCommitting, refreshImportedData, t, updateAgent],
  );

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const param = new URLSearchParams(window.location.search).get("import");
    if (param) setDialogOpen(true);
  }, []);

  /* 开发/截图用：?import=agent 自动走一遍演示解析。 */
  useEffect(() => {
    if (!import.meta.env.DEV || demoStartedRef.current) return;
    const param = new URLSearchParams(window.location.search).get("import");
    if (param !== "agent" && param !== "agent-ready") return;
    demoStartedRef.current = true;
    const demo = new File(["date,steps\n2026-11-01,8421\n"], "export.csv", {
      type: "text/csv",
    });
    filesRef.current = [{ file: demo, path: demo.name }];
    setHasSelection(true);
    setDialogOpen(true);
    void createAgentSession([demo])
      .then((session) => {
        setAgent({
          session,
          status: "created",
          events: [],
          thought: "",
          proposals: [],
          selectedKinds: [],
          error: null,
          summary: null,
          toolCalls: 0,
          commit: null,
        });
        if (param === "agent") {
          window.setTimeout(() => void runAgent(), 400);
        }
      })
      .catch((caught) => setError(localError(caught)));
  }, [runAgent]);

  /* 全局拖拽：任意页面拖入文件/文件夹即进入预览。 */
  useEffect(() => {
    let depth = 0;

    const hasFiles = (event: DragEvent) =>
      Array.from(event.dataTransfer?.types ?? []).includes("Files");

    const onDragEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth += 1;
      if (!busyRef.current) setDragActive(true);
    };
    const onDragOver = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      if (!busyRef.current) setDragActive(true);
    };
    const onDragLeave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0 || event.relatedTarget === null) {
        depth = 0;
        setDragActive(false);
      }
    };
    const onDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDragActive(false);
      const transfer = event.dataTransfer;
      if (!transfer) return;
      void collectDroppedFiles(transfer)
        .then((files) => startFiles(files))
        .catch((caught) => {
          setDialogOpen(true);
          setError(localError(caught));
        });
    };

    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [startFiles]);

  const handleInputFiles = (list: FileList | null) => {
    const files = Array.from(list ?? []).map((file) => ({
      file,
      path:
        (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
        file.name,
    }));
    if (files.length) void startFiles(files);
  };

  return (
    <ImportContext.Provider value={{ openPicker }}>
      {children}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".zip,.csv,.txt,.xml,.json,.html,.htm,.pdf,.xlsx,.xls,.fit,.gpx,.tcx,.edf,.bdf,.dat,.hea,.atr"
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => {
          // Read the FileList before clearing the input: Chrome clears the same
          // FileList object when value is reset, which would drop the selection.
          const list = event.target.files;
          handleInputFiles(list);
          event.target.value = "";
        }}
      />
      <input
        ref={(element) => {
          dirInputRef.current = element;
          if (element) {
            element.setAttribute("webkitdirectory", "");
            element.setAttribute("directory", "");
          }
        }}
        type="file"
        multiple
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => {
          // Read the FileList before clearing the input: Chrome clears the same
          // FileList object when value is reset, which would drop the selection.
          const list = event.target.files;
          handleInputFiles(list);
          event.target.value = "";
        }}
      />
      <DropOverlay visible={dragActive} />
      <ImportDialog
        open={dialogOpen}
        onOpenChange={(next) => {
          if (next) setDialogOpen(true);
          else closeDialog();
        }}
        preview={preview}
        error={error}
        busy={busy}
        committing={committing}
        commitError={commitError}
        source={source}
        recordCounts={recordCounts}
        totalRecords={totalRecords}
        result={commitResult}
        hasSelection={hasSelection}
        selectedFiles={filesRef.current?.map((item) => item.file.name) ?? []}
        agent={agent}
        agentBusy={agentBusy}
        agentCommitting={agentCommitting}
        onPickSource={(next) => {
          sourceRef.current = next;
          setSource(next);
        }}
        onChooseFiles={chooseFiles}
        onChooseFolder={chooseFolder}
        onOpenDialog={openDialog}
        onStartAgent={() => void startAgentSession()}
        onRunAgent={() => void runAgent()}
        onStopAgent={stopAgent}
        onToggleAgentKind={toggleAgentKind}
        onSetAgentKinds={setAgentKinds}
        onCommitAgent={(memberId) => void commitAgent(memberId)}
        onDone={finishBundle}
        onCommit={(body) => void commit(body)}
        onPickAnother={pickAnother}
      />
    </ImportContext.Provider>
  );
}

export function useImport(): ImportContextValue {
  const value = useContext(ImportContext);
  if (!value) {
    throw new Error("useImport must be used inside <ImportProvider>");
  }
  return value;
}
