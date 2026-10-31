import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { intlLocale } from "@/lib/i18n";
import { callModuleRpc } from "../api";
import { moduleErrorMessage } from "../errors";
import type { ModuleWidget } from "../types";
import { WidgetView } from "./widget-view";

/** 只接受站内路径；`//host` 与外部 URL 一律忽略，避免卡片变成跳转器。 */
function safeLink(link: string | undefined): string | null {
  if (typeof link !== "string") return null;
  const trimmed = link.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return null;
  return trimmed;
}

interface WidgetCardProps {
  widget: ModuleWidget;
  className?: string;
}

export function WidgetCard({ widget, className }: WidgetCardProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const navigate = useNavigate();

  const source = widget.dataSource;
  const method = typeof source?.method === "string" ? source.method : "";
  const params = source?.params ?? {};
  const link = safeLink(widget.link);

  const query = useQuery({
    queryKey: [
      "modules",
      "contributions",
      "rpc",
      widget.moduleId,
      widget.id,
      method,
      params,
    ],
    queryFn: () => callModuleRpc(widget.moduleId, method, params),
    enabled: source?.type === "module-rpc" && method.length > 0,
    // 卡片失败不该重试到阻塞仪表盘；状态一出来就降级，用户可手动重试。
    retry: 0,
    staleTime: 30_000,
  });

  const open = () => {
    if (link) navigate(link);
  };

  return (
    <Card
      className={cn(
        "h-full",
        link && "cursor-pointer transition-shadow hover:ring-primary/30",
        className,
      )}
      title={widget.description || undefined}
      role={link ? "link" : undefined}
      tabIndex={link ? 0 : undefined}
      onClick={link ? open : undefined}
      onKeyDown={
        link
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                open();
              }
            }
          : undefined
      }
    >
      <CardHeader>
        <CardTitle className="truncate">{widget.title}</CardTitle>
        <CardDescription className="truncate">{widget.moduleName}</CardDescription>
        <CardAction>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={t("moduleUi.widgets.refresh", { title: widget.title })}
            disabled={query.isFetching || method.length === 0}
            onClick={(event) => {
              event.stopPropagation();
              void query.refetch();
            }}
          >
            <RefreshCw
              aria-hidden="true"
              className={cn(query.isFetching && "animate-spin")}
            />
          </Button>
        </CardAction>
      </CardHeader>

      <CardContent>
        {/* 骨架 → 内容、以及刷新成功后的一次性 200ms 淡入；key 变化即重播。 */}
        <div
          key={
            query.isLoading
              ? "loading"
              : query.isError
                ? `error:${query.errorUpdatedAt}`
                : `data:${query.dataUpdatedAt}`
          }
          className="eh-fade-in"
        >
          {method.length === 0 ? (
            <p className="eh-caption text-destructive">
              {t("moduleUi.widgets.cardError")}
            </p>
          ) : query.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : query.isError ? (
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-start gap-2">
                <AlertCircle
                  className="mt-0.5 size-4 shrink-0 text-destructive"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="eh-caption text-destructive">
                    {t("moduleUi.widgets.cardError")}
                  </p>
                  <p
                    className="eh-caption text-muted-foreground"
                    title={moduleErrorMessage(query.error, t)}
                  >
                    {t("moduleUi.widgets.cardErrorDesc")}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={(event) => {
                  event.stopPropagation();
                  void query.refetch();
                }}
              >
                {t("common.retry")}
              </Button>
            </div>
          ) : (
            <WidgetView widget={widget} data={query.data} locale={locale} />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
