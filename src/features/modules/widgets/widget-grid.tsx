import "@/features/modules/i18n";

import { useTranslation } from "react-i18next";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ModuleWidget, WidgetSize } from "../types";
import { WidgetCard } from "./widget-card";
import { useModuleWidgets } from "./use-widgets";

/** 12 列（xl）→ 8 列（desk）→ 单列；尺寸只影响占位，不放大内容。 */
const SIZE_CLASS: Record<WidgetSize, string> = {
  sm: "desk:col-span-2 xl:col-span-3",
  md: "desk:col-span-4 xl:col-span-4",
  lg: "desk:col-span-8 xl:col-span-6",
};

function sizeClass(size: WidgetSize | string): string {
  return SIZE_CLASS[size as WidgetSize] ?? SIZE_CLASS.md;
}

function widgetKey(widget: ModuleWidget): string {
  return `${widget.moduleId}:${widget.id}`;
}

/** 独立使用时的模块卡片区块；仪表盘已改为按布局逐卡渲染。 */
export function WidgetGrid() {
  const { t } = useTranslation();
  const { widgets, isLoading, isError, refetch } = useModuleWidgets();

  if (isLoading) {
    return (
      <section className="mt-6" aria-busy="true">
        <h2 className="eh-h3">{t("moduleUi.widgets.sectionTitle")}</h2>
        <div className="eh-grid mt-3">
          {[0, 1, 2].map((index) => (
            <Skeleton
              key={index}
              className="h-28 rounded-xl desk:col-span-2 xl:col-span-4"
            />
          ))}
        </div>
      </section>
    );
  }

  if (isError) {
    return (
      <Card className="mt-6">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 px-4">
          <div className="flex min-w-0 items-start gap-2">
            <AlertCircle
              className="mt-0.5 size-4 shrink-0 text-destructive"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {t("moduleUi.widgets.loadError")}
              </p>
              <p className="eh-caption text-muted-foreground">
                {t("moduleUi.widgets.loadErrorDesc")}
              </p>
            </div>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={refetch}>
            <RefreshCw data-icon="inline-start" />
            {t("common.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  // 没有模块卡片时整块消失，不留空壳。
  if (widgets.length === 0) return null;

  return (
    <section className="mt-6" aria-labelledby="dashboard-widgets-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="dashboard-widgets-title" className="eh-h3">
          {t("moduleUi.widgets.sectionTitle")}
        </h2>
        <span className="eh-caption text-muted-foreground">
          {t("moduleUi.widgets.sectionDesc")}
        </span>
      </div>
      <div className="eh-grid mt-3">
        {widgets.map((widget) => (
          <WidgetCard
            key={widgetKey(widget)}
            widget={widget}
            className={sizeClass(widget.size)}
          />
        ))}
      </div>
    </section>
  );
}
