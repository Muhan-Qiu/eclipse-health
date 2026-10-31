import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "@/lib/motion";

interface AnimatedNumberProps {
  value: number | null;
  /** 每帧都会调用，保持与页面现有数字格式一致。 */
  format: (value: number) => string;
  /** 首次从 0 滚到目标值；后续刷新从旧值滚到新值。 */
  duration?: number;
  placeholder?: string;
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** 数值滚动（≤600ms）；减少动效时直接显示最终值。 */
export function AnimatedNumber({
  value,
  format,
  duration = 560,
  placeholder = "—",
}: AnimatedNumberProps) {
  const [display, setDisplay] = useState(0);
  // 从 0 开始，首次数据到达时滚到目标值；之后从上一个显示值继续。
  const currentRef = useRef(0);

  useEffect(() => {
    if (value === null) return;
    const from = currentRef.current;
    // 差异小于千分之一时没有滚动意义，直接落定。
    if (prefersReducedMotion() || Math.abs(value - from) < 0.001) {
      currentRef.current = value;
      setDisplay(value);
      return;
    }

    let frame = 0;
    // 用第一帧的时间做起点：首屏如果被波形渲染占住主线程，
    // 动画从真正开始绘制的那一刻计时，而不是从 effect 挂载时计时。
    let started: number | null = null;
    const tick = (now: number) => {
      if (started === null) started = now;
      const progress = Math.min(1, Math.max(0, (now - started) / duration));
      const next = from + (value - from) * easeOutCubic(progress);
      currentRef.current = next;
      setDisplay(next);
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        currentRef.current = value;
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  if (value === null) return <>{placeholder}</>;
  return <>{format(display)}</>;
}
