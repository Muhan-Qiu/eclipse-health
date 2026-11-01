# eclipse health · 内部 API 契约 v1（B2 用）

> 2026-10-28 · 指挥官文件 · 适用于 B2 四个 Agent
> 事实源：B1 已实现的 OpenAPI + 本文件对 B2 新增接口的约定。字段一律 **camelCase**，时间 RFC 3339 UTC。

## 0. 通用

- Base：`http://127.0.0.1:8765/api/v1`（端口 `EH_PORT`，默认 8765）。
- 错误体：`{ "code": "...", "message": "...", "details": {...} }`；HTTP 状态语义：400/404/409/413/422/500。
- 波形：`application/octet-stream`，小端 float32；元数据在响应头 `X-Signal-*`。
- 分页：`limit` + `offset`，默认 20，最大 200（记录）/ 5000（beats）。
- 演示/示例数据必须由 UI 标注；API 不返回「示例」标记。

## 1. B1 已有（不要改形状）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 状态、版本、数据库/数据目录、迁移 |
| GET/POST | `/members` | 成员列表/创建；`GET/PATCH /members/{id}` |
| GET | `/records?limit=&offset=&recordType=&moduleId=&favorite=&from=&to=&includeDeleted=` | `{items,total,limit,offset}`；`favorite=true/false` 按收藏过滤（B5） |
| POST | `/records` | 创建记录 + 单导联信号（B2 导入走 imports，不直接用它） |
| GET/PATCH/DELETE | `/records/{id}` | 读取/更新/软删除 |
| GET | `/records/{id}/signals` | 信号元数据数组 |
| GET | `/records/{id}/signal?lead=` | 原始 float32 波形 |

`HealthRecord` 关键字段：`id, memberId, recordType, moduleId, capturedAt, timezone, source, samplingRate, leads, durationSec, unit, signalIds, quality, tags, notes, metadata, payload, createdAt, updatedAt, deletedAt`。

## 2. B2 新增：导入

### 2.1 预览

`POST /imports/preview`（`multipart/form-data`）

- `file`：必需（≤200MB）；或 `path`：本地调试用绝对路径（仅 B2 调试，正式 UI 用 file）。
- `hintFormat`：可选 `wfdb|csv|auto`，默认 `auto`。

200：

```json
{
  "importId": "imp_0192...",
  "format": "wfdb",
  "adapterId": "org.eclipsehealth.wfdb",
  "fileNameHash": "sha256:...",
  "fileHash": "sha256:...",
  "samplingRate": 360,
  "leads": ["MLII"],
  "durationSec": 1800.0,
  "unit": "mV",
  "requires": { "samplingRate": false, "lead": false, "unit": false },
  "warnings": [],
  "preview": { "nSamples": 650000, "samples": [0.01, 0.02] }
}
```

- `samples` 最多 2000 点；用于波形预览。
- 无法识别：422 `{code:"unsupported_format"}`；文件损坏：422 `{code:"invalid_file"}`。

### 2.2 提交

`POST /imports/{importId}/commit`

```json
{
  "memberId": "mem_...",
  "capturedAt": "2026-10-28T10:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "tags": ["晨起"],
  "notes": "",
  "parameters": { "samplingRate": 360, "lead": "MLII", "unit": "mV", "polarity": "normal" }
}
```

201：`{ "recordId": "rec_...", "record": { ...HealthRecord } }`

- 参数校正写回记录；`polarity="inverted"` 时翻转样本并记录 `metadata.polarity`。
- 临时文件在 commit / delete / 24h TTL 后清理。

### 2.3 丢弃

`DELETE /imports/{importId}` → 204。

### 2.4 内置示例记录（B5 / A1）

`POST /imports/samples/{sampleId}`

- `sampleId` 白名单：`mitdb-100`、`mitdb-200`、`mitdb-208`（`backend/resources/samples/` 内 WFDB）；未知 → 404 `sample_not_found`。
- 请求体可空：`{memberId?, capturedAt?, timezone?, startAnalysis?}`；`memberId` 缺省用默认成员。
- 201：`{ "recordId": "rec_...", "analysisId": "ana_..." | null }`。
- 走真实导入管线；记录 `metadata.isSample=true` / `metadata.sampleId`，`source.kind="import"`。
- `startAnalysis=true` 时异步发起 Cardia 分析；分析失败不影响记录创建（`analysisId=null`）。

## 3. B2 新增：分析

### 3.1 发起

`POST /records/{recordId}/analyses`

```json
{ "engine": "cardia", "options": { "allowShortRecord": false } }
```

202：

```json
{ "analysisId": "ana_...", "recordId": "rec_...", "status": "queued", "engine": "cardia" }
```

- 同一记录串行分析；重复点击返回已有 `running` 分析（409 或 202 幂等，二选一并写进 OpenAPI）。
- 记录不存在 404；无信号 409 `record_has_no_signal`；<64 搏且未允许短记录 422 `too_few_beats`。

### 3.2 轮询

`GET /analyses/{analysisId}`

- 默认包含 beats；`?includeBeats=false` 可省。
- `status`: `queued|running|completed|failed|cancelled`。
- `progress`: `{ "stage": "quality|features|inference|measurements|summary", "percent": 0-100 }`（可为 null）。
- 失败：`error: {code, message}` + `warnings`。

`GET /records/{recordId}/analyses` → `{ "items": [AnalysisSummary] }`，按 `createdAt` 倒序。

`GET /analyses/{analysisId}/beats?offset=&limit=` → `{items,total,limit,offset}`（大记录用）。

### 3.3 引擎状态

`GET /engine`（或 `/analysis/engine`，二选一，固定在 OpenAPI）

```json
{
  "status": "warming|ready|error",
  "engine": "cardia",
  "moduleId": "org.eclipsehealth.cardia",
  "modelId": "cardia-2.0",
  "modelVersion": "2.0.0",
  "message": "首次加载约 150 秒",
  "startedAt": "...",
  "readyAt": null
}
```

- UI 在 `warming` 时禁用「分析」并显示原因；引擎就绪后可点。
- 若 ONNX 启动优化成功，`message` 改为实际耗时。

### 3.4 引擎目录（B5 / C7）

`GET /analyses/engines`

```json
{
  "items": [
    {
      "id": "cardia",
      "name": "Cardia 2.0",
      "moduleId": "org.eclipsehealth.cardia",
      "modelId": "cardia-2.0",
      "modelVersion": "2.0.0",
      "available": true,
      "reason": null
    }
  ]
}
```

- 列表来自后端注册表，UI 不得写死引擎；当前仅内置 Cardia，更多引擎由模块提供（平台 #1 ONNX loader）。
- `POST /records/{id}/analyses` 的 `engine` 按注册表校验；未注册 → 422 `unknown_engine`，`details.supported` 为可用 ID。
- 同记录存在 `queued|running` 分析时仍幂等复用；`completed|failed` 后再次 POST 视为重新分析，新建一条。

## 4. 数据形状约定

- `AnalysisResult` 按 `DATA_SCHEMA_V1` §6；B2 增加：
  - `beats[].probabilities`: `{N,SVEB,VEB,F}`，0–1；
  - `measurements`: 完整对象数组（`id,code,label,value,unit,ucum,range,confidence,method,warnings`），不是 ID 数组；
  - `progress`, `error` 为 B2 扩展字段。
- 比率类测量值用百分数 0–100，`unit="%"`；`ucum` 留空字符串表示无 UCUM。
- `summary` 是一句话中文/本地化前的英文均可，UI 用结构化字段重新渲染 i18n 文案。

## 5. UI 视图模型（B2-03 用）

后端 `HealthRecord` → UI `RecordSummary` 的映射：

- `device`：由 `source.manufacturer/model` 组合；
- `sampleRateHz`：`samplingRate`；
- `status`：由 `signalIds.length` + 是否存在分析派生（`ready|analyzing|analyzed|failed`），不在后端存储；
- `capturedAt` 直接使用；`tags/leads` 直接使用。

禁止在 UI 里假设后端有 `device` 字段；映射层放 `src/lib/api/adapters.ts`。

## 6. 非目标（B2 不做）

SSE/WebSocket、取消分析、批量分析、12 导联、报告 PDF、模块安装 UI、权限授权 UI、远程模型、MCP。轮询足够。
