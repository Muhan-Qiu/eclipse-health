# Agent 数据导入 API（A5）

> 状态：v1 接口契约（2026-11-01）
> 后端实现：`backend/src/eclipse_health_backend/import_agent/`
> 前端（A6）按本文实现；记录字段规范见 `docs/HEALTH_RECORD_KINDS.md`。

## 1. 目标

用户上传任意健康导出文件（CSV / JSON / XML / HTML / PDF / XLSX / ZIP / FIT / GPX / TCX 等），
内置 Agent 在受限沙箱里写 Python 解析，产出**候选健康记录**；用户确认后由后端校验并写入。
不再要求用户手工把文件改成固定格式。

Agent **不直接写数据库**。它只能：

1. 读取本次 session 的输入文件；
2. 在 `work/` 写脚本并运行；
3. 把中间结果写到 `output/`；
4. 通过 `propose_records` 提交候选；
5. 通过 `finish` 结束。

## 2. 安全边界（实现与文档必须一致）

| 边界 | 实现 |
|---|---|
| 文件范围 | 只复制用户本次选择/上传的文件到 `<data>/import-agent/<sessionId>/input/`；Agent 的全部工具路径都限制在该 session 目录内 |
| 进程隔离 | Agent 的 Python 在 `work/` 运行：独立子进程、`-I`（源码模式）、清空环境变量、cwd 限定、默认 120 s 超时、stdout/stderr 各 64 KB 上限；不提供 shell |
| 网络 | **默认关闭**：子进程环境不含代理与任何密钥；沙箱 bootstrap 还会拦截 `socket.connect` / `create_connection` / `getaddrinfo`、`subprocess` 与 `os.system`。**Windows 下这不是 OS 级硬沙箱**，只是纵深防御 |
| 数据库 | Agent 进程没有数据库连接；只有 `propose_records` 产出候选，commit 由主进程校验后写入 |
| 云端模型 | 不把整份原始文件发给模型。模型只看到：文件清单、大小/哈希、`read_text_file` 返回的文本片段；二进制文件不发送。默认建议本地 Ollama |
| 波形 | PDF/图片里的心电图波形无法可靠还原为采样点，只允许提取报告中的数值/结论；`kind=ecg` 必须附带 `output/` 下的采样文件，否则拒绝 |
| 审计 | 每次建会话/运行/工具调用/提交/放弃都写审计事件（`<data>/audit/import-agent.jsonl` + 尽力写 `audit_log` 表） |
| 清理 | 提交或放弃后删除 `input/ work/ output/`；24 h TTL 兜底 |

用户可在 UI 通过 SSE `tool_call` 事件看到 Agent 将读取/执行什么（`read_text_file` 参数、
`write_script` 的完整代码、`run_python` 参数、`propose_records` 的候选摘要）。

## 3. 会话生命周期

```
POST /sessions ──► created ──run(SSE)──► ready
                      │                  │
                      │                  └──commit──► committed（删除 input/work/output）
                      └──DELETE──────────────────────► 删除整个 session
```

- 状态：`created`、`running`、`ready`、`error`、`committed`。
- 同一 session 同时只允许一个 run；并发 run 返回 `409 run_in_progress`。
- `committed` 后再次 commit 是幂等的：返回首次结果并带 `duplicateCommit=true`。
- 运行失败可再次 run；重跑会清空 `work/ output/` 与候选，但保留 `input/`。

## 4. 端点

前缀：`/api/v1/import-agent`。错误统一 `{code, message, details}`。

### 4.1 创建会话

```http
POST /api/v1/import-agent/sessions
Content-Type: multipart/form-data
```

字段（三选一）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `files` 或 `files[]` | file[] | 本次上传的文件，最多 20 个 |
| `file` | file | 单文件上传（兼容） |
| `path` | string | 仅调试：本机绝对文件/目录路径；目录会递归复制 |

限制：单文件 ≤ 200 MB，session 总量 ≤ 300 MB；符号链接、`..` 条目拒绝。

`201`：

```json
{
  "sessionId": "ias_019..." ,
  "status": "created",
  "createdAt": "2026-11-01T10:00:00+00:00",
  "expiresAt": "2026-11-02T10:00:00+00:00",
  "files": [
    {
      "name": "export.csv",
      "storedName": "export.csv",
      "size": 12345,
      "sha256": "sha256:...",
      "kind": "csv"
    }
  ],
  "limits": {
    "maxFiles": 20,
    "maxUploadBytes": 209715200,
    "maxToolCalls": 12,
    "maxTurnSeconds": 180,
    "maxRunSeconds": 120,
    "maxProposalRecords": 20000,
    "network": false
  },
  "proposalCount": 0,
  "summary": null,
  "lastError": null,
  "commit": null
}
```

### 4.2 运行 Agent（SSE）

```http
POST /api/v1/import-agent/sessions/{sessionId}/run
Content-Type: application/json

{ "providerId": "llm_xxx", "instructions": "可选，补充说明，≤2000 字" }
```

- `providerId` 省略时选择第一个可用的 provider（优先本地 Ollama / Mock）。
- 没有可用 provider → `409 provider_not_configured`；ID 不存在 → `404 provider_not_found`；
  未启用 → `409 provider_disabled`；缺 API Key → `409 missing_api_key`。

响应 `text/event-stream`，事件：

| event | data | 说明 |
|---|---|---|
| `status` | `{phase, provider, files, limits, toolCalls, elapsedMs, network:false}` | 开始/每次工具后 |
| `token` | `{text}` | 模型文本流 |
| `tool_call` | `{id, name, args, index}` | Agent 即将执行什么；`write_script` 的 `args.code` 是完整代码 |
| `tool_result` | `{id, name, ok, durationMs, resultSummary, error?}` | 结果摘要（不返回完整文件内容） |
| `preview` | `{count, total, items, issues}` | `propose_records` 后立即推送；`items` 最多 50 条 |
| `done` | `{summary, proposalCount, toolCalls, durationMs, status}` | 正常结束 |
| `error` | `{code, message, details?}` | 失败结束 |

限制：最多 **12** 次工具调用，整轮 ≤ **180 s**；达到上限返回 `tool_limit` / `agent_timeout`。

### 4.3 确认并提交

```http
POST /api/v1/import-agent/sessions/{sessionId}/commit
Content-Type: application/json

{
  "records": ["prp_..."],
  "memberId": "mem_...",
  "timezone": "Asia/Shanghai"
}
```

- `records` 省略/空数组 → 提交全部候选。
- 元素可以是候选 ID 字符串、`{"id": "prp_..."}`，或完整候选对象（按指纹匹配）。
- 只能提交 `propose_records` 产生过的候选；未知项 → `422 record_not_proposed`。
- `memberId` 省略用默认成员；`timezone` 省略用 `UTC`。

`200`：

```json
{
  "sessionId": "ias_...",
  "created": 3,
  "skipped": 0,
  "failed": 0,
  "duplicateCommit": false,
  "recordIds": ["rec_..."],
  "counts": {"heart-rate": 2, "blood-pressure": 1},
  "errors": []
}
```

幂等：去重键 = `sha256(文件哈希 | 来源 | kind | startAt | endAt | 规范化 value)`。
同一文件同一来源重复提交只 `skipped`，不会产生重复记录。

### 4.4 读取会话

```http
GET /api/v1/import-agent/sessions/{sessionId}
```

返回与 4.1 相同的结构，加：

```json
{
  "proposals": [ ...前 200 条候选... ],
  "proposalCount": 1234,
  "proposalsTruncated": true,
  "lastError": {"code": "...", "message": "..."}
}
```

### 4.5 分页读取候选

```http
GET /api/v1/import-agent/sessions/{sessionId}/proposals?limit=200&offset=0
```

```json
{"items": [...], "total": 1234, "limit": 200, "offset": 0}
```

### 4.6 放弃会话

```http
DELETE /api/v1/import-agent/sessions/{sessionId}   → 204
```

删除整个 session 目录。已提交的会话删除后不影响已写入的记录。

### 4.7 最近会话

```http
GET /api/v1/import-agent/sessions?limit=20
```

返回 `{items: [session 摘要...]}`，按创建时间倒序；用于 UI 重载后恢复。

## 5. Agent 工具

工具名与参数是稳定契约（模型与前端共同依赖）：

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_files` | `{}` | 文件清单：名称、大小、sha256、类型；文本文件附 240 字符预览 |
| `read_text_file` | `{path, offset?, limit?}` | 按字节偏移读取文本；单次 ≤ 256 KB；二进制文件拒绝 |
| `write_script` | `{name, code}` | 在 `work/scripts/` 写脚本，`code` ≤ 64 KB |
| `run_python` | `{script, args?, timeout?}` | 在 `work/` 运行脚本；`timeout` 0.1–120 s |
| `write_output` | `{path, content}` | 写 `output/`，单文件 ≤ 8 MB |
| `read_output` | `{path, offset?, limit?}` | 读 `output/` 文本，单次 ≤ 256 KB |
| `propose_records` | `{records: [...]}` | 校验候选并写入 session；单次 ≤ 1000 条 |
| `finish` | `{summary}` | 结束并给出摘要 |

未列出的工具一律拒绝。工具结果超过 16 KB 会被截断后发给模型。

### 沙箱内可用的 helper

Agent 的脚本可 `import eh_import_helpers`，提供：

- `list_input_files()`、`input_path()`、`work_path()`、`output_path()`
- `read_text(path, offset=0, limit=...)`
- `read_csv_rows(path)`、`read_json(path)`、`read_xml(path)`
- `read_html_tables(path)`、`read_xlsx_rows(path, sheet=None)`
- `read_pdf_pages(path)`、`pdf_text(path)`
- `extract_zip_safe(path, dest="unzipped")`
- `write_output_text()`、`write_output_json()`

所有路径都限制在 session 的 `input/ work/ output/` 内。

## 6. Provider 与隐私

- 支持现有 provider：`openai`、`anthropic`、`ollama`、`mock`（见 `docs/LLM_PROVIDERS.md`）。
- 默认建议本地 Ollama；云端 provider 只会收到文件清单与文本片段。
- 不发送：二进制内容、整份大文件、环境变量、密钥、数据库内容。
- 用户可见：SSE `status.provider` 与 `tool_call` / `tool_result` 全量展示。

## 7. 错误码

| code | HTTP | 含义 |
|---|---|---|
| `session_not_found` | 404 | session 不存在 |
| `session_expired` | 404 | 超过 24 h TTL |
| `run_in_progress` | 409 | 同一 session 正在运行 |
| `session_committed` | 409 | 已提交，不能再 run |
| `provider_not_configured` | 409 | 没有可用 provider |
| `provider_disabled` | 409 | provider 被禁用 |
| `missing_api_key` | 409 | 云端 provider 缺 key |
| `invalid_file` / `file_too_large` | 422/413 | 上传问题 |
| `path_escape` | 422 | 工具路径越界 |
| `binary_file` | 422 | 对二进制文件调用 `read_text_file` |
| `tool_limit` | SSE error | 工具调用超过 12 次 |
| `agent_timeout` | SSE error | 整轮超过 180 s |
| `invalid_record` | 422 | 候选记录字段非法 |
| `ecg_waveform_required` | 422 | `kind=ecg` 但没有采样文件 |
| `record_not_proposed` | 422 | 提交了未提案的记录 |

## 8. 拒绝事项

- 不接受无法追溯到本次上传文件的记录（`evidence.file` 必须是本次文件或其子路径）。
- 不接受 PDF/图片“还原”的波形；只能写报告里的数值与结论。
- 不把 session 目录暴露给其他 session、其他成员或外部应用。

## 9. 样例（curl）

```bash
# 1) 建会话
curl -F "files=@export.csv" http://127.0.0.1:8765/api/v1/import-agent/sessions

# 2) 跑（SSE）
curl -N -X POST http://127.0.0.1:8765/api/v1/import-agent/sessions/ias_xxx/run \
  -H "Content-Type: application/json" -d '{"providerId":"llm_ollama"}'

# 3) 提交全部候选
curl -X POST http://127.0.0.1:8765/api/v1/import-agent/sessions/ias_xxx/commit \
  -H "Content-Type: application/json" -d '{}'
```
