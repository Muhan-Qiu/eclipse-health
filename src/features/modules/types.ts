export type ModuleState =
  | "installed"
  | "enabled"
  | "running"
  | "stopped"
  | "disabled"
  | "crashed";

export type PermissionRisk = "low" | "medium" | "high";

export interface PermissionDetail {
  scope: string;
  risk: PermissionRisk;
  label: string;
  description: string;
  requested?: boolean;
  granted?: boolean;
}

export interface ModuleSummary {
  id: string;
  name: string;
  description: string;
  version: string;
  type: string;
  enabled: boolean;
  running: boolean;
  state: ModuleState;
  requestedPermissions: string[];
  grantedPermissions: string[];
  previousVersion: string | null;
  installedAt: string | null;
  updatedAt: string | null;
}

export interface ModuleAuthor {
  name: string;
  url?: string;
  email?: string;
}

export interface ModuleResources {
  memoryMb?: number;
  cpu?: number;
  startupTimeoutMs?: number;
}

export interface ModuleManifest {
  id: string;
  name: string;
  description: string;
  version: string;
  type: string;
  schemaVersion: string;
  apiVersion: string;
  engines: { eclipse: string };
  author: ModuleAuthor;
  license: string;
  homepage?: string | null;
  repository?: string | null;
  permissions: string[];
  permissionDetails: PermissionDetail[];
  contributes: Record<string, unknown>;
  resources: ModuleResources;
  updateChannel?: string | null;
  i18n: Record<string, string>;
}

export interface ModulePreview {
  id: string;
  name: string;
  description: string;
  version: string;
  type: string;
  author: ModuleAuthor;
  license: string;
  homepage?: string | null;
  repository?: string | null;
  apiVersion: string;
  schemaVersion: string;
  engines: { eclipse: string };
  permissions: string[];
  permissionDetails: PermissionDetail[];
  contributes: Record<string, unknown>;
  resources: ModuleResources;
  updateChannel?: string | null;
  warnings: string[];
  packageBytes: number;
  alreadyInstalled: boolean;
  installedVersion: string | null;
  newPermissions: string[];
}

export interface PermissionsState {
  moduleId: string;
  requested: string[];
  granted: string[];
  available: string[];
  scopes: PermissionDetail[];
}

export interface AuditEvent {
  id: string;
  moduleId: string | null;
  action: string;
  scope: string | null;
  detail: Record<string, unknown> | null;
  createdAt: string;
}

export interface AuditPage {
  events: AuditEvent[];
  count: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export interface AuditQuery {
  moduleId?: string;
  action?: string;
  limit?: number;
  offset?: number;
}

export interface InstallOptions {
  enable: boolean;
  /** null 表示沿用内核默认授权（UI 总是显式传勾选结果）。 */
  permissions: string[] | null;
}

/* ------------------------------------------------------------------ *
 * 平台 v2 贡献点（MODULE_CONTRACT_V2.md §2 / §7）
 *
 * 模块只交声明式 JSON；核心用受控组件渲染。这里的类型只是前端视角，
 * 后端不做 widget 结构校验，因此 `type` 用 string，未知视图由前端降级。
 * ------------------------------------------------------------------ */

export type ContributionKind = "widgets" | "pages" | "tools" | "recordTypes";

export interface ModuleContributionMeta {
  moduleId: string;
  moduleName: string;
  moduleVersion: string;
  moduleType: string;
}

export type WidgetSize = "sm" | "md" | "lg";

export type WidgetViewType = "stat" | "sparkline" | "list" | "progress" | "text";

export interface ModuleWidgetDataSource {
  /** 契约 v2 固定 module-rpc：核心只会调用声明它的模块自身。 */
  type: "module-rpc";
  method: string;
  params?: Record<string, unknown>;
}

export interface ModuleWidgetView {
  /** 契约内为 WidgetViewType；保留 string 以便未知类型降级而不是崩溃。 */
  type: string;
  /** 受限路径，如 `latest.weight`、`series[0].value`；不执行表达式。 */
  valuePath: string;
  unit?: string;
  label?: string;
  min?: number;
  max?: number;
}

export interface ModuleWidget extends ModuleContributionMeta {
  id: string;
  title: string;
  description?: string;
  size: WidgetSize;
  dataSource: ModuleWidgetDataSource;
  view: ModuleWidgetView;
  /** v2 schema 未定义；若第三方清单附带则作为站内跳转路径，否则卡片无交互。 */
  link?: string;
}

export interface ModuleContributionGroups {
  widgets: ModuleWidget[];
  pages: ModuleContributionMeta[];
  tools: ModuleContributionMeta[];
  recordTypes: ModuleContributionMeta[];
  counts: Record<ContributionKind, number>;
}

export interface ModuleContributionList {
  type: ContributionKind;
  items: ModuleContributionMeta[];
}

export interface ModuleWidgetList {
  type: "widgets";
  items: ModuleWidget[];
}
