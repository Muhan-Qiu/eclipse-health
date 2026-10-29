/**
 * 仅用于本地截图验证的独立入口（不出现在生产路由中）。
 *
 * B3-03 的文件所有权不含 `src/App.tsx`，路由切换由 B3-02 / 指挥官完成；
 * 这里用同一个 AppShell 与 Providers 渲染报告页，便于在真实后端数据上验收视觉。
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter, Route, Routes } from "react-router-dom";
import { AppProviders } from "@/app/providers";
import { AppShell } from "@/components/layout/app-shell";
import { ReportsWorkspace } from "./reports-workspace";
import "./i18n";
import "@/index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AppProviders>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="reports" element={<ReportsWorkspace />} />
          </Route>
        </Routes>
      </HashRouter>
    </AppProviders>
  </React.StrictMode>,
);
