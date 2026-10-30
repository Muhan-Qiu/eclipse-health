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
