# A1 · 平台 v2 契约 + 贡献注册表 + loader 骨架（关键路径）

> 先读 `prompts/00-COMMON.md`，再读本文件。项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 目标

把第三方模块的 `contributes` 从「manifest 里保留的任意 JSON」升级为**可校验、可查询、可被后续 UI/工具消费的契约**。本任务只做契约 + 注册表 + 只读 API，不做渲染、不执行模块。

## 交付

### 1. 契约文档 `docs/MODULE_CONTRACT_V2.md`（先写，其他 Agent 会参考）

必须包含：

- `contributes.ui.widgets[]` 的稳定形状：
  ```json
  {"id":"weight-trend","title":"体重趋势","description":"","size":"sm|md|lg",
   "dataSource":{"type":"module-rpc","method":"stats","params":{}},
   "view":{"type":"stat|sparkline|list|progress|text","unit":"kg","valuePath":"latest.weight"}}
  ```
  只允许受控组件；禁止任意 React/CSS/iframe。
- `contributes.ui.pages[]` 的稳定形状：`{id,title,icon?,layout:[{component:"form|table|detail|list|text", ...}]}`，声明式、无脚本。
- `contributes.tools[]`：`{id,name,description,parameters(JSON Schema),permissions?}`，工具只能通过模块 RPC 执行。
- `contributes.recordTypes[]`：沿用 v1，补模块数据归属规则。
- 每个贡献的权限要求：声明式 UI 不需要 `ui:custom`；`tools` 需要 `llm`；数据访问仍由 `records:*` 在 RPC 时校验。
- 至少 2 个完整示例（一个 dashboard-widget，一个 ai-tool）。

### 2. JSON Schema

- 修改 `schemas/module.schema.json`：把 `ui.widgets/pages` 从 `{"type":"object"}` 收紧为带 `required` 的受控结构；`tool` 已有定义，补齐与文档一致的约束。
- 保持向后兼容：已有 Cardia/demo 模块 manifest 必须继续通过校验；如果旧模块没有这些字段，不受影响。
- 增加 schema 测试：合法示例通过、缺字段/未知 view type/超长字符串被拒绝。

### 3. 后端贡献注册表

- 新建 `backend/src/eclipse_health_backend/modules/contributions.py`：
  - 扫描已安装且 **enabled** 的模块 manifest，聚合 `widgets/pages/tools/recordTypes`；
  - 每项带 `moduleId/moduleName/moduleVersion`；
  - `tools` 仅当模块已授予 `llm` 权限时出现；`widgets/pages` 仅在模块 enabled 时出现；
  - 不启动 worker、不调用 RPC。
- `GET /api/v1/modules/contributions?type=widgets|pages|tools|recordTypes` → `{items:[...]}`；无 type 返回四类分组。
- 测试：enabled/disabled 过滤、权限过滤、聚合字段、空模块。

## 文件所有权（只改这些）

- `docs/MODULE_CONTRACT_V2.md`（新建）
- `schemas/module.schema.json`
- `backend/src/eclipse_health_backend/modules/contributions.py`（新建）
- `backend/src/eclipse_health_backend/modules/api.py`（只加 contributions 路由）
- `backend/tests/modules/test_contributions*.py`（新建）
- `backend/tests/fixtures/modules/contributions/**`（只加本任务 fixture）

## 明确不做

- 不写前端渲染器、不改 `src/**`。
- 不执行模块 RPC、不改 `host.py`/`manager.py` 的 records 回调（A2 所有权）。
- 不实现 ONNX loader（A3 所有权）。
- 不改 `docs/MODULE_CONTRACT_V1.md`、`prompts/`、`uploads/`；不新增依赖；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q
```

报告 `reports/A1-platform-contract-report.md`，≤80 行。必须写清：契约字段、兼容性验证、API 形状、测试输出、未做项。
