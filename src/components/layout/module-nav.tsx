import "./sidebar-i18n";
import "@/features/modules/i18n";

import { useQuery } from "@tanstack/react-query";
import { Link, NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";
import { cn } from "cn";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { MODULE_QUERY_KEY, listModules } from "@/features/modules/api";
import { moduleDisplayName } from "@/features/modules/copy";
import { moduleStateLabel } from "@/features/modules/format";
import { moduleTypeIcon } from "@/features/modules/module-icon";
import type { ModuleState, ModuleSummary } from "@/features/modules/types";

// 用户要求侧栏直接列出每个已安装模块；保留一个很高的上限只是防止异常数据撑爆 DOM。
const MAX_VISIBLE_MODULES = 64;

function stateDotClass(state: ModuleState): string {
  switch (state) {
    case "running":
      return "bg-emerald-500";
    case "enabled":
      return "bg-primary";
    case "crashed":
      return "bg-destructive";
    case "disabled":
      return "bg-muted-foreground/40";
    default:
      return "bg-muted-foreground/60";
  }
}

function ModuleNavEntry({
  module,
  collapsed,
}: {
  module: ModuleSummary;
  collapsed: boolean;
}) {
  const { t, i18n } = useTranslation();
  const Icon = moduleTypeIcon(module.type);
  const name = moduleDisplayName(i18n.language, module.id, module.name);
  const stateLabel = moduleStateLabel(t, module.state);

  const link = (
    <NavLink
      to={`/modules/${encodeURIComponent(module.id)}`}
      className={cn(
        "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm text-muted-foreground transition-[background-color,color] duration-200",
        "hover:bg-accent hover:text-foreground",
        "aria-[current=page]:bg-subtle aria-[current=page]:font-medium aria-[current=page]:text-foreground aria-[current=page]:[&_svg]:text-primary",
        collapsed && "justify-center px-0",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {collapsed ? (
        <span className="sr-only">
          {name} · {stateLabel}
        </span>
      ) : (
        <>
          <span className="min-w-0 flex-1 truncate">{name}</span>
          <span
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              stateDotClass(module.state),
            )}
            title={stateLabel}
            aria-hidden="true"
          />
        </>
      )}
    </NavLink>
  );

  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">
        {name} · {stateLabel}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * 侧栏中的已安装模块列表。
 *
 * 模块列表来自本地后端；后端不可用或列表为空时直接不渲染，避免把侧栏撑高
 * 或反复重试。最多展示 12 个，其余引导到模块中心。
 */
export function ModuleNav({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  const modulesQuery = useQuery({
    queryKey: MODULE_QUERY_KEY,
    queryFn: listModules,
    staleTime: 30_000,
    retry: false,
  });

  const modules = modulesQuery.data ?? [];
  if (modulesQuery.isPending || modules.length === 0) return null;

  const visible = modules.slice(0, MAX_VISIBLE_MODULES);
  const hasMore = modules.length > visible.length;

  return (
    <div className="mt-1">
      <Separator className="my-2" />
      {collapsed ? null : (
        <p className="px-2.5 pb-1 text-[11px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
          {t("nav.moduleCenter")}
        </p>
      )}
      <ul className="flex flex-col gap-0.5">
        {visible.map((module) => (
          <li key={module.id}>
            <ModuleNavEntry module={module} collapsed={collapsed} />
          </li>
        ))}
      </ul>
      {hasMore ? (
        collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link
                to="/modules"
                aria-label={t("nav.viewAllModules")}
                className="mt-0.5 flex h-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <ChevronRight className="size-4" aria-hidden="true" />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">{t("nav.viewAllModules")}</TooltipContent>
          </Tooltip>
        ) : (
          <Link
            to="/modules"
            className="mt-0.5 flex h-8 items-center gap-1 rounded-lg px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {t("nav.viewAllModules")}
            <ChevronRight className="size-3" aria-hidden="true" />
          </Link>
        )
      ) : null}
    </div>
  );
}
