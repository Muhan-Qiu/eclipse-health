import type {
  AnalysisSummary,
  HealthStatus,
  RecordSummary,
} from "./types";

/**
 * 合成演示数据：仅用于 B1 的界面骨架。
 * 不包含真实患者信息，也不构成任何诊断结论。
 */
export const mockRecords: RecordSummary[] = [
  {
    id: "rec_0193a4c2-7b1e-7c3a-9d20-1a2b3c4d5e60",
    recordedAt: "2026-10-26T08:12:00+08:00",
    durationSec: 60,
    device: { vendor: "apple", model: "Apple Watch Series 9" },
    tags: ["morning", "resting"],
    leads: ["I"],
    sampleRateHz: 512,
    status: "ready",
    isDemo: true,
  },
  {
    id: "rec_0193a0d1-2f7a-7b51-a6c8-9d0e1f2a3b4c",
    recordedAt: "2026-10-22T21:40:00+08:00",
    durationSec: 90,
    device: { vendor: "samsung", model: "Galaxy Watch7" },
    tags: ["postExercise", "evening"],
    leads: ["I"],
    sampleRateHz: 500,
    status: "ready",
    isDemo: true,
  },
  {
    id: "rec_01939c8e-6d2b-7330-bf4e-5a6b7c8d9e0f",
    recordedAt: "2026-10-15T07:05:00+08:00",
    durationSec: 60,
    device: { vendor: "huawei", model: "HUAWEI WATCH GT 5 Pro" },
    tags: ["morning"],
    leads: ["I"],
    sampleRateHz: 500,
    status: "ready",
    isDemo: true,
  },
];

export const mockAnalysis: AnalysisSummary = {
  recordId: mockRecords[0].id,
  modelId: "cardia-2.0",
  modelVersion: "2.0.0",
  computedAt: "2026-10-26T08:13:10+08:00",
  heartRateBpm: 62,
  hrvRmssdMs: 42,
  abnormalBeatRatio: 0.004,
  qualityScore: 0.92,
  isDemo: true,
};

export const mockHealth: HealthStatus = {
  status: "ok",
  version: "0.1.0",
  mock: true,
};

/** 模拟网络延迟，让加载骨架在开发时可见。 */
export function mockDelay<T>(value: T, ms = 240): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value), ms);
  });
}
