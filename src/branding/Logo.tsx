import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export type LogoVariant = "auto" | "light" | "dark" | "mono";

/** 与 EclipseMark 同一套 4 圈涟漪几何。 */
const RINGS = [
  { r: 46, width: 3.6, opacity: 0.95 },
  { r: 33, width: 3, opacity: 0.74 },
  { r: 21, width: 2.4, opacity: 0.54 },
  { r: 10, width: 1.9, opacity: 0.36 },
] as const;

export interface LogoProps {
  /** 像素尺寸或任意 CSS 长度，默认 32。 */
  size?: number | string;
  /** auto 跟随主题令牌；light/dark 用于固定在亮/暗背景上的场景；mono 用 currentColor。 */
  variant?: LogoVariant;
  className?: string;
  /** 无障碍名称；装饰性场景请设 decorative。 */
  title?: string;
  decorative?: boolean;
  /** 常驻 logo：深绿涟漪由外向内收，10s 无限循环；减少动效时静止。 */
  loop?: boolean;
}

/**
 * 品牌标识：深绿同心圆环（3–4 圈）+ 中心点。
 * 颜色来自 --eh-brand-ripple（由 --eh-signal / --eh-text 派生），不再使用金色。
 */
export function Logo({
  size = 32,
  variant = "auto",
  className,
  title = "eclipse health",
  decorative = false,
  loop = false,
}: LogoProps) {
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
      <g className={cn("eh-brand-ripple", loop && "eh-brand-ripple--loop")}>
        {RINGS.map((ring) => (
          <circle
            key={ring.r}
            className="eh-brand-ripple__ring"
            cx="64"
            cy="64"
            r={ring.r}
            fill="none"
            stroke="var(--eh-brand-ripple)"
            strokeWidth={ring.width}
            strokeOpacity={ring.opacity}
          />
        ))}
        <circle cx="64" cy="64" r="4" fill="var(--eh-brand-ripple)" />
      </g>
    </svg>
  );
}

export interface WordmarkProps {
  /** 是否显示副标题「被忽视的健康」；默认不显示（副标题只解释 logo 含义）。 */
  subtitle?: boolean;
  className?: string;
}

/** 启动页与侧栏可复用的字标；字号由使用处通过 CSS 控制。 */
export function Wordmark({ subtitle = false, className }: WordmarkProps) {
  const { t } = useTranslation();
  return (
    <span className={cn("eh-brand-wordmark", className)}>
      <span className="eh-brand-wordmark__name">{t("app.name")}</span>
      {subtitle ? <span className="eh-brand-wordmark__sub">{t("app.tagline")}</span> : null}
    </span>
  );
}
