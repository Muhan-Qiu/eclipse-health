/** 外部访问权限：与后端 `/api/v1/external/keys` 的 scopes 契约一致。 */
export const EXTERNAL_SCOPES = ["read", "write", "assistant"] as const;

export type ExternalScope = (typeof EXTERNAL_SCOPES)[number];

export interface ExternalKey {
  id: string;
  name: string;
  prefix: string;
  scopes: ExternalScope[];
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
}

/**
 * 列表加载的结果。404 或后端不可达都归为 `unavailable`，
 * 由面板显示降级状态，而不是抛错导致整页白屏。
 */
export type ExternalKeysState =
  | { status: "ok"; items: ExternalKey[] }
  | { status: "unavailable" };

export interface CreateExternalKeyInput {
  name: string;
  scopes: ExternalScope[];
}

/** 创建响应中的 token 只在这一次返回，列表接口不会再有。 */
export interface CreatedExternalKey {
  id: string;
  name: string;
  token: string;
  prefix: string;
  scopes: ExternalScope[];
  createdAt: string;
}

export function isExternalScope(value: unknown): value is ExternalScope {
  return (
    value === "read" || value === "write" || value === "assistant"
  );
}
