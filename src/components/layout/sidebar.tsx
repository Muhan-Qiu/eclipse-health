import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EclipseMark } from "@/components/common/eclipse-mark";
import { primaryNav, secondaryNav, type NavItem } from "@/lib/nav";
import { ModuleNav } from "./module-nav";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const moduleNavItems = secondaryNav.filter((item) => item.path === "/modules");
const utilityNavItems = secondaryNav.filter((item) => item.path !== "/modules");

function NavEntry({
  item,
  collapsed,
}: {
  item: NavItem;
  collapsed: boolean;
}) {
  const { t } = useTranslation();
  const Icon = item.icon;
  const label = t(item.labelKey);

  const link = (
    <NavLink
      to={item.path}
      end={item.end ?? item.path === "/modules"}
      className={cn(
        "relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm text-muted-foreground transition-[background-color,color,box-shadow] duration-200",
        "hover:bg-accent hover:text-foreground",
        "aria-[current=page]:bg-surface aria-[current=page]:font-medium aria-[current=page]:text-foreground aria-[current=page]:shadow-[inset_0_0_0_1px_var(--eh-border)] aria-[current=page]:[&_svg]:text-primary",
        collapsed && "justify-center px-0",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {collapsed ? <span className="sr-only">{label}</span> : (
        <span className="truncate">{label}</span>
      )}
    </NavLink>
  );

  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

function NavGroupLabel({ children }: { children: string }) {
  return <p className="eh-sidebar-label">{children}</p>;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside
      aria-label={t("nav.primary")}
      data-collapsed={collapsed ? "true" : "false"}
      className={cn(
        "eh-sidebar flex h-full shrink-0 flex-col border-r border-border bg-sidebar transition-[width,background-color,border-color] duration-200",
        collapsed ? "w-16" : "w-[232px]",
      )}
    >
      <div
        className={cn(
          "flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-3",
          collapsed && "justify-center px-0",
        )}
      >
        <EclipseMark className="size-7" loop />
        {collapsed ? null : (
          <p className="min-w-0 truncate font-heading text-[15px] leading-tight font-semibold">
            {t("app.name")}
          </p>
        )}
      </div>

      <nav className="flex min-h-0 flex-1 flex-col p-2">
        <div className="shrink-0">
          {collapsed ? null : (
            <NavGroupLabel>{t("nav.primary")}</NavGroupLabel>
          )}
          <ul className="flex flex-col gap-1">
            {primaryNav.map((item) => (
              <li key={item.path}>
                <NavEntry item={item} collapsed={collapsed} />
              </li>
            ))}
          </ul>
        </div>

        <Separator className="my-2 shrink-0" />

        <div className="flex min-h-0 flex-1 flex-col">
          <ul className="flex shrink-0 flex-col gap-1">
            {moduleNavItems.map((item) => (
              <li key={item.path}>
                <NavEntry item={item} collapsed={collapsed} />
              </li>
            ))}
          </ul>
          <div
            className={cn(
              "eh-sidebar-module-list mt-1 min-h-0 flex-1 overflow-y-auto overscroll-contain",
              collapsed ? "pr-0" : "pr-0.5",
            )}
          >
            <ModuleNav collapsed={collapsed} />
          </div>
        </div>
      </nav>

      <div className="shrink-0 border-t border-border p-2">
        <ul className="flex flex-col gap-1">
          {utilityNavItems.map((item) => (
            <li key={item.path}>
              <NavEntry item={item} collapsed={collapsed} />
            </li>
          ))}
        </ul>
        <div className="mt-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size={collapsed ? "icon-sm" : "sm"}
                onClick={onToggle}
                aria-label={
                  collapsed ? t("a11y.expandNav") : t("a11y.collapseNav")
                }
                aria-expanded={!collapsed}
                className={cn(
                  "w-full justify-start gap-2 text-muted-foreground",
                  collapsed && "justify-center",
                )}
              >
                {collapsed ? (
                  <PanelLeftOpen aria-hidden="true" />
                ) : (
                  <>
                    <PanelLeftClose aria-hidden="true" />
                    <span>{t("nav.collapse")}</span>
                  </>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              {collapsed ? t("a11y.expandNav") : t("a11y.collapseNav")}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </aside>
  );
}
