# B5 · LLM 真实 provider 联调（DeepSeek / OpenCode Go）

> 先读 `prompts/00-COMMON.md`、`reports/B4-08-report.md`、`backend/src/eclipse_health_backend/llm/providers.py`，再读本文件。
> 用户已授权使用 CC Switch 中的 OpenCode Go / DeepSeek 官方 API 做测试。

## 凭据规则（重要）

- **不要**扫描/读取 `~/.cc-switch/cc-switch.db`、不要导出或打印任何 key/token。
- 优先复用当前进程已有环境变量（不打印值）：
  - `ANTHROPIC_BASE_URL`（本机 CC Switch 代理，通常 `http://127.0.0.1:15721`）
  - `ANTHROPIC_AUTH`
  - 可选 `DEEPSEEK_API_KEY` / `OPENCODE_API_KEY`
- 测试用环境变量前缀隔离：`EH_TEST_ANTHROPIC_BASE_URL`、`EH_TEST_ANTHROPIC_API_KEY`、`EH_TEST_ANTHROPIC_MODEL`；缺省时从上面的现有变量映射，仍缺就 skip 并在报告写「缺凭据」，**不要硬编码**。
- 日志/报告只写 provider 类型、模型名、状态码、延迟；不写 key、请求体、完整响应。

## 目标

把 B4-08 未完成的「真实外部 provider」补齐：至少跑通一个 Anthropic 兼容代理（CC Switch → DeepSeek/OpenCode），验证流式、工具调用、用量、错误映射；若 DeepSeek 官方 key 可用，再补一个 OpenAI 兼容直连。

## 交付

### 1. Provider 配置健壮性

- `llm/providers.py`：
  - 确认 Anthropic/OpenAI 兼容 provider 支持自定义 `baseUrl`、`apiKey`、`model`；
  - 对代理返回的非标准 usage/错误结构做容错；
  - 401/403/404/408/422/429/5xx/连接失败映射与 B4-08 一致；
  - 不把 baseUrl 里的凭据写日志。
- 如代理只支持 Anthropic Messages 格式，明确记录；不要为此改协议。

### 2. 真实联调测试

- 新建 `backend/tests/assistant/test_live_providers.py`，`@pytest.mark.slow` + 环境变量开关（如 `EH_TEST_LIVE_LLM=1`），默认 skip：
  - 非流式一轮：`/assistant` 或直接 adapter 调用，断言 `completed`、usage 来源、延迟；
  - 流式一轮：首 token 时间、done 事件、usage；
  - 工具调用一轮（若模型支持）：`list_records`，断言工具名/结果引用/非诊断声明；
  - 错误路径：故意错 key/错 baseUrl → 401/连接失败映射，文本不含 key；
  - 取消：流式中取消，状态 `cancelled`。
- 跑通后把真实命令、模型名、延迟、usage 写进报告；失败就写失败原因，不伪造。

### 3. 前端 provider 预设

- `src/features/assistant/provider-card.tsx`：增加「DeepSeek / OpenCode（兼容代理）」预设入口：
  - 字段：baseUrl、model、apiKey；不预填任何真实 key；
  - 说明「可填 CC Switch 代理地址；key 仅存本机」；
  - 测试按钮复用现有能力探测。
- 文案加到 `src/features/assistant/i18n.ts`（feature-local，zh-CN/en-US）。

### 4. 文档

- 新建 `docs/LLM_PROVIDERS.md`：各 provider 配置示例（DeepSeek 官方、OpenCode Go、Ollama、Anthropic 兼容代理）、模型建议、限制（工具调用/思考链/用量）、隐私说明。不要写真实 key。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/llm/providers.py`
- `backend/tests/assistant/test_live_providers.py`（新建）
- `src/features/assistant/provider-card.tsx`
- `src/features/assistant/i18n.ts`
- `docs/LLM_PROVIDERS.md`（新建）

## 明确不做

- 不改 `llm/tools.py`/`agent.py`（B2 所有权）、不改 assistant workspace/chat panel。
- 不做模块工具、widget、模块页、S2 导入。
- 不读取 CC Switch 数据库、不打印/提交 key；不新增依赖；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\assistant -q
# 有凭据时：
$env:EH_TEST_LIVE_LLM="1"; backend\.venv\Scripts\python.exe -m pytest backend\tests\assistant\test_live_providers.py -m slow -q
npm run build
```

报告 `reports/B5-llm-live-report.md`，≤80 行。必须写清：用了哪个 provider/模型/代理、真实延迟与 usage、工具调用是否支持、失败项、凭据来源（只写变量名）。
