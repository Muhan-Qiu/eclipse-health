import {
  Activity,
  BarChart3,
  Blocks,
  Database,
  Download,
  Languages,
  Palette,
  Sparkles,
  Watch,
  Waves,
  type LucideIcon,
} from "lucide-react";

/** 模块类型 → 图标。未知类型回退到 Blocks，避免新增类型导致界面空白。 */
const MODULE_TYPE_ICONS: Record<string, LucideIcon> = {
  "analysis-model": Activity,
  "ai-tool": Sparkles,
  "data-source": Database,
  "dashboard-widget": BarChart3,
  "device-adapter": Watch,
  "signal-engine": Waves,
  exporter: Download,
  theme: Palette,
  locale: Languages,
};

export function moduleTypeIcon(type: string | undefined): LucideIcon {
  return (type && MODULE_TYPE_ICONS[type]) || Blocks;
}

export function ModuleTypeIcon({
  type,
  className,
}: {
  type: string | undefined;
  className?: string;
}) {
  const Icon = moduleTypeIcon(type);
  return <Icon className={className} aria-hidden="true" />;
}
