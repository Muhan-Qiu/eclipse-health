# D1 · 动画系统基线（启动 / 切页 / 卡片 / 波形反馈）

> 先读 `prompts/00-COMMON.md`、`src/branding/branding.css`、`src/branding/SplashScreen.tsx`、`src/index.css`，再读本文件。

## 目标

建立统一、克制的动效基线，让桌面应用有「活着」的反馈，但不花哨、不卡顿。**不依赖用户反馈**，先把通用动效做好；用户具体意见进 D3。

## 动效规范（必须遵守）

- 时长令牌：`120ms`（微反馈）、`200ms`（常规）、`320ms`（页面/大块）；缓动 `cubic-bezier(0.2, 0, 0, 1)` 或现有令牌。
- 尊重 `prefers-reduced-motion: reduce`：所有新增动效必须降级为无动画/瞬时；不要只靠全局 `* { transition-duration: 0.01ms }` 兜底。
- 不引入高饱和、玻璃拟态、弹跳/旋转大动画；不改变布局尺寸导致抖动。
- 不新增依赖（`motion` 已安装，可少量使用；能用 CSS 就 CSS）。

## 交付

### 1. 动效令牌

- 在 `src/index.css` 或 `src/lib/motion.ts` 定义时长/缓动常量，供组件复用；不要散落魔法数字。
- 页面容器统一使用一个 `PageTransition` 包装（`src/components/layout/page-transition.tsx`）：淡入 + 4–8px 上移，320ms；切页不阻塞交互。

### 2. 启动日食动画

- 保留现有 1600ms 日食动画与 logo；只做打磨：
  - 启动过快/过慢时保持节奏稳定；
  - 减少动效模式直接显示内容；
  - 不因动画阻塞首屏数据加载（现有逻辑保持）。

### 3. 页面与卡片

- `src/pages/dashboard.tsx`：引导卡片/最近记录/指标卡首次进入时轻微 stagger（≤3 组，间隔 40–60ms）；刷新数据不重复播放入场。
- 列表/表格行 hover 反馈统一 120ms；不改变行高。
- 空状态/加载骨架到内容的切换用 200ms 淡入。

### 4. 波形交互反馈

- `src/components/records/waveform-viewer.tsx`（及 `src/pages/record-detail.tsx` 中相关部分）：
  - 选中 R 峰/心搏时的高亮过渡 120ms；
  - 缩放/平移保持即时，不加惯性动画；
  - 质量区段/异常标记 hover 有轻微反馈，但不遮挡波形。

### 5. 验证

- `npm run build` 通过。
- 亮/暗截图：启动帧（如可截）、仪表盘、记录详情；放 `reports/screenshots/D1-*.png`。
- 用 `prefers-reduced-motion: reduce` 模拟（CDP/Playwright）确认无动画、无报错。
- 控制台 0 error；切换页面无明显掉帧（主观 + 无长任务报错即可）。

## 文件所有权（只改这些）

- `src/index.css`
- `src/lib/motion.ts`（新建，可选）
- `src/components/layout/**`
- `src/components/common/**`
- `src/branding/**`
- `src/pages/dashboard.tsx`
- `src/pages/record-detail.tsx`
- `src/components/records/waveform-viewer.tsx`（及同目录 waveform 子组件）

## 明确不做

- 不改 `src/pages/{records,trends,reports,assistant,profile,settings,modules,health-data,compare,about}.tsx`（D2 所有权）。
- 不改 `src/components/ui/**`（D2 所有权）、不改业务逻辑/接口/数据。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
```

报告 `reports/D1-motion-report.md`，≤80 行。必须写清：令牌值、每个动效位置、reduced-motion 处理、截图与验证结果、未做项。
