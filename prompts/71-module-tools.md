# B2 · 平台 #3：模块工具注册表 → 助手工具

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md` 的 `tools` 段、`backend/src/eclipse_health_backend/llm/tools.py`，再读本文件。

## 目标

让已安装且授予 `llm` 权限的 `ai-tool` 模块，把 `contributes.tools[]` 自动注册成助手可调用的工具；执行走模块 RPC，结果进透明面板。核心内置工具保持不变。

## 交付

### 1. 后端工具注册

- `llm/tools.py`：
  - 在 `TOOL_SPECS` 基础上动态追加模块工具（每次构建工具表时读取 `modules.contributions`，不缓存跨请求的安装状态）；
  - 工具名加命名空间，避免与内置冲突：`m_<moduleId 短哈希>_<toolId>`；同时保留展示名 `moduleName · toolName`；
  - 参数 schema 用模块 `inputSchema`（A1 已归一），强制 `additionalProperties:false`；
  - 只注册模块 enabled 且已授予 `llm` 权限的工具（注册表已过滤，再校验一次）。
- 执行：
  - 识别命名空间工具 → `manager.call(moduleId, toolId, args)`；
  - 结果裁剪到 `MAX_TOOL_RESULT_JSON`，不含波形/备注/成员姓名；
  - 模块未运行/超时/错误 → 统一 `TOOL_FAILED`，不把模块内部错误原文透给模型；
  - 写审计（RPC 已有审计，不重复）。
- `llm/agent.py`：工具表来源改为动态函数（保持内置行为）；系统提示里说明模块工具由第三方提供、结果仅供参考。
- 测试 `backend/tests/assistant/test_module_tools.py`（新建）：
  - 未授权 `llm` → 不出现；
  - 授权后出现且 schema 正确；
  - 执行成功返回裁剪结果；
  - 未知工具/模块错误/超时映射；
  - 内置工具不受影响（现有 assistant 测试全绿）。

### 2. 前端透明面板

- `src/features/assistant/tool-trace.tsx`：模块工具显示「模块名 · 工具名」+ 来源徽标；不新增 i18n 共享键，模块名/工具名来自后端。
- 不显示模块返回的原始大 JSON；沿用现有摘要。

### 3. 测试模块

- 用 `backend/tests/fixtures/modules/host/` 或新建 `fixtures/modules/tools/` 下的 ai-tool 测试模块（manifest + worker），在测试中安装/授权/调用；不要提交真实第三方代码。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/llm/tools.py`
- `backend/src/eclipse_health_backend/llm/agent.py`
- `backend/tests/assistant/test_module_tools.py`（新建）
- `backend/tests/fixtures/modules/tools/**`（新建）
- `src/features/assistant/tool-trace.tsx`

## 明确不做

- 不改 `modules/**`（A1/A2 已完成）、不改 `schemas/**`、不改 `providers.py`（B5 所有权）。
- 不改 `assistant-workspace.tsx`/`chat-panel.tsx`/`assistant/i18n.ts`（B5 会改 provider 卡片与 i18n）。
- 不做模块页/widget/S2；不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\assistant backend\tests\modules -q
npm run build
```

报告 `reports/B2-module-tools-report.md`，≤80 行。必须写清：命名规则、权限过滤、错误映射、真实测试输出、未做项。
