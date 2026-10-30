# 报告 · B5 LLM 真实 provider 联调（74-llm-live）

状态：完成（Anthropic 兼容代理已真实联调；OpenAI 兼容直连缺凭据未测）

## 交付

- `llm/providers.py`：`baseUrl` 额外拒绝查询串/片段（防止 `?api_key=` 随 provider 列表回显），
  其余（自定义 baseUrl/model/apiKey、DPAPI 存储、只回显 `configured`）复核无需改动。
- `api/assistant.py`（偏离，1 行）：`_test_litellm` 原来只给 `openai` 传 `api_base`，
  导致「测试连接」永远打官方 Anthropic 端点；改为所有带 `baseUrl` 的 provider 都传，
  否则新增的代理预设无法自检。
- `backend/tests/assistant/test_live_providers.py`（新建）：8 个 `slow` 用例 + 1 个常规用例，
  `EH_TEST_LIVE_LLM=1` 才跑；凭据缺失 skip，不硬编码、不打印。
- `src/features/assistant/provider-card.tsx`：新增「DeepSeek / OpenCode（兼容代理）」预设
  （标题栏短入口 + 空状态入口），预填 `http://127.0.0.1:15721` 与 `deepseek-chat`，不预填 Key，
  测试连接复用现有能力探测。
- `src/features/assistant/i18n.ts`：`proxyQuick` / `proxyQuickShort` / `proxyHint`（zh-CN + en-US）。
- `docs/LLM_PROVIDERS.md`（新建）：四类 provider 配置示例、模型建议、限制与隐私说明。

## 验证

- `ruff check backend` → All checks passed。
- `pytest backend\tests\assistant` → **59 passed, 11 skipped**（8 个 live + 3 个 Ollama 默认跳过）。
- `EH_TEST_LIVE_LLM=1` + `test_live_providers.py -m slow` → **8 passed**（真实调用，耗时约 1 分钟）。
- `npm run build` → pass（tsc 0 error；主包 620.52 kB / gzip 199.30 kB，>500kB 提示沿用基线）。
- 真实联调（`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `EH_TEST_ANTHROPIC_MODEL`，
  模型名 `claude-opus-5[1M]`，上游回显 `deepseek-v4.1-flash`）：
  - 测试连接：ok，`latencyMs=2790`，`supportsTools=true`。
  - 非流式：3.62 s，usage 35 / 40 tokens，`total=75`。
  - 流式：首 token 3.13 s，总 3.39 s，文本正常；**usage=None**（见限制）。
  - 工具调用：`list_records`，参数 `{"limit":5}`。
  - 完整助手一轮（1 次工具）：6.31 s，SSE 顺序 `start→tool_call→tool_result→citation→token…→done`，
    引用记录 ID，含「不构成医学诊断」，落库 `completed`。
  - 取消：流式中取消后落库 `cancelled`，`done.cancelled=true`。
  - 401：本地模拟 Anthropic 网关返回 401 → `anthropic_auth_error`，文本含 HTTP 401、不含 Key。
  - 错误 baseUrl：错误被脱敏，文本不含 Key 与地址。
- 凭据来源（只写变量名）：`ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`EH_TEST_ANTHROPIC_MODEL`。

## 未做 / 偏离

- 改了 `api/assistant.py`（不在本任务所有权列表）：不修则代理预设的「测试连接」必然失败；
  若与其它批次冲突，保留 `kwargs["api_base"] = provider.base_url` 这一行即可。
- OpenAI 兼容直连未测：`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` 均未设置；CC Switch 的
  `/chat/completions` 入口使用另一套凭据（实测 401），未复用 Anthropic 令牌硬凑。
- Anthropic 流式 usage 为空：代理在 `message_delta` 给了 usage，但当前 LiteLLM 版本丢弃；
  修复点在 `llm/agent.py`（B2 所有权），本批未动。
- 错误 baseUrl 被 LiteLLM 包装成 `InternalServerError(status=500)`，映射为 `*_server_error`
  而不是 `*_network_error`；同样需要改 `agent._sanitize`。
- 未做 UI 截图（时间原因）：本次 UI 改动仅新增按钮与提示，已过 `tsc`/构建；建议下一批补
  亮/暗各一张 provider 预设截图。

## 跨区需求（需要别的 Agent 或指挥官处理）

- `llm/agent.py::_sanitize`：识别异常链里的 `httpx.ConnectError`，把 LiteLLM 的 500 包装
  归类为 `*_network_error`。
- `llm/agent.py::LiteLLMAdapter`：Anthropic 流可从最终 chunk 的 provider 元数据/`message_delta`
  补 usage；否则界面 tokens 永远为空。
- 启动时设置 `LITELLM_LOCAL_MODEL_COST_MAP=True`：LiteLLM 导入时默认联网拉价格表，
  离线/断网首轮可达 60 s，与「本地优先」冲突。

## 需要指挥官决策

- 流式无 usage：接受「不显示 tokens」，还是在缺失时用估算值并明确标注 `estimate`。
- 是否默认关闭思考链（更快，但部分模型关闭后不调用工具）。
- 是否把「代理预设」提升为默认入口（当前是次级按钮）。

## 建议下一批

- 拿到 DeepSeek 官方 Key 后补 OpenAI 兼容直连、429 限流与断流重试实测。
- provider 卡片 UI 走查与截图；把 Ollama/代理模型建议写进设置页文案。
