# LLM Provider 配置与限制

> 适用于 eclipse health v3 助手（`backend/src/eclipse_health_backend/llm/`）。
> 全部配置只保存在本机；本文不包含任何真实 Key。

## 1. Provider 类型

| kind | 协议 | 典型用途 | 需要 Key |
|---|---|---|---|
| `mock` | 进程内确定性回复 | 无网络演示、测试 | 否 |
| `ollama` | Ollama `/api/chat` | 本地模型（qwen3 等） | 否 |
| `openai` | OpenAI Chat Completions（经 LiteLLM） | DeepSeek / OpenRouter / 自建网关 | 是 |
| `anthropic` | Anthropic Messages（经 LiteLLM） | Anthropic 官方、DeepSeek Anthropic 兼容端点、CC Switch 等本地代理 | 是 |

`anthropic` 与 `openai` 都支持自定义 `baseUrl` 和 `model`，因此也能接任何同协议网关。
`baseUrl` 必须是 `http(s)` 地址，且不允许内嵌用户名/密码、查询串或 `#` 片段（防止 Key 随配置回显）。

## 2. 常用配置对照

| 服务 | kind | baseUrl | 模型示例 |
|---|---|---|---|
| 本地 Ollama | `ollama` | `http://127.0.0.1:11434` | `qwen3:4b`、`qwen3.5:9b` |
| DeepSeek 官方（Anthropic 兼容） | `anthropic` | `https://api.deepseek.com/anthropic` | `deepseek-chat`、`deepseek-reasoner` |
| DeepSeek 官方（OpenAI 兼容） | `openai` | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenCode Go（经 CC Switch 本地代理） | `anthropic` | `http://127.0.0.1:15721` | 以代理实际暴露的模型名为准 |
| 其他 Anthropic 兼容网关 | `anthropic` | 网关地址 | 网关文档中的模型名 |

> **模型名以网关为准。** 代理通常只接受它自己配置的模型 ID；把官方模型名填到代理上会得到 400/404。
> CC Switch 的 Anthropic 入口使用 `ANTHROPIC_DEFAULT_*_MODEL` 中的名字（本机实测该名字会被转发为上游模型）；
> 令牌填 CC Switch 设置的 `ANTHROPIC_AUTH_TOKEN`，本地代理不校验时任意占位值也可通过。

## 3. UI 配置

1. 打开「助手 → 模型提供商」。
2. 点击「代理预设（DeepSeek / OpenCode）」或「添加提供商」。
3. 填写名称、模型、接口地址与 API Key；Key 保存后只显示「已配置」。
4. 点击「测试连接」：执行一次短请求，返回延迟、模型可用性与工具能力，不显示 Key。

预设只预填 `http://127.0.0.1:15721` 与占位模型名 `deepseek-chat`，不会预填任何真实 Key。

## 4. API 示例

```bash
curl -X PUT http://127.0.0.1:8765/api/v1/assistant/providers/llm_deepseek \
  -H "content-type: application/json" \
  -d '{
    "kind": "anthropic",
    "label": "DeepSeek",
    "model": "deepseek-chat",
    "baseUrl": "https://api.deepseek.com/anthropic",
    "apiKey": "<你的 Key>"
  }'
```

`apiKey` 为空或不传表示保持原有 Key；`clearKey: true` 表示清除。

## 5. 实测记录（2026-10-30）

环境：CC Switch 本地代理（Anthropic Messages）→ 上游 `deepseek-v4.1-flash`，模型名为代理暴露的名称。

| 场景 | 结果 |
|---|---|
| 测试连接（非流式 ping） | ok，2.8 s，`supportsTools=true` |
| 非流式一轮 | 3.6 s，usage 35 / 40 tokens |
| 流式一轮 | 首 token 3.1 s，总 3.4 s；流内无 usage |
| 工具调用（`list_records`） | 可用，参数 `{"limit":5}` |
| 完整助手一轮（含 1 次工具） | 6.3 s，引用记录 ID，含「不构成医学诊断」 |
| 错误 Key | 本地代理不校验 Key，无法实测 401；错误映射由单元测试覆盖 |
| 错误 baseUrl | 映射为可读 provider 错误，文本不含 Key |

> V4.1 起，固定免责尾注已移除：免责声明由界面统一展示，回答不再每轮重复。
> 上表为 V4 时期的实测记录，保留原样。

Ollama 实测见 `reports/B4-08-report.md`。

## 6. 限制

- **用量**：Ollama 返回 `prompt_eval_count/eval_count`；OpenAI 兼容流已开启
  `stream_options.include_usage`；Anthropic Messages 流把 usage 放在 `message_delta`，
  当前 LiteLLM 版本会丢弃，因此该路流式轮次的 `done.usage` 为空、界面不显示 tokens。
  非流式调用有完整 usage。不用估算值冒充真实用量。
- **思考链**：Anthropic 兼容流的 `thinking` 块会被忽略，不展示给用户；但它计入输出
  token 并拉长首 token 时间（本机约 3 s）。需要更快时可换非推理模型。
- **工具调用**：取决于模型与网关。实测 DeepSeek 经代理可用；Ollama 的 `qwen3:4b`
  在关闭 think 后不再调用工具，因此不默认关闭。
- **错误映射**：401/403/404/408/422/429/5xx 映射为可读文本，只含 provider 类型与状态码。
  部分网关把连接失败包装成 HTTP 500，界面会显示 server error，需结合网关日志排查。
- **超时**：单请求 45 s，整轮 90 s；本地 9B 模型首次加载可能接近上限。
- **离线首轮**：LiteLLM 导入时默认联网拉取模型价格表，离线环境会拖慢首次调用（可达数十秒）。
  部署/测试可设置 `LITELLM_LOCAL_MODEL_COST_MAP=True` 使用本地表。
- **LiteLLM 版本差异**：不同版本对 Anthropic 流式 usage、思考块与错误码的归一化不同；
  升级依赖后建议重跑 `backend\tests\assistant\test_live_providers.py`。

## 7. 隐私

- Key 经 Windows DPAPI 加密后存放于 `<数据目录>/secrets/providers.json`，接口只返回「是否已配置」。
- 发送给模型的内容：系统提示、工具定义、最近 20 条对话、当前上下文切片
  （记录摘要、最新分析摘要、测量值；备注默认不发送）。
- 不发送：波形原始样本、逐搏数据、成员姓名、工具完整返回值。
- 不记录：请求体、完整响应、Key。日志只有 provider 类型、模型名、HTTP 状态与延迟。
- 本地 provider（Ollama / Mock）不出网。使用代理或官方 API 时，上述内容会到达该服务，
  请按自己的隐私要求选择 provider。
- 会话导出默认脱敏（不含工具原始返回、波形、逐搏、备注与成员姓名）。
