import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Moon, Search, Settings, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { findNavItem } from "@/lib/nav";
import { useAppTheme } from "@/lib/theme";

interface TopbarProps {
  onOpenCommand: () => void;
}

export function Topbar({ onOpenCommand }: TopbarProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const navItem = findNavItem(location.pathname);
  const { resolved, toggleMode } = useAppTheme();

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4 transition-colors duration-200">
      <nav
        aria-label={t("nav.primary")}
        className="flex min-w-0 items-center gap-2 text-sm"
      >
        <span className="hidden text-muted-foreground md:inline">
          {t("app.name")}
        </span>
        <ChevronRight
          className="hidden size-3.5 text-muted-foreground md:inline"
          aria-hidden="true"
        />
        <span className="truncate font-medium">
          {navItem ? t(navItem.labelKey) : t("notFound.title")}
        </span>
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={onOpenCommand}
          aria-label={t("a11y.openCommand")}
          className="flex h-8 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 text-sm text-muted-foreground transition-[background-color,color,transform] duration-[120ms] hover:bg-accent hover:text-foreground active:translate-y-px"
        >
          <Search className="size-4" aria-hidden="true" />
          <span className="hidden md:inline">{t("topbar.search")}</span>
          <kbd className="eh-num hidden rounded border border-border px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground lg:inline">
            {t("a11y.searchShortcut")}
          </kbd>
        </button>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleMode}
              aria-label={t("topbar.themeToggle")}
            >
              {resolved === "dark" ? (
                <Sun aria-hidden="true" />
              ) : (
                <Moon aria-hidden="true" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("topbar.themeToggle")}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" asChild>
              <Link to="/settings" aria-label={t("topbar.settings")}>
                <Settings aria-hidden="true" />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("topbar.settings")}</TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}
