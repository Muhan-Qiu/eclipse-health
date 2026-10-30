/**
 * 桌面偏好桥接（B4-01 契约）。
 *
 * Tauri 命令不存在或在浏览器预览中运行时，退化为 localStorage，
 * 由 UI 提示「重启后生效」；不把设置失败当成阻断错误。
 */

export type DesktopPreference = "closeToTray" | "splashEnabled";

const STORAGE_KEYS: Record<DesktopPreference, string> = {
  closeToTray: "eh-close-to-tray",
  splashEnabled: "eh-splash-enabled",
};

const COMMANDS: Record<DesktopPreference, string> = {
  closeToTray: "set_close_to_tray",
  splashEnabled: "set_splash_enabled",
};

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function readLocalPreference(
  preference: DesktopPreference,
  fallback: boolean,
): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEYS[preference]);
    if (stored === "true") return true;
    if (stored === "false") return false;
  } catch {
    // 隐私模式或存储被禁用时使用默认值。
  }
  return fallback;
}

function writeLocalPreference(
  preference: DesktopPreference,
  enabled: boolean,
): void {
  try {
    localStorage.setItem(STORAGE_KEYS[preference], String(enabled));
  } catch {
    // 忽略存储失败；当前会话仍然生效。
  }
}

export type DesktopApplyResult = "applied" | "fallback";

export async function applyDesktopPreference(
  preference: DesktopPreference,
  enabled: boolean,
): Promise<DesktopApplyResult> {
  writeLocalPreference(preference, enabled);
  if (!isTauriRuntime()) return "fallback";
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke(COMMANDS[preference], { enabled });
    return "applied";
  } catch {
    return "fallback";
  }
}
