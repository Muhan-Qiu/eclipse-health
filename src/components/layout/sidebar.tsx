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
import { markNavOrigin } from "@/lib/motion";
import { primaryNav, secondaryNav, type NavItem } from "@/lib/nav";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

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
      end={item.end}
      onClick={(event) => {
        // 只记录普通左键点击；修饰键/中键保持浏览器默认行为。
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
          return;
        }
        markNavOrigin(event.currentTarget);
      }}
      className={cn(
        "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm text-muted-foreground transition-[background-color,color] duration-200",
        "hover:bg-accent hover:text-foreground",
        "aria-[current=page]:bg-subtle aria-[current=page]:font-medium aria-[current=page]:text-foreground aria-[current=page]:[&_svg]:text-primary",
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

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside
      aria-label={t("nav.primary")}
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border bg-sidebar transition-[width,background-color,border-color] duration-200",
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
          <div className="min-w-0">
            <p className="truncate font-heading text-[15px] leading-tight font-semibold">
              {t("app.name")}
            </p>
            <p className="truncate text-[11px] leading-tight text-muted-foreground">
              {t("app.tagline")}
            </p>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-0.5">
          {primaryNav.map((item) => (
            <li key={item.path}>
              <NavEntry item={item} collapsed={collapsed} />
            </li>
          ))}
        </ul>
        <Separator className="my-2" />
        <ul className="flex flex-col gap-0.5">
          {secondaryNav.map((item) => (
            <li key={item.path}>
              <NavEntry item={item} collapsed={collapsed} />
            </li>
          ))}
        </ul>
      </nav>

      <div className={cn("border-t border-border p-2", collapsed && "px-2")}>
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
    </aside>
  );
}
