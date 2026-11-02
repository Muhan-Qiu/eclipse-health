# 报告 · F3 对外 API（后端）

状态：完成

## 交付

- `external_auth.py`：API Key 创建/校验/撤销、scope 检查、`last_used_at` 更新。
  - token 格式 `eh_ext_<secrets.token_urlsafe(32)>`，明文只在创建响应返回一次。
  - 数据库 `external_api_keys.key_hash` 只存 SHA-256（hex），列表只返回 16 字符 `prefix`。
- `db/models.py`：新增 `ExternalApiKeyTable`（id/name/prefix/key_hash/scopes JSON/created_at/last_used_at/revoked_at）。
- `api/external.py`：挂载 `/api/v1/external`，全部端点仅回环访问（非本机 403 `local_only`）。
  - Key 管理（本地设置免 key）：`GET /keys`、`POST /keys`、`DELETE /keys/{id}`。
  - REST（scope read）：`GET /records`、`GET /records/{id}`、`GET /analyses/{id}`、
    `GET /health-data`、`GET /summary`。
  - 写入（scope write）：`POST /health-data`；校验步骤/心率/睡眠/体重/血压边界，ECG 不开放。
  - OpenAI 兼容（scope assistant）：`GET /openai/v1/models`、
    `POST /openai/v1/chat/completions`；复用 `llm.agent` + 只读 `ToolBox`，支持 SSE；
    无可用 provider → 503 `llm_not_configured`；客户端 system/tool 消息被忽略。
  - 读取响应不含波形、notes、metadata、成员姓名；tags 只返回数量。
  - 每次外部调用写审计 `external.call`（keyId/action/ok/error），不含健康数据内容。
- `mcp_server.py`：基于已安装 `mcp` 2.3 的 `MCPServer`，入口
  `python -m eclipse_health_backend.mcp_server`；读取 `EH_EXTERNAL_KEY`，
  `EH_API_BASE` 默认 `http://127.0.0.1:8765/api/v1`；工具 `list_records`、
  `get_record`、`get_analysis`、`health_summary`、`ask_assistant`，错误统一为 `ToolError`。
- `docs/EXTERNAL_API.md`：key 创建、scopes、curl、OpenAI base URL、Claude Code/DeepSeek
  Harness MCP 配置与安全说明。
- `api/__init__.py` 挂载 external router；`db/base.py` 无需改动（`init_db` 已导入 models）。

## 验证

- 命令：`backend\.venv\Scripts\python.exe -m ruff check backend`
  - 结果：`All checks passed!`
- 命令：`backend\.venv\Scripts\python.exe -m pytest backend/tests/external`
  - 结果：`23 passed in 1.40s`
  - 覆盖：key 创建/列表/撤销/hash 不泄露、401/403、REST 读与脱敏、summary、
    健康数据写入与边界、审计、OpenAI models/非流式/流式/503/404/422、MCP 工具列表与调用。
- 回归：`pytest backend/tests/api backend/tests/assistant backend/tests/metrics backend/tests/core`
  - 结果：`171 passed, 11 skipped in 12.88s`

## 未做 / 偏离

- 未做 LAN/公网、OAuth、多用户（任务明确不做）；仅本机、单成员「本人」。
- 未改前端 key 管理 UI（F4 范围）；当前由设置页/直接 HTTP 调用 `/external/keys`。
- OpenAI 端点固定 `model="eclipse-health"`，不开放按 provider id 选择；`temperature` 被接受但未透传。
- `POST /health-data` 先写 `org.eclipsehealth.health.*` 记录；summary 同时聚合手工 metrics
  的体重/血压，保证用户在应用内录入的数据也能被外部读到。
- 撤销是软撤销（`revoked_at`），列表保留记录；`last_used_at` 每次认证更新。

## 跨区需求（需要别的 Agent 或指挥官处理）

- `backend/pyproject.toml` 依赖列表未声明 `mcp`（本机已安装 2.3.0）。打包/新环境可能缺包，
  需要把 `mcp>=2.3` 加入 dependencies；该文件不在本任务所有权内。
- F4 设置页可接入 `GET/POST/DELETE /api/v1/external/keys`，并提示 token 只显示一次。
- 若以后加反向代理/非回环部署，`_require_local` 的 localhost 白名单需重新评估。

## 需要指挥官决策

- 是否允许 OpenAI 兼容端点通过 `model` 选择具体 provider（当前固定使用首个可用 provider）。
- 是否在 v1 开放 `DELETE /health-data/{id}` 或记录写操作（当前 write 仅新增健康数据）。

## 建议下一批

- F4 密钥管理 UI + 一键复制 MCP 配置。
- 用真实 DeepSeek Harness 跑一次 MCP `ask_assistant` 端到端联调。
- 把 `mcp` 纳入依赖并补 CI 打包验证。
