import type {
  AnalysisListResponse,
  AnalysisResult,
  AnalysisStartBody,
  AnalysisStartResponse,
  EngineStatus,
  HealthRecord,
  HealthStatus,
  ImportCommitBody,
  ImportCommitResponse,
  ImportHintFormat,
  ImportPreview,
  Member,
  RecordPage,
  SignalData,
  SignalMetadata,
} from "./types";

export interface RecordListParams {
  limit?: number;
  offset?: number;
  capturedFrom?: string;
  capturedTo?: string;
  recordType?: string;
  moduleId?: string;
}

export interface PreviewSource {
  file?: File;
  /** 仅本地调试：后端只允许数据目录内的路径。 */
  path?: string;
}

export interface ApiClient {
  health(): Promise<HealthStatus>;
  members: {
    list(): Promise<Member[]>;
  };
  records: {
    list(params?: RecordListParams): Promise<RecordPage>;
    get(id: string): Promise<HealthRecord>;
    delete(id: string): Promise<void>;
    signals(id: string): Promise<SignalMetadata[]>;
    signal(id: string, lead?: string): Promise<SignalData>;
    analyses(id: string): Promise<AnalysisListResponse>;
    startAnalysis(
      id: string,
      body?: AnalysisStartBody,
    ): Promise<AnalysisStartResponse>;
  };
  analyses: {
    get(id: string, includeBeats?: boolean): Promise<AnalysisResult>;
  };
  engine: {
    status(): Promise<EngineStatus>;
  };
  imports: {
    preview(
      source: PreviewSource,
      hintFormat?: ImportHintFormat,
    ): Promise<ImportPreview>;
    commit(importId: string, body: ImportCommitBody): Promise<ImportCommitResponse>;
    discard(importId: string): Promise<void>;
  };
}
