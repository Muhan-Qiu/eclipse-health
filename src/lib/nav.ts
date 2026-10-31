import {
  Blocks,
  FileChartColumn,
  FileText,
  GitCompare,
  HeartPulse,
  Info,
  LayoutDashboard,
  Settings,
  Sparkles,
  TrendingUp,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  path: string;
  labelKey: string;
  icon: LucideIcon;
  end?: boolean;
}

export const primaryNav: NavItem[] = [
  { path: "/", labelKey: "nav.dashboard", icon: LayoutDashboard, end: true },
  { path: "/records", labelKey: "nav.records", icon: FileText },
  { path: "/health-data", labelKey: "nav.healthData", icon: HeartPulse },
  { path: "/profile", labelKey: "nav.profile", icon: UserRound },
  { path: "/trends", labelKey: "nav.trends", icon: TrendingUp },
  { path: "/reports", labelKey: "nav.reports", icon: FileChartColumn },
  { path: "/assistant", labelKey: "nav.assistant", icon: Sparkles },
];

export const secondaryNav: NavItem[] = [
  { path: "/modules", labelKey: "nav.modules", icon: Blocks },
  { path: "/settings", labelKey: "nav.settings", icon: Settings },
  { path: "/about", labelKey: "nav.about", icon: Info },
];

/** 不进入侧栏，但需要参与面包屑/页面标题解析的路由。 */
export const hiddenNav: NavItem[] = [
  { path: "/compare", labelKey: "nav.compare", icon: GitCompare },
];

export const allNav: NavItem[] = [...primaryNav, ...secondaryNav, ...hiddenNav];

/** 顶部栏用：把子路由（如 /records/:id）归到父级导航项。 */
export function findNavItem(pathname: string): NavItem | undefined {
  return [...allNav]
    .sort((a, b) => b.path.length - a.path.length)
    .find((item) =>
      item.end ? pathname === item.path : pathname.startsWith(item.path),
    );
}
