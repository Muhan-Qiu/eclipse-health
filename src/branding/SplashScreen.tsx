import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Wordmark } from "./Logo";
import "./branding.css";

const PLAYED_KEY = "eh-splash-played";
/** 与 branding.css 的动画时序保持一致（见文件顶部的启动时间轴）。 */
const FULL_DURATION_MS = 1600;
const LEAVE_DURATION_MS = 200;
/** ?splash=hold 时冻结在动画最有代表性的时刻，便于截图/调试。 */
const HOLD_AT_MS = { dark: 1000, light: 1250 } as const;

type SplashMode = "light" | "dark";

interface SplashDebug {
  /** 本次是否强制播放（不受 sessionStorage 限制）。 */
  force: boolean;
  /** 播放到关键时刻后冻结，等待点击关闭。 */
  hold: boolean;
  /** ?splash=hold&at=900：冻结在指定毫秒，用于逐帧截图。 */
  holdAt: number | null;
}

function readQueryParams(): URLSearchParams {
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash;
  const queryAt = hash.indexOf("?");
  if (queryAt >= 0) {
    const hashParams = new URLSearchParams(hash.slice(queryAt + 1));
    hashParams.forEach((value, key) => {
      if (!params.has(key)) params.set(key, value);
    });
  }
  return params;
}

function readDebugFlag(): SplashDebug {
  try {
    const params = readQueryParams();
    const value = params.get("splash");
    const rawAt = params.get("at");
    const parsedAt = rawAt === null ? Number.NaN : Number(rawAt);
    const holdAt = Number.isFinite(parsedAt)
      ? Math.min(FULL_DURATION_MS, Math.max(0, parsedAt))
      : null;
    return {
      force: value === "1" || value === "force" || value === "hold",
      hold: value === "hold",
      holdAt,
    };
  } catch {
    return { force: false, hold: false, holdAt: null };
  }
}

const DEBUG = readDebugFlag();
const HAS_PLAYED = (() => {
  try {
    return sessionStorage.getItem(PLAYED_KEY) === "1";
  } catch {
    return false;
  }
})();
const PLAY_ON_LOAD = DEBUG.force || !HAS_PLAYED;
if (PLAY_ON_LOAD) {
  try {
    // 每次应用启动播放一次；开发时想重播用 ?splash=1。
    sessionStorage.setItem(PLAYED_KEY, "1");
  } catch {
    // 存储不可用就每次播放
  }
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

function currentMode(): SplashMode {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export interface SplashScreenProps {
  children: ReactNode;
}

/**
 * 日食启动动画。只包裹现有 App，不改变路由与 Provider 结构。
 * 主界面在遮罩下方始终不透明；启动只是遮罩的一次线性交叉溶解。
 */
export function SplashScreen({ children }: SplashScreenProps) {
  const [mode] = useState<SplashMode>(currentMode);
  const [reduced] = useState(prefersReducedMotion);
  const [playing, setPlaying] = useState(() => !reduced && PLAY_ON_LOAD);
  const [paused, setPaused] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const splashRef = useRef<HTMLDivElement | null>(null);
  const leavingRef = useRef(false);
  const leaveTimer = useRef<number | null>(null);

  const dismiss = useCallback(() => {
    if (leavingRef.current) return;
    leavingRef.current = true;
    setPaused(false);
    setLeaving(true);
    leaveTimer.current = window.setTimeout(() => setPlaying(false), LEAVE_DURATION_MS);
  }, []);

  // 自动结束
  useEffect(() => {
    if (!playing || DEBUG.hold) return;
    const timer = window.setTimeout(() => setPlaying(false), FULL_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [playing]);

  // hold 模式：用 Web Animations API 把整棵遮罩精确冻结在目标毫秒。
  // setTimeout 受主线程启动耗时影响，逐帧截图会偏移；直接设置 currentTime 才能复现。
  useEffect(() => {
    if (!playing || !DEBUG.hold) return;
    const at = DEBUG.holdAt ?? HOLD_AT_MS[mode];
    const frame = requestAnimationFrame(() => {
      const element = splashRef.current;
      if (!element) return;
      for (const animation of element.getAnimations({ subtree: true })) {
        animation.currentTime = at;
        animation.pause();
      }
      setPaused(true);
    });
    return () => cancelAnimationFrame(frame);
  }, [mode, playing]);

  // 点击/任意按键跳过
  useEffect(() => {
    if (!playing) return;
    const onKeyDown = () => dismiss();
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dismiss, playing]);

  useEffect(() => {
    if (!playing) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [playing]);

  useEffect(
    () => () => {
      if (leaveTimer.current !== null) window.clearTimeout(leaveTimer.current);
    },
    [],
  );

  // 包裹层始终保留：若启动结束后移除它，React 会整棵卸载重挂载 App，
  // 导致 Provider / 查询状态丢失。
  return (
    <>
      <div className="eh-brand-app" inert={playing || undefined}>
        {children}
      </div>
      {playing ? (
        <div
          ref={splashRef}
          className="eh-brand-splash"
          data-mode={mode}
          data-paused={paused || undefined}
          data-leaving={leaving || undefined}
          onPointerDown={dismiss}
          aria-hidden="true"
        >
          <span className="eh-brand-splash__veil" />
          <div className="eh-brand-splash__scene">
            <span className="eh-brand-splash__glow" />
            <span className="eh-brand-splash__disk" />
            <span className="eh-brand-splash__ring" />
          </div>
          <div className="eh-brand-splash__word">
            <Wordmark />
          </div>
        </div>
      ) : null}
    </>
  );
}

export const splashTiming = {
  fullDurationMs: FULL_DURATION_MS,
  reducedDurationMs: 0,
} as const;
