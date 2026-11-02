# A7 · 多服务商预设（类似 CC Switch）

日期：2026-11-01
范围：LLM 服务商接入层、设置页服务商网格、预设 API 与测试。

## 结论

已完成。用户现在只需「选服务商 → 填 API Key（可选模型）」即可保存，不需要自己查 base URL。
35 个预设覆盖国内外主流服务商，并保留「自定义 OpenAI 兼容」与「CC Switch 代理」。
旧 `providers.json` 无需迁移即可加载；API Key 仍只走 Windows DPAPI，绝不落明文、不写日志。

## 改动文件

### 后端

- `backend/src/eclipse_health_backend/llm/provider_presets.py`（新增）
  - 预设数据：`id / label / labelEn / kind / litellmProvider / baseUrl / defaultModel / models /
    needsKey / keyUrl / docsUrl / description / group / requiresBaseUrl / local / custom`
  - `LITELLM_PROVIDERS` 白名单、`get_preset()`、`list_presets()`
  - `baseUrl = null` 表示交给 LiteLLM / 云 SDK 解析默认端点（Gemini、Bedrock、Vertex、Azure）
- `backend/src/eclipse_health_backend/llm/providers.py`
  - `Provider` 新增 `preset_id`、`litellm_provider`、`needs_key_value`、`local_value`
  - 新增 `litellm_model`（`<provider>/<model>`）、`error_kind` 属性
  - 旧记录缺字段时：`litellmProvider = kind`，`needsKey = kind in {openai, anthropic}`，
    `local = kind in {ollama, mock}`
  - 保存时校验预设存在、预设 kind 不可被改写、`litellmProvider` 必须在白名单内、
    `requiresBaseUrl` 的预设必须提供地址
  - base URL 默认值改为「预设优先」，避免 DeepSeek 等 kind=openai 的预设被错误回退到 OpenAI 地址
- `backend/src/eclipse_health_backend/llm/agent.py`
  - `LiteLLMAdapter` 使用 `provider.litellm_model`
  - 错误脱敏使用 `provider.error_kind`（DeepSeek 报错会显示 `deepseek ...`，而不是 `openai ...`）
  - `stream_options.include_usage` 只对 `litellmProvider == "openai"` 发送，保持原有 OpenAI 行为
  - 透明面板 `localOnly` 使用 `provider.is_local`
- `backend/src/eclipse_health_backend/api/assistant.py`
  - 新增 `GET /api/v1/assistant/provider-presets`
  - `ProviderIn` 接受 `presetId / litellmProvider / needsKey / local`
  - 测试连接与工具能力探测改用 `litellm_model`
- `backend/tests/assistant/test_provider_presets.py`（新增，12 个用例 + 22 个前缀参数化用例）

### 前端

- `src/features/assistant/types.ts`：`AssistantProvider` 增加 `presetId / litellmProvider / needsKey`；
  新增 `ProviderPreset`、`ProviderPresetGroup`
- `src/features/assistant/api.ts`：新增 `assistantApi.providers.presets()`
- `src/features/assistant/provider-card.tsx`：重写设置页服务商区域
  - 服务商网格 + 搜索 + 分组（国际官方 / 国内 / 聚合与网关 / 本地 / 自定义 / 演示）
  - 选中后默认只显示 API Key、模型（带快捷模型标签）；base URL / 名称 / 启用状态折叠在「高级设置」
  - 需要 Key 时显示官方申请链接；缺少 Key、缺少必填 base URL 都有就地提示
  - 保存后出现「测试连接」；旧 provider（无 presetId）继续使用原表单
- `src/features/assistant/i18n.ts`：新增中英文分组、搜索、高级设置、申请 Key 等文案

## 已核实并接入的 provider

核实方式：当前环境 LiteLLM **1.106.5** 的本地 `LlmProviders` / `get_llm_provider` 行为，
以及 Context7 上 LiteLLM 官方文档的 provider 页面。脚本对 22 个 `litellmProvider`
逐个调用 `get_llm_provider("<prefix>/<model>")`，全部返回同一前缀。

| 预设 | LiteLLM 前缀 | 默认端点 | 说明 |
|---|---|---|---|
| OpenAI | `openai` | `https://api.openai.com/v1` | |
| Anthropic | `anthropic` | `https://api.anthropic.com` | |
| Google Gemini | `gemini` | SDK 默认 | |
| Azure OpenAI | `azure` | 用户资源端点（必填） | 模型填部署名 |
| AWS Bedrock | `bedrock` | SDK 默认（按区域） | 支持 Bedrock API Key（bearer），区域取 `AWS_REGION_NAME` |
| Google Vertex AI | `vertex_ai` | SDK 默认 | 支持 Express 模式 API Key 或服务账号 |
| Mistral | `mistral` | `https://api.mistral.ai/v1` | |
| xAI Grok | `xai` | `https://api.x.ai/v1` | |
| Perplexity | `perplexity` | `https://api.perplexity.ai` | |
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` | |
| Moonshot / Kimi | `moonshot` | `https://api.moonshot.cn/v1` | 国际站改 `api.moonshot.ai/v1` |
| 智谱 GLM | `zai` | `https://open.bigmodel.cn/api/paas/v4` | 国际站改 `api.z.ai` |
| 通义千问 / DashScope | `dashscope` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | |
| MiniMax | `minimax` | `https://api.minimaxi.com/v1` | 国际站改 `api.minimax.io/v1` |
| 火山方舟 / 豆包 | `volcengine` | `https://ark.cn-beijing.volces.com/api/v3` | 模型也可填 `ep-…` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | |
| Groq | `groq` | `https://api.groq.com/openai/v1` | |
| Together AI | `together_ai` | `https://api.together.xyz/v1` | |
| Fireworks AI | `fireworks_ai` | `https://api.fireworks.ai/inference/v1` | |
| Cerebras | `cerebras` | `https://api.cerebras.ai/v1` | |
| SambaNova | `sambanova` | `https://api.sambanova.ai/v1` | |
| Novita AI | `novita` | `https://api.novita.ai/v3/openai` | |
| Nebius AI Studio | `nebius` | `https://api.studio.nebius.com/v1` | |
| Ollama | 原生适配器（非 LiteLLM） | `http://127.0.0.1:11434` | 无 Key |
| CC Switch 代理 | `anthropic` | `http://127.0.0.1:15721` | Anthropic Messages 兼容 |

## 通过 OpenAI 兼容端点接入（LiteLLM 无独立前缀）

这些厂商没有（或当前 LiteLLM 版本没有）独立 provider 前缀，预设使用 `openai/<model>` + 官方
OpenAI 兼容地址；模型名保持服务端原样。

| 预设 | 端点 | 备注 |
|---|---|---|
| 百川智能 | `https://api.baichuan-ai.com/v1` | |
| 阶跃星辰 StepFun | `https://api.stepfun.com/v1` | |
| 零一万物 Yi | `https://api.lingyiwanwu.com/v1` | |
| 腾讯混元 | `https://api.hunyuan.cloud.tencent.com/v1` | LiteLLM 的 `tencent` 前缀指向 TokenHub 国际站，国内站按 openai 接入 |
| 硅基流动 SiliconFlow | `https://api.siliconflow.cn/v1` | |
| LM Studio | `http://127.0.0.1:1234/v1` | 无 Key |
| vLLM | `http://127.0.0.1:8000/v1` | 无 Key |
| OneAPI / NewAPI | 用户自填 | 必填 base URL |
| 自定义 OpenAI 兼容 | 用户自填 | 必填 base URL |

## 未接入 / 明确排除

- **Ollama 的 OpenAI 兼容模式**：直接走现有 `OllamaAdapter`，以免丢失 `/api/chat` 的
  `think`、`capabilities` 探测等行为。
- **LiteLLM 的 `openai_like` / `custom` 前缀**：需要额外 provider 元数据，实际行为不如
  `openai/<model>` + `api_base` 可预期，因此统一用 `openai`。
- **腾讯 TokenHub 国际站**：保留在 LiteLLM 中，但未做预设；国内用户使用混元官方端点。
- **其他 LiteLLM 聚合商**（DeepInfra、Hyperbolic、Parasail、Cloudflare 等）：本轮未列入，
  均可通过「自定义 OpenAI 兼容」接入。

## 数据模型与迁移

旧记录示例：

```json
{"id":"llm_old","kind":"openai","label":"OpenAI","model":"gpt-4.1-mini","baseUrl":"https://api.openai.com/v1"}
```

读取后自动推断：

- `presetId = null`
- `litellmProvider = "openai"`（即 `kind`）
- `needsKey = true`（`openai` / `anthropic`）
- `isLocal = false`（`ollama` / `mock` 才为 true）

旧客户端不带 `presetId` 调用 `PUT /assistant/providers/{id}` 仍按原逻辑工作；
新客户端只传 `presetId + apiKey` 也能保存，label / model / baseUrl / litellmProvider / needsKey
由预设补齐。

## 安全

- 预设中不含任何真实 Key；`GET /provider-presets` 不含 Key 字段。
- API Key 仍只写入 DPAPI 密文（`dpapi:v1:`），磁盘、返回值、日志均无明文。
- 「测试连接」复用现有脱敏逻辑；测试用例让 LiteLLM 抛出带 Key 的 401 异常，
  返回体只包含 `deepseek authentication failed (HTTP 401)`，不含 Key。
- 未新增遥测，未修改对话/工具循环。

## 验证

| 命令 | 结果 |
|---|---|
| `backend\.venv\Scripts\python.exe -m ruff check src tests` | 通过 |
| `pytest tests/assistant` | 通过（含新增 34 个参数化/用例） |
| `pytest tests/api` | 通过 |
| `npm run build`（tsc + vite） | 通过 |

完整 `pytest` 在当前工作区会被两个**与本次改动无关的既有问题**中断：

1. `tests/modules/test_official_*.py` 引用了已在工作区被删除的模块目录（`uplot`、`tremor` 等）；
2. `tests/assistant/test_sessions.py` 与 `tests/import_agent/test_sessions.py` 同名，
   无 `__init__.py` 时全量收集会报 import mismatch。

因此验收命令使用了 `tests/assistant` + `tests/api`；`--ignore=tests/modules` 的全量运行在
排除上述 duplicate basename 后同样通过。

## 手工验收建议

1. 设置页 → 添加提供商 → 搜索「DeepSeek」→ 粘贴 Key → 保存 → 测试连接（OpenAI 兼容）。
2. 添加「CC Switch 代理」→ 填本地代理 Key → 保存 → 测试连接（Anthropic 兼容）。
3. 添加「Ollama」→ 不填 Key → 保存 → 测试连接（本地模型）。
4. 用旧版 `providers.json` 启动，确认 provider 列表正常显示「已配置 Key」。
