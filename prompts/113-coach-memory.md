# G4 · 教练（Coach）+ 天气 + 记忆注入 + 助手预设

> 先读 `prompts/00-COMMON.md`、`src/features/assistant/**`、`backend/src/eclipse_health_backend/llm/agent.py`、`reports/B4-08-report.md`。
> **思考强度：low。** 不重写助手，只加模式/上下文/预设。

## 交付

### 1. 后端教练上下文

- 新建 `backend/src/eclipse_health_backend/coach/`：
  - `context.py`：汇总评分（G2 `scoring.service`）、最近健康数据摘要（步数/心率/睡眠/体重/血压）、最近运动记录（G3）、记忆（G3 `memory.memory_context()`）；任何一项缺失就跳过，不报错。**用 try/except ImportError 或延迟导入**，G2/G3 未完成时也能独立启动。
  - `weather.py`：Open-Meteo 免费接口（无需 key）：
    - 城市 → 经纬度：`https://geocoding-api.open-meteo.com/v1/search?name=<city>&count=1&language=zh`
    - 天气：`https://api.open-meteo.com/v1/forecast?latitude=&longitude=&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode&timezone=auto&forecast_days=3`
    - 30 分钟内存缓存；失败返回 null，不影响教练回答。
  - `api.py`：`GET /api/v1/coach/context?city=`、`GET /api/v1/coach/weather?city=`（只读）。
  - `router` 新建，但**不要改 `api/__init__.py`**（指挥官统一挂载）；测试可直接 include router。
- `llm/agent.py`：系统提示增加「教练模式」：
  - 当请求带 `mode="coach"`（SSE/请求体）时，注入：评分摘要、健康数据摘要、运动记录、记忆、天气（若有）；
  - 记忆只来自 `memory_context()`，`enabled=false` 不注入；不把记忆写日志；
  - 明确非诊断、建议渐进、遇到胸痛/晕厥等红旗症状建议就医；
  - 非 coach 模式保持现有行为。
- 助手请求模型/接口增加可选 `mode` 字段（不破坏默认）。

### 2. 前端教练

- `src/features/assistant/**`：
  - 助手页增加「教练 Coach」切换/入口；进入教练模式显示：
    - 预设 chips：`睡眠改善`、`心脏数据解读`、`运动计划`、`压力与呼吸`、`体重管理`；点击填入输入框（可编辑，不自动发送）；
    - 城市输入（可选，用于天气）；天气摘要小卡（若可用）；
    - 预设点击只填 prompt；用户自己按发送。
  - 支持从首页 `/assistant?prompt=...`（或 router state）预填；G1 会传 `prompt`。
  - 教练回答仍走现有消息流/工具追踪；不新增聊天协议。
- i18n `assistant.coach.*`（zh-CN/en-US）；只新增本任务键。

### 3. 测试

- 后端：memory 注入开关、评分/健康摘要缺失容错、天气解析 mock、coach 模式 system prompt 包含关键段、非 coach 不变。
- 前端 `npm run build`；CDP/Playwright：教练切换、5 个 chips 填词、首页 prompt 预填、天气不可用时不报错；截图 `reports/screenshots/G4-*.png`。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/coach/**`（新建）
- `backend/src/eclipse_health_backend/llm/agent.py`
- `backend/tests/coach/**`（新建）
- `src/features/assistant/**`
- `src/pages/assistant.tsx`
- `src/lib/i18n/**`（只新增 assistant.coach 键）
- `src/lib/api/**`（仅当助手请求需要透传 mode；优先用本地 fetch）
- `reports/G4-*.md`、`reports/screenshots/G4-*.png`

## 明确不做

- 不改 `api/__init__.py`（指挥官挂载）；不改评分/档案/记忆实现（G2/G3）。
- 不改 dashboard/health-data（G1）；不做自动发送、不做语音。
- 不新增依赖（httpx 已装）；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\coach -q
npm run build
```

报告 `reports/G4-coach-report.md`，≤80 行。
