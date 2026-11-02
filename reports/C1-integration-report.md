# 报告 · C1 Stage C 集成 owner（契约补口 + 跨区修复 + 全量回归）
状态：完成

## 交付
- `schemas/module.schema.json`：`ui.widgets[]` 新增可选 `link`（`$defs/internalLink`，`^/` 开头，拒绝 `//`、`://`、任意 `..`、反斜杠/空白，≤512）；`table.columns[]`、`detail.fields[]`、`form.fields[]` 新增可选 `format: text|number|date|datetime`（`$defs/valueFormat`）。均为增量字段，旧 manifest 不受影响。
- `docs/MODULE_CONTRACT_V2.md`：补 `link`（§2.3）、`format` 字段说明与示例，更新兼容性小节。
- `src/components/ui/progress.tsx`：`value` 传给 Radix Root，修复全站进度条 `aria-valuenow` 缺失；B1 在 widget 调用处的显式补丁保留（不在本批所有权内，值相同，不冲突）。
- `backend/.../llm/agent.py`：`_sanitize` 沿 `__cause__`/`__context__`/`original_exception`/`args` 识别 `httpx.ConnectError` 与 `APIConnectionError`，LiteLLM 包装的 500 归类为 `*_network_error`；错误文本规则未改。LiteLLM 流式 usage 改为从 chunk.usage / model_extra / _hidden_params / provider_specific_fields / delta 读取并合并 input/output tokens，取不到保持 None。
- `backend/.../llm/providers.py`：导入时设置 `LITELLM_LOCAL_MODEL_COST_MAP=True`，离线首轮不再联网拉价格表。
- `modules-workspace.tsx`：`refreshAll()` 显式失效 `["modules"]` 与 `["modules","contributions"]`（覆盖 widgets/pages/tools 与 page-contributions 子键）。`module-detail.tsx`：授权/撤销后额外失效 contributions 与 page-contributions。
- 测试：`test_contributions_contract.py` 新增 link/format 合法与非法用例；新建 `test_llm_error_mapping.py`（7 例：连接失败、500 包装、纯 500、超时、partial usage 合并、hidden_params usage、无 usage）。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `backend\.venv\Scripts\python.exe -m pytest backend\tests -q` → **594 passed, 11 skipped in 656.31s (0:10:56)**，exit 0；最终复跑 exit 0，`--collect-only` 复核 **605 tests collected**（594 + 11）。
- 定向：`test_contributions_contract.py` + `test_llm_error_mapping.py` → **47 passed**。
- `npm run build` → pass，`✓ 2846 modules transformed`，`✓ built in 2.44s`；仅既有 >500 kB chunk 提示。
- 集成验证（Playwright MCP 被其他会话占用，改用 headless Chrome CDP + 现有 Vite dev server + 隔离 `EH_DATA_DIR` 后端）：
  - 临时测试模块（widget + tool + page，`io.github.example.c1-demo`）安装并启动后，首页显示「C1 集成卡片 / 72 bpm」，模块页显示表格（`70.2 kg`、datetime/date 格式化正确），`/contributions?type=tools` 返回 `c1.ping`。
  - 模块页 → 模块页禁用 → `history.back()`：缓存页面不再显示旧数据，显示未启用；SPA 回首页卡片消失；助手页正常。全程未刷新/重启。
  - 重新启用 → 首页卡片恢复，无需重启。
  - 卸载 → 首页无卡片，直接访问模块页显示「模块未安装」，无残留数据。CDP 断言全部通过，`consoleErrors: []`。
  - 工具目录 API 复核：启用 `['c1.ping']` → 禁用 `[]` → 重新启用 `['c1.ping']`。
- 截图（`reports/screenshots/`）：`C1-home-enabled/disabled/uninstalled.png`、`C1-module-page-enabled/disabled/uninstalled.png`、`C1-modules-enabled.png`、`C1-assistant-enabled/disabled.png`。

## 未做 / 偏离
- 助手工具目录没有可见列表（B2 只做调用追踪），无法用截图证明「工具出现/消失」；改用 contributions API + 单元测试验证，工具调用链本身由 B2 测试覆盖。
- `link` 采用「禁止任意 `..` 子串」的严格规则（比仅禁止路径段更严），避免根路径 `/../x` 绕过；前端仍二次过滤。
- `format` 只是显示提示，不改变数据；form 字段的 `format` 渲染器目前只读不用（B3 既有行为未改）。
- 未改 `widget-view.tsx` 的显式 `aria-valuenow`（非本批所有权）；根因已在 `progress.tsx` 修复。
- 未新增依赖、未 commit/push、未改 prompts/uploads。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `src/features/assistant/tool-trace.tsx` 用模块级 `labelsPromise` 缓存工具标签，一次会话只拉一次；新装模块的工具调用能执行，但徽标可能到刷新页面前仍显示别名。建议后续改为 React Query（key 用 `["modules","contributions","tools"]`）并随安装/启用失效。
- `src/features/modules/pages/page-api.ts` 的 `PAGE_CONTRIBUTIONS_KEY` 与 `MODULE_CONTRIBUTIONS_KEY` 不同但同属 `["modules"]` 前缀，当前失效正常；如未来改前缀需同步。

## 需要指挥官决策
- 是否把 `tool-trace.tsx` 的标签缓存改造纳入下一批（单文件、低风险）。
- 是否允许 `link` 携带查询串/锚点（当前 schema 允许，仅拒绝空白/反斜杠/协议/`..`）。

## 建议下一批
- C2 E2E 复用本次临时模块与 CDP 断言；C3 健康数据页完成后补全链路截图。
