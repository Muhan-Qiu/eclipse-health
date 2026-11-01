import type { TFunction } from "i18next";
import type { PermissionDetail, PermissionRisk } from "./types";

export function scopeKey(scope: string): string {
  return scope.replace(/[^a-zA-Z0-9]+/g, "_");
}

export function actionKey(action: string): string {
  return action.replace(/[^a-zA-Z0-9]+/g, "_");
}

export function permissionLabel(
  t: TFunction,
  detail: PermissionDetail | string,
): string {
  const scope = typeof detail === "string" ? detail : detail.scope;
  const fallback = typeof detail === "string" ? detail : detail.label;
  return t(`moduleUi.permissions.scopes.${scopeKey(scope)}.label`, {
    defaultValue: fallback,
  });
}

export function permissionDescription(
  t: TFunction,
  detail: PermissionDetail | string,
): string {
  const scope = typeof detail === "string" ? detail : detail.scope;
  const fallback = typeof detail === "string" ? "" : detail.description;
  return t(`moduleUi.permissions.scopes.${scopeKey(scope)}.description`, {
    defaultValue: fallback,
  });
}

export function riskLabel(t: TFunction, risk: PermissionRisk): string {
  return t(`moduleUi.permissions.risk.${risk}`);
}

export function riskVariant(
  risk: PermissionRisk,
): "destructive" | "secondary" | "outline" {
  if (risk === "high") return "destructive";
  if (risk === "medium") return "secondary";
  return "outline";
}

export function riskOf(scope: string, details: PermissionDetail[]): PermissionRisk {
  return details.find((item) => item.scope === scope)?.risk ?? "medium";
}
