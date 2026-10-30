import { useEffect, useRef } from "react";
import i18n, { intlLocale } from "@/lib/i18n";
import { useMock } from "@/lib/api/client";
import { listRecentRecords } from "./api";

export const ANALYSIS_NOTIFICATIONS_KEY = "eh-notify-analysis-complete";
const POLL_INTERVAL_MS = 15_000;

/** 默认开启；设置开关（B4-04 后续提供）写入 localStorage 后即时生效。 */
export function analysisNotificationsEnabled(): boolean {
  try {
    return localStorage.getItem(ANALYSIS_NOTIFICATIONS_KEY) !== "false";
  } catch {
    return true;
  }
}

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function sendTitleBody(title: string, body: string): Promise<void> {
  if (isTauri()) {
    try {
      const plugin = await import("@tauri-apps/plugin-notification");
      let granted = await plugin.isPermissionGranted();
      if (!granted) granted = (await plugin.requestPermission()) === "granted";
      if (granted) {
        plugin.sendNotification({ title, body });
        return;
      }
    } catch {
      // 插件未初始化/权限被拒：继续走浏览器降级
    }
  }

  if (typeof Notification !== "undefined") {
    try {
      if (Notification.permission === "default") {
        await Notification.requestPermission();
      }
      if (Notification.permission === "granted") {
        new Notification(title, { body });
        return;
      }
    } catch {
      // 浏览器通知不可用：静默，不打断用户
    }
  }
}

/**
 * 轮询最近记录，检测 running/queued → completed 的转换。
 *
 * 只在窗口可见时轮询；通知文案含记录日期与「非诊断」，默认不包含心率等数值。
 */
export function AnalysisNotificationsWatcher() {
  const seen = useRef<Map<string, string>>(new Map());
  const seeded = useRef(false);

  useEffect(() => {
    if (useMock) return;
    let disposed = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    const poll = async () => {
      if (disposed) return;
      if (!analysisNotificationsEnabled()) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") {
        return;
      }
      try {
        const page = await listRecentRecords(20);
        for (const record of page.items) {
          const status = record.latestAnalysisStatus ?? "none";
          const signature = `${status}:${record.latestAnalyzedAt ?? ""}`;
          const previous = seen.current.get(record.id);
          seen.current.set(record.id, signature);
          if (!seeded.current || previous === undefined) continue;
          const wasRunning =
            previous.startsWith("running") || previous.startsWith("queued");
          if (wasRunning && status === "completed") {
            const date = new Intl.DateTimeFormat(intlLocale(i18n.language), {
              dateStyle: "medium",
              timeStyle: "short",
            }).format(new Date(record.capturedAt));
            void sendTitleBody(
              i18n.t("profile.notifications.title"),
              i18n.t("profile.notifications.body", { date }),
            );
          }
        }
        seeded.current = true;
      } catch {
        // 后端未启动时静默等待下一次轮询
      }
    };

    void poll();
    timer = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      disposed = true;
      if (timer !== undefined) clearInterval(timer);
    };
  }, []);

  return null;
}
