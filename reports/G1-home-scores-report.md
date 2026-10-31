# 报告 · G1 首页「概览」重组 + 健康评分/建议 UI + 首启 LLM Key 引导
状态：完成

## 交付
- 首页顺序：问候/名言 → 健康评分卡 → 建议卡 → 健康数据摘要 → 原 ECG 引导/最近记录/指标/波形；移动端单列。
- `src/features/scores/health-score-grid.tsx`：总分大数字 + 分项小卡（颜色 + 文字等级），无分项/接口失败显示轻量「数据不足」，底部「缺数据：…」。
- `src/features/scores/suggestion-card.tsx`：最多 2 条；「和教练聊聊」跳 `/assistant?prompt=<编码后问题>`，不自动发送。
- `src/features/scores/health-summary-card.tsx`：`useHealthRecords` 取五类最新值（步数/心率/睡眠/体重/血压）；无数据显示「还没有健康数据」+ 唯一导入按钮。
- `src/features/onboarding/llm-key-prompt.tsx`：启动后调用 provider 列表；无 enabled+configured provider 时显示 Dialog；去配置跳 `/assistant?focus=provider`；稍后/不再提示写 `eh-onboarding-llm-dismissed=1`；mock 模式不显示，后端异常静默。
- 数据层：`types.ts` 增 Score/Suggestion 类型；`adapters.ts` 增 `normalizeScores`/`normalizeSuggestions`；`client.ts` 增 `fetchScores`/`fetchSuggestions`（mock 走 `mock.ts` 固定示例）；`queries.ts` 增 `useHealthScores`/`useHealthSuggestions`，404/网络错误不重试、由页面降级。
- 健康数据页空状态去掉重复按钮，只保留 PageHeader 的「导入健康数据」。
- i18n：`nav.dashboard` 改为「概览 / Overview」；新增 `dashboard.scores.*`、`dashboard.suggestions.*`、`dashboard.healthSummary.*`、`onboarding.llm.*`（zh-CN/en-US）。

## 验证
- `npm run build`：pass（tsc + vite，约 4.5s；仅有既有的 >500kB chunk 警告）。
- headless Chrome + CDP（1440×1000），真实后端 8765（`/scores` 返回 404）与 mock Vite（VITE_USE_MOCK=true）：
  - 有分数/缺项：总分 78，4 个分项，「缺数据：体重」；建议 2 条。
  - 无分数：评分卡「数据不足」、建议卡「暂时没有建议」，无红屏；console error 0、page error 0。
  - 健康数据摘要：mock 下显示 6,200 步 / 68 bpm / 7 小时 30 分 / 68.4 kg / 116/76 mmHg。
  - 建议点击：hash 变为 `#/assistant?prompt=…`；隔离后端 + Mock provider 下助手输入框已预填「观察我最近的睡眠数据，分析可以改善的点。」且未发送。
  - 首启弹窗：未配置时出现（标题「配置 AI Provider」）；「去配置」跳 `#/assistant?focus=provider`；点击后写 dismissed。
  - 健康数据空页：仅 PageHeader 一个「导入健康数据」，空状态无按钮，正文计数 0/0。
- 截图：`reports/screenshots/G1-dashboard-scores-light.png`、`G1-dashboard-scores-dark.png`、`G1-dashboard-noscores-light.png`、`G1-onboarding-light.png`、`G1-health-data-empty-light.png`。

## 未做 / 偏离
- `src/lib/nav.ts` 未改：首项路径与 labelKey 不变，改名仅靠 i18n，符合「路径不变」。
- 首启「去配置」目前只带 `?focus=provider`；助手页尚未消费该参数做滚动/聚焦（见跨区）。
- mock provider 的 `configured` 为 false，因此只配 Mock 时仍会弹首启提示；按契约「configured」判定。
- 未新增依赖；未改后端/助手/档案/branding。

## 跨区需求（需要别的 Agent 或指挥官处理）
- G2：运行中的 8765 尚无 `GET /api/v1/scores`、`/suggestions`（均 404），前端已降级；G2 合入后应自动出现真实评分。
- G3/G4：助手页已支持 `?prompt=` 预填（已实测）；尚未处理 `?focus=provider`，建议滚动并聚焦「模型提供商」区域。

## 需要指挥官决策
- 首启判定是否把「enabled 的 mock provider」视作已配置（当前不算，只有 configured 才算）。

## 建议下一批
- G2 合入后回归真实 `/scores` 五分项与总分；补一条无缺项状态的视觉回归。
- 将临时 CDP 截图脚本入库为 `scripts/` 复用工具（本轮未创建无关文件）。
