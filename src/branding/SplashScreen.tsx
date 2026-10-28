import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Wordmark } from "./Logo";
import "./branding.css";

const PLAYED_KEY = "eh-splash-played";
/** 与 branding.css 的动画时序保持一致（见文件末尾时间轴）。 */
const FULL_DURATION_MS = 1600;
const REDUCED_DURATION_MS = 300;
const LEAVE_DURATION_MS = 200;
/** ?splash=hold 时冻结在动画最有代表性的时刻，便于截图/调试。 */
const HOLD_AT_MS = { dark: 950, light: 1150 } as const;

type SplashMode = "light" | "dark";

interface SplashDebug {
  /** 本次是否强制播放（不受 sessionStorage 限制）。 */
  force: boolean;
  /** 播放到关键时刻后冻结，等待点击关闭。 */
  hold: boolean;
}

function readDebugFlag(): SplashDebug {
  try {
    const fromHash = window.location.hash.includes("?")
      ? window.location.hash.slice(window.location.hash.indexOf("?") + 1)
      : "";
    const value =
      new URLSearchParams(window.location.search).get("splash") ??
      new URLSearchParams(fromHash).get("splash");
    return { force: value === "1" || value === "force" || value === "hold", hold: value === "hold" };
  } catch {
    return { force: false, hold: false };
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
 * 动画期间主界面在遮罩下方正常挂载，结束后遮罩卸载。
 */
export function SplashScreen({ children }: SplashScreenProps) {
  const [mode] = useState<SplashMode>(currentMode);
  const [reduced] = useState(prefersReducedMotion);
  const [playing, setPlaying] = useState(() => !reduced && PLAY_ON_LOAD);
  const [paused, setPaused] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const leavingRef = useRef(false);
  const leaveTimer = useRef<number | null>(null);
  const startedAt = useRef(performance.now());
  // 过早跳过时主界面还没开始淡入，改走 300ms 的短淡入，避免空白等待
  const [skippedEarly, setSkippedEarly] = useState(false);

  const dismiss = useCallback(() => {
    if (leavingRef.current) return;
    leavingRef.current = true;
    if (performance.now() - startedAt.current < 1050) setSkippedEarly(true);
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

  // hold 模式：到达关键帧后暂停所有动画
  useEffect(() => {
    if (!playing || !DEBUG.hold) return;
    const timer = window.setTimeout(() => setPaused(true), HOLD_AT_MS[mode]);
    return () => window.clearTimeout(timer);
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
  const animated = reduced || skippedEarly;
  const appClassName =
    playing || reduced
      ? `eh-brand-app ${animated ? "eh-brand-app--reduced" : "eh-brand-app--intro"}`
      : "eh-brand-app";

  return (
    <>
      <div className={appClassName} inert={playing || undefined}>
        {children}
      </div>
      {playing ? (
        <div
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
  reducedDurationMs: REDUCED_DURATION_MS,
} as const;
