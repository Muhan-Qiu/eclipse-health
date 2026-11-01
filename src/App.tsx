import { lazy, Suspense, type ReactNode } from "react";
import { HashRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/app-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { DashboardPage } from "@/pages/dashboard";
import { AnalysisNotificationsWatcher } from "@/features/profile/notifications";
import { LlmKeyPrompt } from "@/features/onboarding/llm-key-prompt";

/**
 * 首屏只保留 Dashboard 与外壳，其余页面各自分包：
 * 主 chunk 里不再打包报告/图表等重依赖，路由切换时再按需加载。
 */
const RecordsPage = lazy(() =>
  import("@/pages/records").then((m) => ({ default: m.RecordsPage })),
);
const RecordDetailPage = lazy(() =>
  import("@/pages/record-detail").then((m) => ({ default: m.RecordDetailPage })),
);
const HealthDataPage = lazy(() =>
  import("@/pages/health-data").then((m) => ({ default: m.HealthDataPage })),
);
const ProfilePage = lazy(() =>
  import("@/pages/profile").then((m) => ({ default: m.ProfilePage })),
);
const TrendsPage = lazy(() =>
  import("@/pages/trends").then((m) => ({ default: m.TrendsPage })),
);
const ComparePage = lazy(() =>
  import("@/pages/compare").then((m) => ({ default: m.ComparePage })),
);
const AssistantPage = lazy(() =>
  import("@/pages/assistant").then((m) => ({ default: m.AssistantPage })),
);
const ReportsPage = lazy(() =>
  import("@/pages/reports").then((m) => ({ default: m.ReportsPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings").then((m) => ({ default: m.SettingsPage })),
);
const ModulesPage = lazy(() =>
  import("@/pages/modules").then((m) => ({ default: m.ModulesPage })),
);
const ModulePage = lazy(() =>
  import("@/pages/module-page").then((m) => ({ default: m.ModulePage })),
);
const AboutPage = lazy(() =>
  import("@/pages/about").then((m) => ({ default: m.AboutPage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/not-found").then((m) => ({ default: m.NotFoundPage })),
);

function PageFallback() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <Skeleton className="h-40 w-full rounded-xl" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </div>
    </div>
  );
}

/** Suspense 包在路由元素上，AppShell 不会在切页时被卸载。 */
function lazyPage(node: ReactNode) {
  return <Suspense fallback={<PageFallback />}>{node}</Suspense>;
}

/**
 * 桌面端使用 HashRouter：Tauri 的 asset 协议不会为深层路径回退到 index.html，
 * hash 路由可以避免打包后刷新 404。
 */
export default function App() {
  return (
    <HashRouter>
      <AnalysisNotificationsWatcher />
      <LlmKeyPrompt />
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="records" element={lazyPage(<RecordsPage />)} />
          <Route path="records/:id" element={lazyPage(<RecordDetailPage />)} />
          <Route path="health-data" element={lazyPage(<HealthDataPage />)} />
          <Route path="profile" element={lazyPage(<ProfilePage />)} />
          <Route path="trends" element={lazyPage(<TrendsPage />)} />
          <Route path="compare" element={lazyPage(<ComparePage />)} />
          <Route path="reports" element={lazyPage(<ReportsPage />)} />
          <Route path="assistant" element={lazyPage(<AssistantPage />)} />
          <Route path="settings" element={lazyPage(<SettingsPage />)} />
          <Route path="modules" element={lazyPage(<ModulesPage />)} />
          <Route
            path="modules/:moduleId/pages/:pageId"
            element={lazyPage(<ModulePage />)}
          />
          <Route path="about" element={lazyPage(<AboutPage />)} />
          <Route path="*" element={lazyPage(<NotFoundPage />)} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
