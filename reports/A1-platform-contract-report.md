# 报告 · A1 平台 v2 契约 + 贡献注册表 + loader 骨架
状态：完成

## 交付
- `docs/MODULE_CONTRACT_V2.md`：widgets/pages/tools/recordTypes 稳定形状、权限矩阵、注册表 API、两个完整 manifest 示例。
- `schemas/module.schema.json`：`ui.widgets/pages` 收紧为受控结构（新增 11 个 `$defs`）；`tool` 增加 `parameters` 别名与 `permissions`，禁止两者同设；`ui.commands/settings` 仍保留。
- `backend/.../modules/contributions.py`：扫描已安装且 enabled 的模块，聚合四类贡献并注入 `moduleId/moduleName/moduleVersion/moduleType`；不启动 worker、不调 RPC。
- `GET /api/v1/modules/contributions[?type=widgets|pages|tools|recordTypes]`：无 type 返回分组 + counts，未知 type 返回 422 `INVALID_INPUT`。
- 新测试 36 个：`test_contributions_contract.py`（schema）与 `test_contributions_registry.py`（注册表 + API）。

## 验证
- `python -m ruff check backend` → **4 errors，全部在 `analysis_service/onnx_engine.py`（A3 正在改的文件，跨区）**；A1 涉及的 4 个文件单独检查 → All checks passed。
- `pytest backend/tests/modules` → **127 passed in 9.18s**（0 失败）。
- `pytest backend/tests/modules/test_contributions_contract.py backend/tests/modules/test_contributions_registry.py` → **36 passed in 0.71s**。
- 文档中的两个完整示例已用 `parse_manifest` 实际校验通过（dashboard-widget / ai-tool）。
- 向后兼容：`modules/demo.echo`、`modules/official/cardia`、`schemas/examples/*.module.json` 全部继续通过；仓库内无旧形状 `ui.widgets` 模块。
- 边界覆盖：缺字段、未知 size/view、超长 title（121）、脚本字段、非法 valuePath、未知 dataSource、未知工具权限、inputSchema 与 parameters 同设，均被 schema 拒绝。

## 未做 / 偏离
- 计划写 `tools[].parameters`，但内核与 demo/示例既有字段是 `inputSchema`。v2 以 `inputSchema` 为规范名，`parameters` 作为等价别名（schema 限制二选一），注册表输出统一归一为 `inputSchema`。
- 「loader 骨架」在本任务内只指贡献注册表（从已安装 manifest 装载声明）；RPC 数据通道、widget/page 渲染器、工具执行均未做，留给 Stage B。
- 未改 `manager.py`/`host.py`（A2 所有权），未新增 fixture 目录（复用 `build_demo_package`）。
- 未新增依赖、未 commit。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `ruff check backend` 余下 4 条全在 `analysis_service/onnx_engine.py`（RUF100 ×2、RUF046 ×2），属 A3 所有权；A1 未改动该文件。
- A2 的 `test_host_data.py` 在联调中一度失败（records 表/Row 转换），复核时已 127 全绿，无需处理。

## 需要指挥官决策
- `ui.commands` / `ui.settings` 仍为 `{"type":"object"}`，是否在 Stage B 一并收紧。
- 是否要求 `ai-tool` 类型强制声明 `llm`：当前不强制（demo.echo 是反例），仅由注册表按授权过滤；强制会破坏现有 demo。
- v1 `ui.widgets`（任意 JSON）到 v2 受控结构属收紧型变更；如需兼容期，可在 v2.1 放宽 `additionalProperties`。

## 建议下一批
- Stage B 首页 widget 渲染器直接消费 `?type=widgets`；工具注册表消费 `?type=tools`（只读、已按 llm 过滤）。
- 模块页渲染器按 `?type=pages` 的 `layout` 块实现五种受控组件。
