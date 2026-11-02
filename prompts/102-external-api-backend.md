# F3 · 对外 API：API Key + REST + OpenAI 兼容 + MCP（后端）

> 先读 `prompts/00-COMMON.md`、`backend/src/eclipse_health_backend/api/__init__.py`、`api/assistant.py`、`db/models.py`、`docs/INTERNAL_API_V1.md`。
> 用户要求：外面的 Agent / Code / DeepSeek Harness 用我们发的 key，调用本应用的 Agent 与本地数据；**仅本机访问**；默认读+写，另有 assistant 权限。

## 交付

### 1. API Key 管理（本地设置用，不需要 key 认证）

- 新表 `ExternalApiKeyTable`（`db/models.py`）：
  - `id`（`key_...`）、`name`、`prefix`（展示用）、`key_hash`（SHA-256）、`scopes`（JSON 数组）、`created_at`、`last_used_at`、`revoked_at`。
  - 明文 token 只在创建时返回一次：`eh_ext_<urlsafe 32 bytes>`；数据库只存 hash。
- `external_auth.py`：创建/校验/撤销、scope 检查、`last_used_at` 更新。
- 端点（挂在 `/api/v1/external`，本地 UI 调用）：
  - `GET /keys` → 列表（masked，不返回 hash/明文）
  - `POST /keys` `{name, scopes:["read","write","assistant"]}` → `{id, token, ...}`（token 仅此一次）
  - `DELETE /keys/{id}` → 204/撤销
- 外部请求认证：`Authorization: Bearer <token>` 或 `X-API-Key`；无效/撤销 → 401 `invalid_api_key`；缺 scope → 403 `insufficient_scope`。

### 2. 外部 REST（scope: read / write）

- `GET /records?limit&offset&recordTypePrefix&from&to` → 记录摘要（不含波形、备注、成员姓名；健康记录含 value/unit）。
- `GET /records/{id}` → 单条记录摘要 + payload（健康数据）；ECG 只返回元数据，不返回波形。
- `GET /analyses/{id}` → 分析摘要 + measurements（不返回逐搏、原始波形）。
- `GET /health-data?kind=steps|heart-rate|sleep|body-mass|blood-pressure&from&to&limit` → 健康数据列表。
- `GET /summary?days=7` → 聚合：记录数、最近平均心率/HRV/质量、步数/睡眠/体重/血压最新与均值（有就返回，无则 null）。
- `POST /health-data`（scope write）→ 创建健康记录 `{kind,value,unit?,startAt,endAt?,sourceApp?}`；复用 metrics/records 服务与校验；ECG 写入不在本接口。
- 所有响应不包含 notes/metadata 中的敏感字段；审计 `external.call`（keyId、action、ok/error），不记录健康数据内容。

### 3. OpenAI 兼容端点（scope: assistant）

- `GET /openai/v1/models` → `{data:[{id:"eclipse-health",...}]}`。
- `POST /openai/v1/chat/completions`：
  - 请求兼容 OpenAI：`{model:"eclipse-health", messages, stream?, temperature?}`；
  - 复用应用内 assistant 服务与已配置的 LLM + 本地工具；返回 OpenAI 形状（`choices[].message.content`、`usage`）；
  - `stream=true` 返回 SSE `data: {...}` / `[DONE]`；
  - 未配置 LLM → 503 `llm_not_configured`，明确提示先在应用设置里配置 provider；
  - 工具调用过程不需要透传给外部（只返回最终回答 + citations 放非标准字段）；
  - 不允许外部请求指定任意系统提示词越权读取；只暴露只读工具（现有 `ToolBox` 只读）。
- base URL 文档写清楚：`http://127.0.0.1:8765/api/v1/external/openai/v1`。

### 4. MCP server（stdio）

- 新建 `backend/src/eclipse_health_backend/mcp_server.py`，使用已安装的 `mcp` 包：
  - 从 `EH_EXTERNAL_KEY` 读取 key，`EH_API_BASE` 默认 `http://127.0.0.1:8765/api/v1`；
  - tools：`list_records`、`get_record`、`get_analysis`、`health_summary`、`ask_assistant`（调用 OpenAI 兼容端点）；
  - 错误映射：无 key/401 → 明确错误；工具参数 JSON Schema。
  - 入口：`python -m eclipse_health_backend.mcp_server`。
- `docs/EXTERNAL_API.md`：创建 key、scopes、curl 示例、OpenAI 配置、MCP 配置（Claude Code / DeepSeek Harness）、安全说明（仅本机、key 只显示一次、可撤销）。

### 5. 测试

- `backend/tests/external/test_keys.py`：创建/列表/撤销、hash 不返回、401/403。
- `backend/tests/external/test_external_api.py`：REST 读、summary、写健康数据、scope 限制、审计。
- `backend/tests/external/test_openai_compat.py`：models、非流式/流式（mock LLM 或测试 adapter）、无 LLM 503。
- MCP：至少测试 tool list 与一个 tool 调用（可 mock httpx）。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/api/external.py`（新建）
- `backend/src/eclipse_health_backend/external_auth.py`（新建）
- `backend/src/eclipse_health_backend/mcp_server.py`（新建）
- `backend/src/eclipse_health_backend/db/models.py`
- `backend/src/eclipse_health_backend/db/base.py`（仅 import 新表）
- `backend/src/eclipse_health_backend/api/__init__.py`（挂 external router）
- `backend/tests/external/**`（新建）
- `docs/EXTERNAL_API.md`（新建）
- `reports/F3-*.md`

## 明确不做

- 不做 LAN/公网访问、不做 OAuth、不做多用户；仅 127.0.0.1。
- 不改前端（F4）、不改 LLM provider 配置逻辑。
- 不新增依赖（mcp/httpx 已装）；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\external -q
```

报告 `reports/F3-external-api-report.md`，≤80 行：key 格式/存储、scope、REST/OpenAI/MCP 端点、真实测试输出、未做项。
