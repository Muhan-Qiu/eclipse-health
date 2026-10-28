# eclipse health · 数据 Schema v1（草案）

> 2026-10-28 · 状态：草案，待用户确认
> 前提：JSON Schema 为唯一事实源（Q14）；模块不得直接读库；模块自定义数据走核心记录扩展。

## 0. 原则

1. **一套契约，多语言生成**：Schema 在 `schemas/`，生成 Python/TypeScript 类型与文档。
2. **核心字段稳定，模块数据隔离**：核心字段固定；模块自定义内容放 `payload`，按模块注册的 Schema 校验。
3. **数值与单位分离**：数值只存 number；单位用 UCUM 代码，展示单位另存。
4. **可追溯**：来源、适配器版本、文件哈希、模型版本、预处理版本必须可查。
5. **可迁移**：每个对象带 `schema` 版本；迁移前自动备份。
6. **隐私优先**：默认不保存原始文件名等潜在 PII；需要时由用户显式开启。

## 1. 命名与 ID

- ID 格式：`<prefix>_<UUIDv7>`，如 `rec_0192f3...`。
- 前缀：`mem_` 成员、`rec_` 记录、`sig_` 信号、`ana_` 分析、`msr_` 测量、`ann_` 标注、`rep_` 报告、`mod_` 模块、`evt_` 审计。
- UUIDv7 可按时间排序，便于分页与本地索引。
- 模块 ID：官方 `org.eclipsehealth.*`；社区 `io.github.<owner>.<name>`（Q24）。

## 2. 通用类型

| 类型 | 规则 |
|---|---|
| `DateTime` | RFC 3339，带时区；存储 UTC |
| `Duration` | 秒，number |
| `Unit` | UCUM 代码字符串，如 `bpm`、`ms`、`mV`、`/min` |
| `JsonObject` | 任意 JSON 对象，大小受限 |
| `Tags` | string[]，≤32 项，每项 ≤32 字符 |
| `Confidence` | 0–1 number |
| `SchemaRef` | 形如 `org.eclipsehealth.record/1` |

## 3. Member（成员）

```json
{
  "schema": "org.eclipsehealth.member/1",
  "id": "mem_0192f3...",
  "displayName": "本人",
  "birthYear": 1990,
  "sex": "female",
  "heightCm": 165,
  "weightKg": 58,
  "conditions": ["高血压"],
  "medications": ["氨氯地平"],
  "notes": "",
  "createdAt": "2026-10-28T10:00:00Z",
  "updatedAt": "2026-10-28T10:00:00Z"
}
```

- `birthYear` 而非完整生日，降低 PII。
- `conditions` / `medications` 可选，仅用于解释上下文；可随时清除。
- 首版仅一个默认成员，但数据模型带 `memberId`（D7 架构预留）。

## 4. HealthRecord（健康记录）

```json
{
  "schema": "org.eclipsehealth.record/1",
  "id": "rec_0192f3...",
  "memberId": "mem_0192f3...",
  "recordType": "org.eclipsehealth.ecg",
  "moduleId": "org.eclipsehealth.samsung",
  "capturedAt": "2026-10-28T10:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "source": {
    "kind": "wearable",
    "manufacturer": "Samsung",
    "device": "Galaxy Watch",
    "app": "Samsung Health",
    "appVersion": "6.x"
  },
  "samplingRate": 500.0,
  "leads": ["I"],
  "durationSec": 30.0,
  "unit": "mV",
  "signalIds": ["sig_0192f3..."],
  "quality": { "score": 0.93, "level": "good", "warnings": [] },
  "tags": ["晨起"],
  "notes": "心悸",
  "metadata": { "resting": true },
  "payload": {},
  "provenance": {
    "fileNameHash": "sha256:...",
    "fileHash": "sha256:...",
    "adapterVersion": "1.0.0"
  },
  "createdAt": "2026-10-28T02:00:00Z",
  "updatedAt": "2026-10-28T02:00:00Z",
  "deletedAt": null
}
```

固定字段（核心）：`schema/id/memberId/recordType/moduleId/capturedAt/timezone/source/samplingRate/leads/durationSec/unit/signalIds/tags/notes/metadata/provenance/createdAt/updatedAt/deletedAt`。

模块扩展：`payload`，必须通过该 `recordType` 注册的 Schema 校验。

`recordType` 命名：

- 核心：`org.eclipsehealth.ecg`、`org.eclipsehealth.ppg`、`org.eclipsehealth.eeg`（后续）。
- 第三方：`io.github.<owner>.<domain>`。

## 5. Signal（信号）

```json
{
  "schema": "org.eclipsehealth.signal/1",
  "id": "sig_0192f3...",
  "recordId": "rec_0192f3...",
  "lead": "I",
  "fs": 500.0,
  "unit": "mV",
  "dtype": "float32",
  "shape": [15000],
  "startSample": 0,
  "storage": {
    "kind": "file",
    "relativePath": "signals/sig_0192f3.f32",
    "sha256": "...",
    "byteOrder": "little"
  },
  "createdAt": "2026-10-28T02:00:00Z"
}
```

- 波形不存 JSON；按导联分文件，float32 小端；元数据存 SQLite。
- 模块只拿 `SignalHandle`，通过 `signals.read` 读取切片，不接触真实路径。
- 多导联：一条记录多个 Signal，`lead` 区分；12 导联用标准名称 `I/II/III/aVR/aVL/aVF/V1..V6`。

## 6. AnalysisResult（分析结果）

```json
{
  "schema": "org.eclipsehealth.analysis/1",
  "id": "ana_0192f3...",
  "recordId": "rec_0192f3...",
  "moduleId": "org.eclipsehealth.cardia",
  "modelId": "cardia-2.0",
  "modelVersion": "2.0.0",
  "task": "beat-classification",
  "status": "completed",
  "startedAt": "2026-10-28T02:00:01Z",
  "completedAt": "2026-10-28T02:00:03Z",
  "durationMs": 2100,
  "summary": "N 96.2% · SVEB 1.1% · VEB 2.4% · F 0.3%",
  "quality": { "score": 0.93, "level": "good", "warnings": [] },
  "measurements": ["msr_..."],
  "beats": [
    { "index": 0, "rPeakSample": 120, "label": "N", "confidence": 0.99, "rrPrevMs": 850 }
  ],
  "annotations": ["ann_..."],
  "warnings": [],
  "parameters": { "engine": "cardia", "sequenceLength": 64 },
  "provenance": { "preprocess": "cardia-v2", "preprocessVersion": "2.0" }
}
```

- `status`: `queued|running|completed|failed|cancelled`。
- `beats` 超过 50,000 条时改用 `beatsRef` 文件，JSON 只放引用。
- 模型版本、预处理版本必须记录，否则结果不可复现。

## 7. Measurement（测量值）

```json
{
  "schema": "org.eclipsehealth.measurement/1",
  "id": "msr_0192f3...",
  "recordId": "rec_0192f3...",
  "analysisId": "ana_0192f3...",
  "code": "heart_rate_mean",
  "label": "平均心率",
  "value": 68.0,
  "unit": "bpm",
  "ucum": "/min",
  "range": { "startSec": 0, "endSec": 30 },
  "confidence": 0.98,
  "method": "cardia-2.0",
  "warnings": []
}
```

核心测量码（固定）：

`heart_rate_mean/min/max`、`rr_mean`、`sdnn`、`rmssd`、`pnn50`、`qrs_duration`、`pr_interval`、`qt_interval`、`qtc`、`n_ratio`、`svb_ratio`、`veb_ratio`、`f_ratio`。

模块自定义码必须命名空间化：`io.github.owner.metric_name`。

## 8. Annotation / Beat / Quality

### 8.1 Annotation

```json
{
  "schema": "org.eclipsehealth.annotation/1",
  "id": "ann_0192f3...",
  "recordId": "rec_0192f3...",
  "analysisId": "ana_0192f3...",
  "type": "r_peak|beat_label|quality_segment|event",
  "label": "VEB",
  "startSample": 1200,
  "endSample": 1260,
  "confidence": 0.87,
  "source": "cardia-2.0"
}
```

### 8.2 Beat

`index`、`rPeakSample`、`label`、`confidence`、`rrPrevMs`、可选 `rrNextMs`、`morphologyRef`。

### 8.3 Quality

```json
{
  "score": 0.93,
  "level": "good|fair|poor",
  "warnings": [
    { "code": "lead_off", "severity": "warning", "startSec": 12.0, "endSec": 13.5, "message": "导联脱落" }
  ],
  "segments": [
    { "startSec": 0, "endSec": 30, "quality": 0.93 }
  ]
}
```

## 9. Report（报告）

```json
{
  "schema": "org.eclipsehealth.report/1",
  "id": "rep_0192f3...",
  "recordId": "rec_0192f3...",
  "analysisId": "ana_0192f3...",
  "templateId": "eclipse.standard",
  "format": "pdf|png",
  "storage": { "relativePath": "reports/rep_...pdf", "sha256": "...", "size": 245678 },
  "createdAt": "2026-10-28T02:05:00Z"
}
```

## 10. 模块自定义记录类型

模块在 manifest 中注册：

```json
{
  "recordTypes": [
    {
      "id": "io.github.owner.eeg.record",
      "name": "EEG Recording",
      "schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
          "channelCount": { "type": "integer", "minimum": 1 },
          "montage": { "type": "string" }
        },
        "required": ["channelCount"],
        "additionalProperties": false
      },
      "indexes": ["capturedAt", "payload.channelCount"],
      "display": { "title": "脑电", "icon": "brain" }
    }
  ]
}
```

规则：

- 核心字段固定；模块字段只能进 `payload`。
- 模块不得建表；需要查询的字段用 `indexes` 声明 JSON 路径，由核心建索引。
- `payload` 默认 ≤ 1MB；更大数据用文件引用。
- 卸载时可选择保留或删除 payload；保留时标记孤立数据。

## 11. 存储映射

| SQLite 表 | 关键列 | JSON |
|---|---|---|
| `members` | id, displayName | 完整对象 |
| `records` | id, memberId, recordType, moduleId, capturedAt, deletedAt | 完整对象 + payload |
| `signals` | id, recordId, lead, fs | 元数据 |
| `analyses` | id, recordId, moduleId, modelId, status, createdAt | 完整对象 |
| `measurements` | id, recordId, analysisId, code, value, unit | 完整对象 |
| `annotations` | id, recordId, analysisId, type, label | 完整对象 |
| `reports` | id, recordId, format, createdAt | 完整对象 |
| `modules` | id, version, enabled, installedAt | manifest 摘要 |
| `audit_log` | id, moduleId, action, scope, createdAt | 事件 |

波形文件：`data/signals/<id>.f32`；报告：`data/reports/<id>.<ext>`；均带 sha256。

## 12. 校验与大小限制

| 项 | 限制 |
|---|---|
| `metadata` | ≤16KB |
| `notes` | ≤4000 字符 |
| `tags` | ≤32 项，每项 ≤32 字符 |
| `payload` | ≤1MB（超出用文件引用） |
| `leads` | ≤16 |
| `measurements` | ≤500 / 分析 |
| `beats` 内联 | ≤50,000；超出用 `beatsRef` |
| 单条记录波形 | ≤24h / ≤2GB，超出拒绝并提示分段 |

- 写入前校验 Schema；未知字段默认拒绝（`additionalProperties: false`）。
- 迁移/导入时允许宽松模式，但必须标记 `legacy: true`。

## 13. 版本与迁移

- 每个对象带 `schema`，如 `org.eclipsehealth.record/1`。
- 核心至少兼容当前与前一个大版本；迁移脚本幂等。
- 迁移前自动备份数据库与信号文件索引。
- 模块自定义 Schema 版本由模块提供迁移；核心在事务内执行，失败回滚。

## 14. 生成类型与 CI

- `schemas/` 为唯一事实源；生成：
  - TypeScript：`json-schema-to-typescript`
  - Python：`datamodel-code-generator` → Pydantic v2
- CI：Schema 语法、示例校验、向后兼容检查、生成代码 diff。
- 每个模块模板自带 Schema 示例与测试。

## 15. 隐私与 PII

- 默认不保存原始文件名；只存 `fileNameHash` 与 `fileHash`。
- `notes` / `conditions` / `medications` 是用户主动输入，导出时提示可能含敏感信息。
- 导出包默认不含原始波形？可配置；报告分享默认脱敏。
- 审计日志不记录波形内容，只记录访问范围。

## 16. 示例

### 16.1 手表单导联 ECG

已在上文 HealthRecord/Signal/AnalysisResult 示例中给出。

### 16.2 未来 EEG 记录

`recordType: "io.github.owner.eeg.record"`，`payload: { "channelCount": 8, "montage": "10-20" }`，波形仍走 Signal，多导联按 `lead` 存。

## 17. 决策记录

已定（2026-10-28）：

- 数据契约：**JSON Schema 2020-12** 为唯一事实源。
- 模块数据：**核心记录 + `payload` 扩展**，模块不建新表。
- 波形：二进制文件 + Signal 元数据；模块只拿句柄。
- Q37 ID：**前缀 + UUIDv7**（如 `rec_0192f3...`）。
- Q38 单位：**UCUM**（bpm、ms、mV），展示单位另存。
- Q39 模块数据：**核心 `records.payload`**，按模块注册 Schema 校验。
- Q40 逐搏：**内联 JSON ≤50,000 条**，超出自动转 `beatsRef` 文件。
- Q41 Schema 方言：**JSON Schema draft 2020-12**。
- Q42 PII：**默认剥离原始文件名**，只存哈希；用户可显式开启保留。
- Q43 删除：**软删除 + 30 天回收站**，到期自动清除；用户可手动彻底删除。
- Q44 导出：**WFDB + CSV + 原始 float32 + JSON 元数据**。

> 以上为实现细节，用户不需要逐项确认；后续试用后觉得不合适可随时调整。
