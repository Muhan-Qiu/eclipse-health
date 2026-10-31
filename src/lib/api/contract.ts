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
  SampleImportBody,
  SampleImportResponse,
  SampleRecordId,
  SignalData,
  SignalMetadata,
} from "./types";

export interface RecordListParams {
  limit?: number;
  offset?: number;
  capturedFrom?: string;
  capturedTo?: string;
  recordType?: string;
  /** 按 recordType 前缀筛选（如 `org.eclipsehealth.health.`）；与 recordType 互斥。 */
  recordTypePrefix?: string;
  moduleId?: string;
  favorite?: boolean;
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
    /** D1：只改 favorite，返回完整记录。 */
    updateFavorite(id: string, favorite: boolean): Promise<HealthRecord>;
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
    /** A1：白名单内置示例（真实 WFDB 导入）。 */
    sample(
      sampleId: SampleRecordId,
      body?: SampleImportBody,
    ): Promise<SampleImportResponse>;
  };
}
