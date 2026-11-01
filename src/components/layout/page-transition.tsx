import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useOutlet } from "react-router-dom";
import { MOTION, prefersReducedMotion } from "@/lib/motion";
import "./page-transition.css";

interface Layer {
  key: string;
  node: ReactNode;
}

/**
 * 页面转场：纯交叉淡入淡出，不再使用 clip-path 斜向 sweep。
 *
 * 这里用 useOutlet() 拿到「当前匹配到的路由元素」而不是 <Outlet /> 占位符：
 * 占位符会跟随新 location 重新渲染，旧层就失去意义；拿到的元素是静态的，
 * 放到旧层后仍保持已挂载的子树与数据，因此不会出现空白白页或重复请求。
 * 旧层绝对定位、pointer-events:none、aria-hidden，只负责淡出。
 * 侧栏位于 main 之外，始终不被覆盖；导航本身从不被阻塞。
 * prefers-reduced-motion 时直接切换，不保留旧层。
 */
export function PageTransition() {
  const location = useLocation();
  const outlet = useOutlet();
  // 渲染期记录「当前已渲染的层」；路由变化时把它转存为旧层，保证旧页面不卸载。
  const latest = useRef<Layer>({ key: location.key, node: outlet });
  const [previous, setPrevious] = useState<Layer | null>(null);

  if (latest.current.key !== location.key) {
    const old = latest.current;
    latest.current = { key: location.key, node: outlet };
    setPrevious(prefersReducedMotion() ? null : old);
  } else {
    latest.current.node = outlet;
  }

  useEffect(() => {
    if (!previous) return;
    const timer = window.setTimeout(() => setPrevious(null), MOTION.pageFade + 60);
    return () => window.clearTimeout(timer);
  }, [previous]);

  const reduced = prefersReducedMotion();

  return (
    <div className="eh-page-stack">
      {previous ? (
        <div
          key={previous.key}
          className="eh-page eh-page-layer eh-page-layer--out"
          aria-hidden="true"
          inert
        >
          {previous.node}
        </div>
      ) : null}
      <div
        key={location.key}
        className={`eh-page eh-page-layer${reduced ? "" : " eh-page-layer--in"}`}
      >
        {outlet}
      </div>
    </div>
  );
}
