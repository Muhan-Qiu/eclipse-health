# D1 · 动画系统（丰富、统一、有存在感）

> 先读 `prompts/00-COMMON.md`、`src/branding/branding.css`、`src/branding/SplashScreen.tsx`、`src/index.css`，再读本文件。
> **产品方向：动画要多、要明显、要有质感。** 只有系统开启 `prefers-reduced-motion` 时才降级；默认完整播放。

## 目标

把动画做成应用的辨识度之一：启动、切页、卡片、数值、图表、波形、列表、弹窗、主题切换都有连贯反馈；丰富但不混乱，不卡顿。

## 用户明确要求（必须做）

1. **侧栏/顶栏 logo 持续慢速循环**：进入应用后，logo 的「黑盘 + 亮环」像启动动画一样缓慢收束/呼吸，一直循环；比启动动画慢（建议 6–10s 一轮），不抢注意力。`prefers-reduced-motion` 时静止。
2. **启动收束要线性**：现有日食收束过程用户觉得「有点卡、不是线性」。改用 `linear`/近乎线性的缓动，只动 transform/opacity，确保 60fps；不要用会触发逐帧布局的属性。
3. **侧栏导航「斜向扩展」转场**：点击左侧导航的圆角矩形项时，不要直接切到右侧页面；从该导航项的矩形位置开始，一个带斜边的矩形/遮罩向右扩展并填满内容区，然后新页面淡入。
   - 优先用 View Transitions API（`document.startViewTransition`，WebView2/Chromium 支持则用）+ CSS `view-transition-name`/`clip-path`；
   - 不支持时用 Motion/CSS 覆盖层：从导航项 `getBoundingClientRect()` 到内容区，`clip-path: polygon(...)` 斜向扩展，320–420ms；
   - 不阻塞路由；动画失败/被打断时回退为普通淡入；`prefers-reduced-motion` 直接切换。

## 动效规范

- 时长：`120ms` 微反馈、`200ms` 常规、`320ms` 页面/大块、`480ms` 启动/强调（仅少量使用）。
- 缓动：`cubic-bezier(0.2, 0, 0, 1)`；入场可用轻微 overshoot，但不要弹跳。
- 同一屏同时动画的元素分组 stagger（40–60ms），不要所有东西一起动。
- 不改变布局尺寸导致抖动；动画只做 transform/opacity/filter，避免触发布局。
- `prefers-reduced-motion: reduce` 时全部瞬时完成；这是唯一降级条件。
- 不引入高饱和、玻璃拟态、霓虹/发光；保持莫奈低饱和与设计令牌。
- 不新增依赖（`motion` 已安装，可少量使用；能用 CSS 就 CSS）。

## 交付（尽量都做）

### 1. 启动日食动画

- 打磨现有 1600ms 日食：黑盘 + 亮环的出现、光晕扩散、logo 收束；节奏有“呼吸感”。
- 不阻塞首屏数据；动画结束平滑交接到仪表盘（淡出 + 内容淡入）。
- 减少动效模式直接显示内容。

### 2. 切页过渡

- 统一 `PageTransition`（`src/components/layout/page-transition.tsx`）：淡入 + 6–10px 上移/轻微缩放，320ms；切页不阻塞交互。
- 侧栏选中态滑动/高亮过渡 200ms；顶栏按钮 hover/active 120ms。

### 3. 仪表盘

- 引导卡片、最近记录、指标卡分组 stagger 入场；刷新数据不重复播放。
- 数值卡：数字从 0/旧值滚动到新值（≤600ms，尊重 reduced-motion）。
- Sparkline：首次出现时线条从左到右绘制（CSS `stroke-dashoffset`，≤600ms）。
- 模块卡片：入场 stagger；hover 轻微抬升/阴影；RPC 刷新时骨架→内容淡入。
- 波形预览：首次加载淡入 + 轻微上移。

### 4. 列表与表格

- 记录/健康数据/模块列表行入场 stagger（前 8–12 行即可，避免长列表卡顿）。
- hover 背景/边框过渡 120ms；选中态、收藏星标点击有缩放/颜色反馈。
- 空状态/加载骨架切换淡入 200ms。

### 5. 波形交互

- R 峰/心搏选中：高亮环/竖线 120ms 过渡；选中时轻微脉冲（一次，不循环）。
- 质量区段/异常标记 hover 轻微反馈，不遮挡波形。
- 缩放/平移保持即时，不加惯性；工具按钮 active 反馈 120ms。

### 6. 弹窗、Toast、主题

- Dialog/Sheet 入场 200ms（淡入 + 轻微缩放/上移），退出 160ms。
- Toast 滑入/滑出；错误 toast 不抖动过度。
- 主题/配色切换：背景/文字/边框 200ms 过渡（避免整页闪白）。

### 7. 验证

- `npm run build` 通过。
- 截图/录屏：启动帧、仪表盘入场、记录详情波形选中、主题切换；放 `reports/screenshots/D1-*.png`。
- 用 CDP/Playwright 模拟 `prefers-reduced-motion: reduce`，确认无动画、无报错。
- 控制台 0 error；主观确认无明显掉帧。

## 文件所有权（只改这些）

- `src/index.css`
- `src/lib/motion.ts`（新建）
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

报告 `reports/D1-motion-report.md`，≤80 行。必须写清：每个动效位置、时长/缓动、stagger 分组、reduced-motion 处理、截图与验证结果、未做项。
