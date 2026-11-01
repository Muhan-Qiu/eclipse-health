# eclipse health · 对外 API（F3）

> 状态：v1（2026-10-31）  
> Base URL：`http://127.0.0.1:8765/api/v1/external`  
> 仅本机可用：服务只监听 `127.0.0.1`，非回环来源返回 403 `local_only`。

外部 Agent / 编辑器 / DeepSeek Harness 通过应用内创建的 API Key 读取本地记录、分析与健康数据，并可调用应用内助手。所有请求默认作用于「本人」成员。

---

## 1. 创建与管理 API Key

Key 管理接口由桌面设置页调用，**不需要也用不上外部 key**；但仍只接受本机请求。

```bash
# 创建：明文 token 只在这里出现一次
curl -X POST http://127.0.0.1:8765/api/v1/external/keys \
  -H "Content-Type: application/json" \
  -d '{"name":"my-agent","scopes":["read","write","assistant"]}'
```

响应：

```json
{
  "id": "key_019...",
  "name": "my-agent",
  "prefix": "eh_ext_abcd1234",
  "scopes": ["read", "write", "assistant"],
  "createdAt": "2026-10-31T12:00:00Z",
  "lastUsedAt": null,
  "revokedAt": null,
  "revoked": false,
  "token": "eh_ext_<43 字符随机串>"
}
```

- `token` 形如 `eh_ext_<urlsafe 32 bytes>`，**只返回一次**；数据库只保存 SHA-256。
- 列表 `GET /keys` 只返回 `prefix`，不会返回 token 或 hash。
- 撤销：`DELETE /keys/{id}` → `204`；撤销后立即返回 401。

### scopes

| scope | 能力 |
|---|---|
| `read` | 读取记录、分析、健康数据、聚合摘要 |
| `write` | `POST /health-data` 写入健康数据（ECG 写入不开放） |
| `assistant` | `GET /openai/v1/models`、`POST /openai/v1/chat/completions` |

认证头二选一：

```http
Authorization: Bearer eh_ext_...
X-API-Key: eh_ext_...
```

错误：无效/撤销 → `401 invalid_api_key`；缺 scope → `403 insufficient_scope`（`details.required` 指明所需 scope）。

---

## 2. REST 读取

### 2.1 记录

```bash
curl http://127.0.0.1:8765/api/v1/external/records \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY"
```

查询参数：`limit`（1–200，默认 50）、`offset`、`recordTypePrefix`、`from`、`to`（RFC 3339）。

返回摘要，**不含**波形、`notes`、`metadata`、成员姓名；`tags` 只给数量：

```json
{
  "items": [
    {
      "id": "rec_...",
      "recordType": "org.eclipsehealth.ecg",
      "kind": "ecg",
      "capturedAt": "2026-10-30T08:00:00Z",
      "source": {"kind": "import", "manufacturer": "Apple"},
      "samplingRate": 360.0,
      "leads": ["MLII"],
      "durationSec": 180.0,
      "unit": "mV",
      "quality": {"score": 0.93, "level": "good"},
      "tagCount": 1,
      "favorite": false,
      "signalCount": 1
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

健康记录（`org.eclipsehealth.health.*`）额外带 `value`。单条：

```bash
curl http://127.0.0.1:8765/api/v1/external/records/rec_... \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY"
```

- ECG：`payload` 为 `null`，只有元数据；
- 健康数据：`payload` 为 `{kind, value, unit, startAt, endAt, sourceApp}`。

### 2.2 分析

```bash
curl http://127.0.0.1:8765/api/v1/external/analyses/ana_... \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY"
```

返回 `analysis`（状态、摘要、质量、警告、进度、`beatsTotal`）与 `measurements`；**不返回逐搏与原始波形**。

### 2.3 健康数据列表

```bash
curl "http://127.0.0.1:8765/api/v1/external/health-data?kind=steps&limit=30" \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY"
```

`kind`：`steps`、`heart-rate`、`sleep`、`body-mass`、`blood-pressure`；也支持 `from` / `to` / `offset`。
手工录入的体重/血压（metrics）会归入 `body-mass` / `blood-pressure`。

### 2.4 聚合摘要

```bash
curl "http://127.0.0.1:8765/api/v1/external/summary?days=7" \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY"
```

返回最近 N 天（1–365）的 `recordCount`（ECG 记录）、`healthRecordCount`、`analysisCount`、
`heartRate`、`hrv`、`quality`、`steps`、`sleep`（分钟）、`weight`、`bloodPressure`。
没有数据的项为 `null`。

---

## 3. 写入健康数据（scope: write）

```bash
curl -X POST http://127.0.0.1:8765/api/v1/external/health-data \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"kind":"steps","value":8231,"startAt":"2026-10-30T00:00:00Z","endAt":"2026-10-30T23:59:59Z","sourceApp":"my-agent"}'
```

请求体：`{kind, value, unit?, startAt, endAt?, sourceApp?}`。

- `steps`：0–10000000；
- `heart-rate`：10–400；
- `sleep`：数字表示分钟（0–1440）；也可传分类字符串并同时给 `endAt`；
- `body-mass`：2–500 kg；
- `blood-pressure`：`value` 为 `{"systolic":50–300,"diastolic":20–200}`，单位固定 `mmHg`。

超出范围 → 422；`endAt < startAt` → 422 `invalid_time_range`。ECG 写入不在本接口。

---

## 4. OpenAI 兼容端点（scope: assistant）

Base URL 直接填：

```text
http://127.0.0.1:8765/api/v1/external/openai/v1
```

- API Key：上面的外部 key（需包含 `assistant`）；
- Model：`eclipse-health`；
- 支持 `stream: true`（SSE，`data: {...}` / `data: [DONE]`）。

```bash
curl -X POST http://127.0.0.1:8765/api/v1/external/openai/v1/chat/completions \
  -H "Authorization: Bearer $EH_EXTERNAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"eclipse-health","messages":[{"role":"user","content":"我最近的心率怎么样？"}],"stream":false}'
```

非标准字段 `citations` 放在响应顶层（流式时在最后一个 chunk 里），工具调用过程不会透传。

安全边界：

- 外部请求里的 `system` / `tool` 消息会被忽略，不能覆盖应用内系统提示词；
- 只暴露现有只读 `ToolBox`，没有写操作；
- 未配置任何可用 LLM provider → `503 llm_not_configured`，请先在应用设置里配置。

---

## 5. MCP stdio server

入口：

```powershell
# 在项目根目录
$env:EH_EXTERNAL_KEY = "eh_ext_..."
$env:EH_API_BASE = "http://127.0.0.1:8765/api/v1"
backend\.venv\Scripts\python.exe -m eclipse_health_backend.mcp_server
```

工具：

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_records` | `limit?`, `offset?` | 最近记录摘要 |
| `get_record` | `record_id` | 单条记录 |
| `get_analysis` | `analysis_id` | 分析摘要 + 测量值 |
| `health_summary` | `days?` | 最近 N 天聚合 |
| `ask_assistant` | `question` | 调用 OpenAI 兼容端点；需 `assistant` scope 与已配置 LLM |

### Claude Code（`.mcp.json`）

```json
{
  "mcpServers": {
    "eclipse-health": {
      "command": "C:\\Users\\<you>\\Documents\\claude\\心电智能体\\v3\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "eclipse_health_backend.mcp_server"],
      "env": {
        "EH_EXTERNAL_KEY": "eh_ext_...",
        "EH_API_BASE": "http://127.0.0.1:8765/api/v1"
      }
    }
  }
}
```

### DeepSeek Harness / 其他 MCP 客户端

使用同样的 stdio 形态：`command` 指向后端 venv 的 `python.exe`，`args` 为
`["-m", "eclipse_health_backend.mcp_server"]`，环境变量同上。若客户端要求绝对路径，
`EH_API_BASE` 与 `command` 都写绝对路径即可。

错误映射：未设置 `EH_EXTERNAL_KEY`、401、403、404 或后端不可达时，工具会返回明确的
`ToolError` 文本，不会静默成功。

---

## 6. 安全说明

- **仅本机**：服务绑定 `127.0.0.1`；后端对非回环来源一律 403。
- **key 只显示一次**：明文只在创建响应出现；数据库存 SHA-256，列表只显示 `prefix`。
- **可撤销**：`DELETE /keys/{id}` 立即生效；`lastUsedAt` 便于发现异常使用。
- **数据最小化**：外部读取不含波形、备注、成员姓名、metadata；标签只给数量。
- **审计**：每次外部调用写 `external.call`（keyId、action、成功/失败、错误码），不记录健康数据内容。
- **不联网**：本模块不向任何远程服务发送数据；只有 `ask_assistant` 会把最小上下文发送到用户已配置的 LLM provider。

完整 OpenAPI：`http://127.0.0.1:8765/docs`。
