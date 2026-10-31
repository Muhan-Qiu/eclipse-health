/**
 * 动效基线与跨组件工具（D1）。
 *
 * 约定：时长 120ms 微反馈 / 200ms 常规 / 320ms 页面 / 480ms 强调；
 * 缓动统一为 cubic-bezier(0.2, 0, 0, 1)，入场可轻微 overshoot，但不弹跳。
 * 动画只改 transform / opacity / filter，避免触发布局。
 */

export const MOTION = {
  micro: 120,
  base: 200,
  page: 320,
  emphasis: 480,
  /** 侧栏导航斜向展开（320–420ms 区间）。 */
  sweep: 380,
} as const;

export const EASE_STANDARD = "cubic-bezier(0.2, 0, 0, 1)";

export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/**
 * 点击侧栏导航时记下该项的矩形，PageTransition 据此做斜向展开。
 * 用模块级变量而不是 context：点击先于路由变化，且同一时刻只可能有一个转场。
 */
let navOrigin: { rect: DOMRect; at: number } | null = null;

export function markNavOrigin(element: Element | null): void {
  if (!element) return;
  try {
    navOrigin = { rect: element.getBoundingClientRect(), at: performance.now() };
  } catch {
    navOrigin = null;
  }
}

/** 取出并清空导航起点；超过 800ms 视为过期，避免影响程序化跳转。 */
export function consumeNavOrigin(): DOMRect | null {
  const entry = navOrigin;
  navOrigin = null;
  if (!entry) return null;
  if (performance.now() - entry.at > 800) return null;
  const { rect } = entry;
  return rect.width > 0 && rect.height > 0 ? rect : null;
}
