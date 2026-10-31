import { useId } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export type LogoVariant = "auto" | "light" | "dark" | "mono";

export interface LogoProps {
  /** 像素尺寸或任意 CSS 长度，默认 32。 */
  size?: number | string;
  /** auto 跟随主题令牌；light/dark 用于固定在亮/暗背景上的场景；mono 用 currentColor。 */
  variant?: LogoVariant;
  className?: string;
  /** 无障碍名称；装饰性场景请设 decorative。 */
  title?: string;
  decorative?: boolean;
  /** 常驻 logo：缓慢呼吸循环（侧栏/顶栏），减少动效时自动静止。 */
  loop?: boolean;
}

/**
 * 品牌标识：深墨圆盘 + 日冕环。
 * 颜色全部来自 --eh-brand-*（由 --eh-logo-* / --eh-accent 派生），换配色只需改令牌。
 */
export function Logo({
  size = 32,
  variant = "auto",
  className,
  title = "eclipse health",
  decorative = false,
  loop = false,
}: LogoProps) {
  // SVG 渐变 id 必须页内唯一，React 19 的 useId 含冒号，去掉后再用于 url(#...)。
  const gradientId = `eh-corona-${useId().replace(/:/g, "")}`;
  const mono = variant === "mono";

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 128 128"
      fill="none"
      width={size}
      height={size}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : title}
      aria-hidden={decorative || undefined}
      className={cn("eh-brand-logo", `eh-brand-logo--${variant}`, className)}
    >
      <defs>
        <radialGradient id={gradientId} cx="64" cy="64" r="64" gradientUnits="userSpaceOnUse">
          <stop offset="0.58" stopColor="var(--eh-brand-ring)" stopOpacity="0" />
          <stop offset="0.70" stopColor="var(--eh-brand-ring)" stopOpacity={mono ? 0 : 0.34} />
          <stop offset="0.82" stopColor="var(--eh-brand-ring)" stopOpacity={mono ? 0 : 0.14} />
          <stop offset="1" stopColor="var(--eh-brand-ring)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="64" cy="64" r="64" fill={`url(#${gradientId})`} />
      <g className={loop ? "eh-brand-logo__loop" : undefined}>
        <circle cx="64" cy="64" r="52" stroke="var(--eh-brand-ring)" strokeWidth="3.2" />
        <circle cx="64" cy="64" r="40" fill="var(--eh-brand-disk)" />
        <circle
          cx="64"
          cy="64"
          r="40"
          stroke="var(--eh-brand-ring)"
          strokeWidth="1"
          opacity={mono ? 0 : 0.3}
        />
      </g>
    </svg>
  );
}

export interface WordmarkProps {
  /** 是否显示副标题「被忽视的健康」。 */
  subtitle?: boolean;
  className?: string;
}

/** 启动页与侧栏可复用的字标；字号由使用处通过 CSS 控制。 */
export function Wordmark({ subtitle = true, className }: WordmarkProps) {
  const { t } = useTranslation();
  return (
    <span className={cn("eh-brand-wordmark", className)}>
      <span className="eh-brand-wordmark__name">{t("app.name")}</span>
      {subtitle ? <span className="eh-brand-wordmark__sub">{t("app.tagline")}</span> : null}
    </span>
  );
}
