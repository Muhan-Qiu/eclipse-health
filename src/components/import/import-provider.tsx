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
import { ImportDialog } from "./import-dialog";

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
  const inputRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const previewRef = useRef<ImportPreview | null>(null);
  const sourceRef = useRef<ImportSourceKind>("auto");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [commitError, setCommitError] = useState<ApiError | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [source, setSource] = useState<ImportSourceKind>("auto");
  const [recordCounts, setRecordCounts] = useState<ImportRecordCounts>(EMPTY_COUNTS);
  const [totalRecords, setTotalRecords] = useState(0);
  const [commitResult, setCommitResult] = useState<HealthImportCommitResult | null>(null);

  useEffect(() => {
    previewRef.current = preview;
  }, [preview]);

  const discardCurrent = useCallback(async () => {
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

  const startFiles = useCallback(async (dropped: DroppedFile[]) => {
    if (busyRef.current) return;
    busyRef.current = true;
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
  }, []);

  const openPicker = useCallback(() => {
    setCommitResult(null);
    setError(null);
    setPreview(null);
    setDialogOpen(true);
  }, []);

  const pickSource = useCallback((next: ImportSourceKind) => {
    sourceRef.current = next;
    setSource(next);
    setCommitResult(null);
    setError(null);
    setPreview(null);
    setRecordCounts({ ...EMPTY_COUNTS });
    setTotalRecords(0);
    window.setTimeout(() => inputRef.current?.click(), 0);
  }, []);

  const pickAnother = useCallback(() => {
    void discardCurrent();
    setError(null);
    setDialogOpen(true);
    window.setTimeout(() => inputRef.current?.click(), 0);
  }, [discardCurrent]);

  const closeDialog = useCallback(() => {
    setDialogOpen(false);
    setError(null);
    setCommitResult(null);
    void discardCurrent();
  }, [discardCurrent]);

  const finishBundle = useCallback(() => {
    setDialogOpen(false);
    setCommitResult(null);
    navigate("/records");
  }, [navigate]);

  const commit = useCallback(
    async (body: ImportCommitBody) => {
      const current = previewRef.current;
      if (!current || committing) return;
      setCommitting(true);
      setCommitError(null);
      try {
        const result = await commitHealthImport(current.importId, body);
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
    [committing, navigate, t, totalRecords],
  );

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

  return (
    <ImportContext.Provider value={{ openPicker }}>
      {children}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".hea,.dat,.atr,.zip,.csv,.txt,.xml"
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []).map((file) => ({
            file,
            path: file.name,
          }));
          event.target.value = "";
          if (files.length) void startFiles(files);
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
        onPickSource={pickSource}
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
