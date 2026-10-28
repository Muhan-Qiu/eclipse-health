import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "./command-palette";
import { findNavItem } from "@/lib/nav";

const NAV_STORAGE_KEY = "eh-nav-collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function AppShell() {
  const { t } = useTranslation();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(NAV_STORAGE_KEY, String(collapsed));
    } catch {
      // 忽略存储失败
    }
  }, [collapsed]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
    const navItem = findNavItem(location.pathname);
    const pageName = navItem ? t(navItem.labelKey) : t("notFound.title");
    document.title = `${pageName} · ${t("app.name")}`;
  }, [location.pathname, t]);

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <a
        href="#main"
        onClick={(event) => {
          // HashRouter 下 href="#main" 会被当作路由跳转，这里改为聚焦主内容。
          event.preventDefault();
          mainRef.current?.focus();
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:shadow-card"
      >
        {t("app.skipToContent")}
      </a>

      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenCommand={() => setCommandOpen(true)} />
        <main
          id="main"
          ref={mainRef}
          tabIndex={-1}
          className="flex-1 overflow-y-auto outline-none"
        >
          <div key={location.pathname} className="eh-page eh-page-enter">
            <Outlet />
          </div>
        </main>
      </div>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
