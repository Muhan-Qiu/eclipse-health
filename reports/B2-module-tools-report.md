# 报告 · B2 平台 #3 模块工具注册表 → 助手工具
状态：完成

## 交付
- `llm/tools.py`：新增模块工具目录 `module_tool_catalog()` / `ModuleTool` / `module_tool_alias()`；`ToolBox.tool_specs()` 返回内置 + 动态模块工具，`ToolBox.execute()` 识别命名空间工具并走 `manager.call()`。
- `llm/agent.py`：工具表改为每轮 `toolbox.tool_specs()`（内置行为不变）；模块工具放到线程执行；系统提示新增第 6 条（`m_` 前缀为第三方模块工具，仅供参考）。
- `tests/assistant/test_module_tools.py`（新建，8 个用例）+ `tests/fixtures/modules/tools/`（manifest + stdio worker）。
- `src/features/assistant/tool-trace.tsx`：模块工具显示「模块名 Badge · 工具名」。

## 命名规则
- 别名 = `m_<fnv1a32(moduleId) 8 位十六进制>_<tool_id 白名单化>`：非 `[A-Za-z0-9_-]` 字符替换为 `_`，去首尾 `_`，截断 53 字符；总长 ≤64。
- 纯函数、无安装状态缓存；前端用同一 10 行 FNV-1a 复算（已用 Node 与 Python 双向比对，示例 `m_98030f40_echo_text` 一致）。
- 短哈希撞名时跳过后者并记 warning，不让模型调用到另一个模块。
- 展示名 `moduleName · toolName` 保留在 `ModuleTool.display_name`，用于透明面板摘要。

## 权限过滤（双重）
1. 注册阶段：`collect_contributions(kind="tools")` 只返回 enabled 且已授予 `llm` 的模块工具。
2. 执行阶段：`_find_module_tool()` 每次重新读注册表，撤销授权/禁用/卸载后立刻返回 `UNKNOWN_TOOL`；不在两次请求之间缓存安装状态。

## Schema 与结果
- 参数取模块 `inputSchema`（`parameters` 由 A1 归一），递归强制 `additionalProperties:false`；顶层非 object 时退回空对象参数。
- 返回值先按字段脱敏（`samples/signal(s)/waveform/notes/memberName/displayName/beats`，字符串 ≤2000、数组 ≤200、深度 ≤8），再按 `MAX_TOOL_RESULT_JSON`=12000 字节截断为 `{truncated, bytes, preview}`。

## 错误映射
- 模块未运行 / `MODULE_TIMEOUT` / `MODULE_ERROR` / 其它异常 → 统一 `TOOL_FAILED`，message 固定为 `module tool execution failed`，模块内部原文（如 `boom: internal detail 42`）不出现在结果或前端。
- 未知别名 / 已失效工具 → `UNKNOWN_TOOL`。内置工具错误路径保持不变。
- 审计沿用 `manager.call()` 既有的 `rpc.call` 记录，未重复写。

## 验证（真实输出）
- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `... -m pytest backend\tests\assistant backend\tests\modules` → `185 passed, 3 skipped in 12.53s`
- `... -m pytest backend\tests\assistant\test_module_tools.py` → `8 passed`
- `... -m pytest backend\tests`（全量回归）→ 全绿，exit=0
- `npm run build`（含 `tsc`）→ `✓ built in 2.60s`，仅既有的 >500kB chunk 提示

## 未做 / 偏离
- **前端映射方式**：`tool_call`/`tool_result` 事件无法携带 `moduleName`（`assistant-workspace.tsx`、`types.ts` 不在本批所有权内），因此 `tool-trace.tsx` 自己拉一次 `/api/v1/modules/contributions?type=tools` 并按同一别名规则建表；失败/离线时优雅退回显示原始别名。事件通道补 `displayName` 建议列入 B5。
- 未改 `modules/**`、`schemas/**`、`providers.py`、`assistant-workspace.tsx`、`chat-panel.tsx`、`assistant/i18n.ts`、docs/prompts/uploads；未新增依赖；未 commit。
- 无 UI 截图：本次前端改动是工具面板的徽标，不新增页面/主题状态；如需可补两张。

## 跨区需求（需要别的 Agent 或指挥官处理）
- B5 若改 `assistant-workspace.tsx` 的事件归并，可把 `tool_call.data.displayName` 直接带进 `ToolCallTrace`，届时 `tool-trace.tsx` 可去掉自取贡献表的兜底。
- 前端拉取贡献表的请求会随 UI 打开触发一次；若后续有统一的数据层缓存，可迁移到 `useAssistantData`。

## 需要指挥官决策
- 模块工具是否应把当前成员 `memberId` 作为隐式参数传给模块（当前严格按模块声明的 schema，不注入任何核心上下文）。

## 建议下一批
- `widgets`/`pages` 渲染（70/72）沿用同一份贡献注册表读法；可考虑在 `src/lib/api` 增加 `contributions` 客户端，避免各模块页各自 fetch。
