# F1 · 开屏/Logo/图标/导航转场/删副标题

> 先读 `prompts/00-COMMON.md` 与 `docs/USER_FEEDBACK.md` 的「已收到（2026-10-31）」。
> 用户明确要求：**动画要多、要明显**；只有系统 `prefers-reduced-motion` 才降级。

## 用户原话要点

- 开屏仍然「有点卡、中间顿了一下」，收束必须**线性**。
- 应用内 logo 现在**没有动画**；要像开屏一样持续、缓慢地「光圈由外向内收」，一直循环。
- 点击左侧导航：**只做淡入淡出**，不要斜向扩展/遮罩；绝不能先出现空白白页，也不能盖住导航栏。
- 应用图标太丑（金色+黑底），换成应用内那个**深绿一圈一圈的涟漪 logo**；图标也要有涟漪感。
- 「被忽视的健康」这句副标题删掉（它只是 logo 含义解释）。

## 交付

### 1. 开屏动画（保留日食，但修卡顿）

- 重做 `src/branding/branding.css` 的时间轴：所有 transform/opacity 动画用 `linear` 或近乎线性；避免多个动画在不同延迟上互相抢帧。
- 减少同时动画的层数；只动 `transform`/`opacity`（不要动 border-color/filter/box-shadow 的逐帧值）；给关键层 `will-change: transform, opacity`。
- 确保「遮罩淡出」和「主界面淡入」不重叠到卡顿；总时长保持约 1600ms。
- `?splash=1` 可重播，`?splash=hold` 仍可用；`prefers-reduced-motion` 直接显示。
- 用 60fps 录屏/DevTools Performance 或至少逐帧截图验证收束是连续线性的。

### 2. 应用内 logo：深绿涟漪 + 持续由外向内收

- 以 `src/components/common/eclipse-mark.tsx` 为基础重画：暖白/深色底上都能看清的**深绿同心圆环**（3–4 圈），风格接近应用内现有 logo，不要金色。
- 动画：外圈向内收/缩放，错开时间，像水波回收；**8–12s 无限循环**，比开屏慢，不抢注意力；`prefers-reduced-motion` 静止。
- 侧栏顶部使用该 logo；`src/branding/Logo.tsx` 的 Wordmark 默认不显示副标题；侧栏删除「被忽视的健康」。
- 设置页 About 的 `app.tagline` 不在本任务范围（F4 所有），不要改 `src/pages/settings.tsx`。
- 保持无障碍名称 `eclipse health`。

### 3. 应用图标

- 用同一套深绿涟漪设计生成/替换 `src-tauri/icons/` 的 Windows 图标：
  - `icon.ico`（含 16/24/32/48/64/128/256 多尺寸）、`32x32.png`、`64x64.png`、`128x128.png`、`128x128@2x.png`、`icon.png`；
  - 其余 Windows Store 尺寸（Square*Logo、StoreLogo）尽量同步；`icon.icns` 可保留旧文件（Windows 不使用）。
- 不要改 `tauri.conf.json` 的路径，只替换文件内容；确认 `npm run tauri build` 能读取。
- 图标背景透明或暖白，不要黑底金环。

### 4. 导航转场：只淡入淡出

- `src/components/layout/page-transition.tsx`：移除 clip-path 斜向 sweep 与 `.eh-nav-sweep` 覆盖层（或保留但永不启用）；改为纯淡入淡出：
  - 路由切换时新页面 200ms 淡入；不要先显示空白白页；
  - 尽量保留旧页面直到新页面首帧就绪（可用 `useLayoutEffect` + 双缓冲/延迟卸载；若复杂，至少不做白色遮罩，直接内容淡入）；
  - 侧栏永远不被覆盖；不阻塞导航/后退。
- `src/lib/motion.ts` 中 sweep 常量可保留但不再用于导航；更新注释。
- `prefers-reduced-motion` 直接切换。

### 5. 验证

- `npm run build` 通过。
- 截图/录屏：开屏 5–6 个关键帧、侧栏 logo 两个循环相位、图标文件预览、导航切换前后；放 `reports/screenshots/F1-*.png`。
- 控制台 0 error；切换 5 个页面无白屏；`?splash=1` 可重播。

## 文件所有权（只改这些）

- `src/branding/**`
- `src/components/common/eclipse-mark.tsx`
- `src/components/layout/**`
- `src/lib/motion.ts`
- `src-tauri/icons/**`
- `reports/F1-*.md`、`reports/screenshots/F1-*.png`

## 明确不做

- 不改 dashboard/quotes/themes/index.css 的配色变量（F2 所有权）。
- 不改外部 API（F3/F4）、不改业务逻辑。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 报告

写 `reports/F1-brand-motion-report.md`，≤80 行：开屏时间轴、logo/图标设计、导航转场实现、验证与截图、未做项。
