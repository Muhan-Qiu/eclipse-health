# G1 · 首页「概览」重组 + 健康评分/建议 UI + 首启 LLM Key 引导

> 先读 `prompts/00-COMMON.md`、`docs/USER_FEEDBACK.md`（第三轮）、`src/pages/dashboard.tsx`、`src/pages/health-data.tsx`。
> **思考强度：low。** 不要过度设计，按契约实现。

## 用户要求

- 健康数据/评分/建议放首页顶部；ECG/分析内容往下移；导航第一项改名「概览」。
- 健康数据页没导入时，也要显示已有记录/指标；只留一个「导入健康数据」入口，下面显示已测数据。
- 首次打开提示配置 LLM Provider Key（应用内 Agent 用），可跳过。
- 评分：心脏/睡眠/体重/活动/血压；没有该项数据就不显示；总分=可用项平均。
- 建议一句话；点进去打开助手并带预置问题。

## 后端契约（G2 提供，前端按此对接）

- `GET /api/v1/scores` →
  ```json
  {"overall":78|null,"generatedAt":"...","categories":[
    {"id":"heart","label":"心脏","score":82,"grade":"excellent|good|fair|attention|unknown",
     "factors":["静息心率 62 bpm"],"missing":null,"evidenceCount":3}
  ],"missing":[{"id":"weight","reason":"缺少身高或体重"}]}
  ```
- `GET /api/v1/suggestions` → `{"items":[{"id":"sleep","text":"...","category":"sleep","severity":"info|attention","prompt":"观察我最近的睡眠数据，分析可以改善的点。"}]}`
- 后端不可用/404 时：评分/建议区域隐藏或显示轻量「数据不足」，不要红屏。

## 交付

### 1. 首页重排

- `src/pages/dashboard.tsx` 顺序：问候/名言 → **健康评分卡（HealthScoreGrid）** → **建议卡（SuggestionCard）** → 健康数据摘要（已有数据/指标）→ 原有引导/最近记录/指标/波形。
- 首次进入 stagger 保留，不重复播放；移动端单列。
- 评分卡：总分大数字 + 各分项小卡（颜色 + 文字等级，不只靠颜色）；缺失项不显示，底部一行「缺数据：体重、血压」。
- 建议卡：每页最多 2 条；点击「和教练聊聊」→ 跳转 `/assistant` 并带上 `prompt`（router state 或 query `?prompt=`），助手页读取后填入输入框（不自动发送）。
- 健康数据摘要：显示已有步数/心率/睡眠/体重/血压最新值（来自 `useHealthRecords`），无数据时显示「还没有健康数据」+ 一个「导入健康数据」按钮（复用 `useImport().openPicker`），不要多个导入入口。
- `src/lib/nav.ts`：第一项标签改「概览」（`nav.dashboard` 文案改「概览 / Overview」）；路径不变。

### 2. 首启 LLM Key 引导

- 新建 `src/features/onboarding/llm-key-prompt.tsx`：应用启动后检查是否已配置 LLM provider：
  - 调现有 assistant provider 列表接口（参考 `src/features/assistant/provider-card.tsx` / `api.ts`）；
  - 未配置且未跳过（`localStorage["eh-onboarding-llm-dismissed"]`）→ 显示非阻塞 Dialog：「配置 AI Provider，才能使用评分建议/教练」；
  - 按钮：去配置（跳 `/assistant` 并聚焦 provider 区）、稍后（写 dismissed）、不再提示（写 dismissed）。
  - 已配置不显示；mock 模式不显示。
- 在 `src/App.tsx` 挂载；不阻塞主界面。

### 3. 数据层

- `src/lib/api/{types,queries,client,adapters,mock}.ts`：scores/suggestions 类型与查询；mock 返回固定示例；404/网络错误优雅降级。
- i18n：`dashboard.scores.*`、`dashboard.suggestions.*`、`onboarding.llm.*`、`nav.dashboard`（概览），zh-CN/en-US。

### 4. 验证

- `npm run build` 通过。
- Playwright/CDP：有分数/无分数/缺项三种状态；建议点击带 prompt 到助手；首启弹窗出现/跳过/不再提示；健康数据页空状态只有一个导入按钮。
- 亮/暗截图 `reports/screenshots/G1-*.png`；控制台 0 error。

## 文件所有权（只改这些）

- `src/pages/dashboard.tsx`、`src/pages/health-data.tsx`
- `src/lib/nav.ts`
- `src/App.tsx`
- `src/features/scores/**`（新建）
- `src/features/onboarding/**`（新建）
- `src/lib/api/{types,queries,client,adapters,mock}.ts`
- `src/lib/i18n/**`（只新增本任务键）
- `reports/G1-*.md`、`reports/screenshots/G1-*.png`

## 明确不做

- 不改后端评分逻辑（G2）、不改 profile/assistant 页面（G3/G4）、不改 branding/themes。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 报告

`reports/G1-home-scores-report.md`，≤80 行。
