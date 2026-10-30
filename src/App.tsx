import { HashRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/app-shell";
import { DashboardPage } from "@/pages/dashboard";
import { RecordsPage } from "@/pages/records";
import { ProfilePage } from "@/pages/profile";
import { RecordDetailPage } from "@/pages/record-detail";
import { TrendsPage } from "@/pages/trends";
import { ComparePage } from "@/pages/compare";
import { AssistantPage } from "@/pages/assistant";
import { ReportsPage } from "@/pages/reports";
import { SettingsPage } from "@/pages/settings";
import { ModulesPage } from "@/pages/modules";
import { AboutPage } from "@/pages/about";
import { NotFoundPage } from "@/pages/not-found";
import { AnalysisNotificationsWatcher } from "@/features/profile/notifications";

/**
 * 桌面端使用 HashRouter：Tauri 的 asset 协议不会为深层路径回退到 index.html，
 * hash 路由可以避免打包后刷新 404。
 */
export default function App() {
  return (
    <HashRouter>
      <AnalysisNotificationsWatcher />
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="records" element={<RecordsPage />} />
          <Route path="records/:id" element={<RecordDetailPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="trends" element={<TrendsPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="modules" element={<ModulesPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
