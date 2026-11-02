# C1 · Stage C 集成 owner：契约补口 + 跨区修复 + 全量回归

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md`、`reports/B1`–`B5`，再读本文件。

## 目标

把 Stage B 留下的跨区小口子收掉，保证「安装模块 → 首页卡片 → 助手工具 → 模块页 → 卸载」在真实应用里连贯可用；不新增功能。

## 交付

### 1. 契约补口

- `schemas/module.schema.json`：
  - `ui.widgets[]` 增加可选 `link`（站内路径，`^/` 开头，禁止 `//`/协议/`..`）；与前端 B1 的容错一致。
  - `ui.pages[]` 的 table `columns[]` / detail `fields[]` / form `fields[]` 增加可选 `format: text|number|date|datetime`（与 B3 渲染器一致）。
  - 更新 `docs/MODULE_CONTRACT_V2.md` 字段表与示例；补 schema 测试（合法/非法 link、format）。
- 不破坏已有模块 manifest；`modules/official/cardia`、`demo.echo`、测试 fixture 继续通过。

### 2. 跨区修复

- `src/components/ui/progress.tsx`：把 `value` 传给 Radix Root，修复全站进度条 `aria-valuenow` 缺失；B1 的显式补丁可保留或移除（不重复）。
- `backend/src/eclipse_health_backend/llm/agent.py`：
  - `_sanitize` 识别异常链里的 `httpx.ConnectError`/连接失败，归类为 `*_network_error`，不要把 LiteLLM 包装的 500 当 server error；
  - LiteLLM Anthropic 流式：从最终 chunk / `message_delta` 补 usage；拿不到时保持 None，不伪造；
  - 不改变 B4-08 的错误文本脱敏规则。
- 启动时设置 `LITELLM_LOCAL_MODEL_COST_MAP=True`（在合适入口，如 `llm/providers.py` 导入前或 app 启动），避免离线首轮联网拉价格表。
- 前端模块状态刷新：确认安装/启用/禁用/卸载后，`["modules"]` 前缀会刷新 contributions、widgets、pages、tools；若 key 不一致，统一为 `["modules", "contributions", ...]` 前缀并在 `modules-workspace.tsx`/`module-detail.tsx` 触发失效。**不要**改 B1/B3 的渲染逻辑。

### 3. 集成测试

- 后端：补 `test_llm_error_mapping.py`（连接失败/500 包装）与 schema link/format 测试；现有全量测试全绿。
- 前端：`npm run build`；手工/Playwright 验证：
  - 安装一个带 widget/tool/page 的测试模块后，首页卡片、助手工具、模块页同时出现；
  - 禁用模块后三处同时消失；重新启用后恢复（无需重启应用）；
  - 卸载后不残留。
- 截图：模块启用前后首页/助手/模块页各一张，放 `reports/screenshots/C1-*.png`。

## 文件所有权（只改这些）

- `schemas/module.schema.json`
- `docs/MODULE_CONTRACT_V2.md`
- `src/components/ui/progress.tsx`
- `backend/src/eclipse_health_backend/llm/agent.py`
- `backend/src/eclipse_health_backend/llm/providers.py`（仅 cost map 开关）
- `backend/src/eclipse_health_backend/app.py`（仅启动设置）
- `src/features/modules/modules-workspace.tsx`、`src/features/modules/module-detail.tsx`（仅 query invalidation）
- `backend/tests/modules/test_contributions_contract.py`（只加 schema 用例）
- `backend/tests/assistant/test_llm_error_mapping.py`（新建）

## 明确不做

- 不改 `src/features/modules/widgets/**`、`pages/**`、`dashboard.tsx`、`records.tsx`、import 组件。
- 不做健康数据列表（C3）、E2E 报告（C2）、发布打包。
- 不新增依赖；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
npm run build
```

报告 `reports/C1-integration-report.md`，≤80 行。必须写清：schema 新增字段、跨区修复点、模块启停刷新验证、全量测试输出、未做项。
