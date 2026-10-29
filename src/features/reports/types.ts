export type ReportFormat = "pdf" | "png";
export type ReportTemplate = "simple" | "detailed" | "doctor";

export interface ReportSummary {
  reportId: string;
  recordId: string;
  analysisId: string | null;
  format: ReportFormat | string;
  template: ReportTemplate | string;
  fileName: string;
  size: number;
  sha256: string;
  redacted: boolean;
  createdAt: string | null;
  /** 后端返回相对 API 根路径的下载地址（如 /api/v1/reports/rep_.../download）。 */
  downloadUrl: string;
}

export interface ReportListResponse {
  items: ReportSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface GenerateReportBody {
  format: ReportFormat;
  template: ReportTemplate;
  redact: boolean;
}
