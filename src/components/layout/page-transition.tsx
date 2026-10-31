import { useLayoutEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import {
  consumeNavOrigin,
  EASE_STANDARD,
  MOTION,
  prefersReducedMotion,
} from "@/lib/motion";

const SWEEP_MS = MOTION.sweep;
const SWEEP_FADE_MS = 160;
/** 展开快完成时新页面才开始淡入，避免两层动画同时抢注意力。 */
const CONTENT_DELAY_MS = 300;

/**
 * 页面转场：从侧栏导航项的矩形位置斜向展开遮罩，再让新页面淡入。
 *
 * 路由切换本身不被阻塞；遮罩只是覆盖在新页面之上。
 * 浏览器不支持 / 减少动效 / 非导航来源的跳转，都回退为普通淡入。
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  const contentRef = useRef<HTMLDivElement | null>(null);
  const sweepRef = useRef<HTMLDivElement | null>(null);
  const timers = useRef<number[]>([]);
  const frame = useRef<number | null>(null);
  const runId = useRef(0);

  useLayoutEffect(() => {
    const content = contentRef.current;
    const sweep = sweepRef.current;
    const origin = consumeNavOrigin();
    const id = ++runId.current;

    for (const timer of timers.current) window.clearTimeout(timer);
    timers.current = [];
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;

    if (!content || !sweep) return;

    sweep.style.display = "none";
    sweep.style.opacity = "0";

    if (!origin || prefersReducedMotion()) return;

    const main = document.getElementById("main");
    const box = main?.getBoundingClientRect();
    if (!box || box.width < 1 || box.height < 1) return;

    // 遮罩从导航项左边缘开始，覆盖到内容区右边缘。
    const left = Math.min(origin.left, box.left);
    const width = Math.max(1, box.right - left);
    const height = box.height;
    const ox = origin.left - left;
    const oy = origin.top - box.top;
    const start = `polygon(${ox}px ${oy}px, ${ox + origin.width}px ${oy}px, ${
      ox + origin.width
    }px ${oy + origin.height}px, ${ox}px ${oy + origin.height}px)`;
    // 右侧保留明显斜边；顶部多 80px 保证展开后完全覆盖内容区（超出部分被视口裁掉）。
    const end = `polygon(0px 0px, ${width + 80}px 0px, ${width}px ${height}px, 0px ${height}px)`;

    Object.assign(sweep.style, {
      left: `${left}px`,
      top: `${box.top}px`,
      width: `${width}px`,
      height: `${height}px`,
      display: "block",
      opacity: "1",
      transition: "none",
      clipPath: start,
    });
    content.style.animationDelay = `${CONTENT_DELAY_MS}ms`;

    // 强制一次样式计算，让 clip-path 的初始值生效后再开始过渡。
    void sweep.offsetWidth;

    frame.current = requestAnimationFrame(() => {
      if (runId.current !== id) return;
      sweep.style.transition = `clip-path ${SWEEP_MS}ms ${EASE_STANDARD}`;
      sweep.style.clipPath = end;

      timers.current.push(
        window.setTimeout(() => {
          if (runId.current !== id) return;
          sweep.style.transition = `opacity ${SWEEP_FADE_MS}ms linear`;
          sweep.style.opacity = "0";
          timers.current.push(
            window.setTimeout(() => {
              if (runId.current !== id) return;
              sweep.style.display = "none";
              content.style.animationDelay = "";
            }, SWEEP_FADE_MS),
          );
        }, SWEEP_MS),
      );
    });

    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null;
      for (const timer of timers.current) window.clearTimeout(timer);
      timers.current = [];
    };
  }, [location.key]);

  return (
    <>
      <div key={location.key} ref={contentRef} className="eh-page eh-page-enter">
        {children}
      </div>
      <div ref={sweepRef} className="eh-nav-sweep" aria-hidden="true" />
    </>
  );
}
