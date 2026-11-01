/** 应用内模块市场（H8 后端契约）的前端视图类型。 */

export type MarketplaceSource = "official" | "community";

export type MarketplaceTab = MarketplaceSource | "local";

/**
 * 索引条目。除 id/name/version 外都按可选处理：
 * `updates` 接口返回的条目可能只带部分字段，UI 需要能优雅降级。
 */
/** 静态扫描结果；索引未提供时整个字段缺省。 */
export interface MarketplaceScan {
  status?: string;
  risk?: string;
  scannedAt?: string;
  reportUrl?: string;
}

export interface MarketplaceModule {
  id: string;
  name: string;
  version: string;
  type?: string;
  description?: string;
  author?: string;
  license?: string;
  repository?: string | null;
  permissions?: string[];
  dependencies?: string[];
  minCoreVersion?: string;
  categories?: string[];
  verified?: boolean;
  file?: string;
  size?: number;
  sha256?: string;
  scan?: MarketplaceScan;
}

export interface MarketplaceIndex {
  source: MarketplaceSource;
  keyId?: string | null;
  modules: MarketplaceModule[];
  generatedAt?: string;
}

export interface MarketplaceSourceInfo {
  configured: boolean;
  url?: string | null;
}

export interface MarketplaceSources {
  official: MarketplaceSourceInfo;
  community: MarketplaceSourceInfo;
  keyId?: string | null;
  keyIds?: string[];
}

export interface MarketplaceUpdate extends Partial<MarketplaceModule> {
  id: string;
  name: string;
  installedVersion: string;
  availableVersion: string;
  source?: MarketplaceSource;
}

export interface MarketplaceInstallBody {
  source: MarketplaceSource;
  moduleId: string;
  version: string;
}
