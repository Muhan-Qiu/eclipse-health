# 报告 · D1 动画系统基线
状态：完成（3 项受文件所有权限制未做，见「未做」）

## 交付
- `src/lib/motion.ts`：统一时长/缓动、`prefers-reduced-motion`、导航起点记录。
- `src/components/layout/page-transition.tsx`：侧栏导航斜向展开转场；非导航跳转回退为普通淡入。
- `src/branding/branding.css`：启动日食改线性/近乎线性，收束只动 transform/opacity；侧栏 logo 8s 呼吸循环。
- `src/index.css`：stagger、reveal、数字/星标/遮罩 keyframes、弹窗 200/160ms、主题颜色 200ms、微反馈 120ms。
- `src/components/common/animated-number.tsx`：数值滚动（≤560ms，首帧计时，减少动效直接落定）。
- 仪表盘/记录详情：卡片与记录行 stagger、数字滚动、Sparkline 绘制、波形淡入、卡片 hover 抬升。
- 侧栏/顶栏：logo 循环、导航高亮 200ms、搜索按钮 120ms 按压反馈。

## 动效位置与参数
- 启动日食 1600ms：黑盘收束 `linear`，光环/辉光/字标 `cubic-bezier(0.33,0,0.67,1)`；去掉 border-color 动画，只保留 transform/opacity。
- 侧栏 logo：8s infinite，圆盘 scale 1→0.955→1，外环 opacity .35→.85；`prefers-reduced-motion` 静止。
- 切页：遮罩从导航项矩形斜向展开 380ms `cubic-bezier(0.2,0,0,1)`，右侧斜边 80px；新页延迟 300ms 后再 320ms 淡入上移 8px。
- 分组入场：420ms，子项间隔 50ms（前 12 项）；仪表盘引导卡/最近记录/指标卡/模块卡分组。
- 数字：0→目标值 560ms ease-out-cubic；刷新时从旧值继续。
- Sparkline：`stroke-dashoffset` 600ms 左→右绘制（`pathLength=1`）。
- 列表：行 hover 120ms；收藏星标 240ms 缩放；骨架/空状态 200ms 淡入。
- 弹窗：入 200ms、出 160ms，只动 opacity/scale（保留居中 translate）；Overlay 同步淡入淡出；Toast 240ms。
- 主题/配色：背景/文字/边框 200ms 过渡，避免闪白。
- 波形：首次进入淡入上移 480ms；心搏详情每次选中 200ms 淡入；心搏列表/质量区段选中与 hover 120ms。

## 验证
- `npm run build`：通过（tsc + vite，3.2s；仅既有 chunk 体积提示）。
- 控制台：0 error。
- 减少动效（Playwright 模拟 reduce）：logo/page 动画时长 `1e-05s`、启动遮罩不渲染、导航遮罩 `display:none`，路由正常。
- 截图：`reports/screenshots/D1-splash-dark.png`、`D1-dashboard-dark.png`、`D1-record-waveform.png`、`D1-theme-light.png`、`D1-nav-sweep-light.png`、`D1-nav-sweep-detail.png`、`D1-reduced-motion.png`。
- 数值卡实测：数据到达后 75 / 66.7 / 0.1 / 100 正确；导航/主题/波形无报错。

## 未做 / 偏离
- 未用 View Transitions API：需要包裹路由更新、可能阻塞导航；已按要求采用不阻塞的 clip-path 覆盖层，兼容所有 WebView。
- R 峰选中竖线/高亮环的 120ms 过渡与一次性脉冲未做：标记绘制在 `src/features/waveform/lead-strip.tsx` 的 canvas 内，不属本任务文件所有权；改用「心搏详情淡入 + 列表选中过渡」反馈。
- 质量区段/异常标记 canvas hover 未改（同上）。
- 模块卡 RPC 刷新时内部骨架→内容淡入未改（WidgetCard 不在所有权内）；卡片挂载时的 stagger 已覆盖首次出现。
- 健康数据/模块列表行 stagger 未做：这两个页面归 D2。
- 除任务列出的路径外，另改了同目录的 `record-row.tsx`、`beat-list.tsx`、`beat-details.tsx`、`quality-legend.tsx`（列表/波形子组件，D2 未声明所有权）；无依赖新增、未 commit。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `src/features/waveform/lead-strip.tsx`：若要 R 峰选中脉冲/hover 反馈，需在 canvas 绘制层加短暂 alpha 动画。
- `src/features/modules/widgets/**`：模块卡内部加载态可补 skeleton→内容淡入。

## 需要指挥官决策
- 无阻塞项。斜向展开目前会短暂覆盖被点击的导航项，若希望遮罩从内容区左缘起算可再调。

## 建议下一批
- 收集候选包反馈（D3）：优先确认动画幅度、侧栏转场速度、数字滚动是否符合预期，再微调时长。
