export type DeviceVendor = "apple" | "samsung" | "huawei" | "generic";

export interface DeviceInfo {
  vendor: DeviceVendor;
  model: string;
}

export type RecordStatus = "ready" | "processing" | "failed";

export interface RecordSummary {
  id: string;
  recordedAt: string;
  durationSec: number;
  device: DeviceInfo;
  tags: string[];
  leads: string[];
  sampleRateHz: number;
  status: RecordStatus;
  /** true 表示合成示例数据，UI 必须显式标注 */
  isDemo: boolean;
}

/**
 * 分析摘要只包含可直接展示的汇总指标。
 * 示例数据不得包含真实患者信息或诊断结论。
 */
export interface AnalysisSummary {
  recordId: string;
  modelId: string;
  modelVersion: string;
  computedAt: string;
  heartRateBpm: number;
  hrvRmssdMs: number;
  abnormalBeatRatio: number;
  qualityScore: number;
  isDemo: boolean;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  version: string;
  mock: boolean;
}
