# 健康记录 kinds（导入 Agent v1）

> 状态：v1（2026-11-01）
> 实现：`backend/src/eclipse_health_backend/import_agent/kinds.py`
> 本文是 `propose_records` / commit 的字段事实源；与 `docs/DATA_SCHEMA_V1.md` 的
> `records.payload` 约定一致。

## 1. 通用候选结构

```json
{
  "kind": "heart-rate",
  "value": 72,
  "unit": "count/min",
  "startAt": "2026-10-30T08:15:00+08:00",
  "endAt": "2026-10-30T08:20:00+08:00",
  "source": {"kind": "app", "app": "Apple Health", "device": "Apple Watch"},
  "evidence": {
    "file": "export.xml",
    "locator": "line 12034",
    "snippet": "<Record type=\"HKQuantityTypeIdentifierHeartRate\" ... value=\"72\"/>"
  },
  "confidence": 0.95,
  "tags": ["导入"],
  "notes": ""
}
```

必填：`kind`、`value`、`unit`、`startAt`、`source`、`evidence`、`confidence`。

- `startAt` / `endAt`：RFC 3339，**必须带时区**；`endAt` 缺省表示点测量。
- `source`：`{kind: "app" | "device" | "manual" | "unknown", app?, device?, manufacturer?}`
  （每项 ≤ 64 字符）。
- `evidence`：`file` 必填，必须是本次上传文件名，或 `文件名/子路径`（ZIP 内路径）；
  `locator` / `snippet` / `page` / `line` 至少提供一个。`snippet` ≤ 500 字符。
- `confidence`：0–1。
- `tags`：≤ 8 项，每项 ≤ 32 字符；`notes` ≤ 2000 字符。
- 数值统一保留 6 位小数参与去重指纹。

持久化：

| 字段 | 落库位置 |
|---|---|
| `recordType` | `org.eclipsehealth.health.<kind>`；`ecg` 为 `org.eclipsehealth.ecg` |
| `capturedAt` | `startAt` |
| `durationSec` | `endAt - startAt`（有 `endAt` 时） |
| `unit` | 规范化后的 UCUM |
| `payload` | `{kind, value, unit, startAt, endAt, source, evidence, confidence, metric?, waveform?}` |
| `metadata` | `{importSource:"import-agent", externalId, agentSessionId, confidence, evidence}` |
| `provenance` | `{fileNameHash, fileHash, adapterVersion:"import-agent/1.0.0"}` |

去重键（幂等）：

```
externalId = "sha256:" + sha256(
    fileHash | sourceLabel | kind | startAt(UTC) | endAt(UTC) | canonical_json(value)
)
```

## 2. kind 表

| kind | recordType 后缀 | value 形状 | 规范单位 | 范围/约束 |
|---|---|---|---|---|
| `steps` | `steps` | number | `count` | 0–200000 |
| `heart-rate` | `heart-rate` | number | `count/min` | 20–300 |
| `resting-heart-rate` | `resting-heart-rate` | number | `count/min` | 20–200 |
| `sleep` | `sleep` | string 阶段 | `1` | 见 §3；`endAt` 必填 |
| `body-mass` | `body-mass` | number | `kg` | 1–500 |
| `blood-pressure` | `blood-pressure` | `{systolic, diastolic}` | `mm[Hg]` | 收缩压 40–300，舒张压 20–200，收缩压 > 舒张压 |
| `spo2` | `spo2` | number | `%` | 0–100 |
| `stress` | `stress` | number | `1` | 0–100 |
| `workout` | `workout` | `{activity, durationSec, distanceM?, energyKcal?, avgHeartRate?}` | `1` | `activity` 必填；`endAt` 必填 |
| `respiratory-rate` | `respiratory-rate` | number | `count/min` | 2–80 |
| `body-temperature` | `body-temperature` | number | `Cel` | 25–45 |
| `blood-glucose` | `blood-glucose` | number | `mg/dL` 或 `mmol/L` | mg/dL 10–1000；mmol/L 0.5–60 |
| `hrv` | `hrv` | `{metric, value}` | `ms` / `%` / `ms2` / `1` | 见 §4 |
| `ecg` | （`org.eclipsehealth.ecg`） | `{samplingRate?, lead?, sampleCount?}` | `mV` | 必须带 `waveform`，见 §5 |
| `body` | `body` | 身体成分对象 | `1` | 见 §6，至少一个指标 |

## 3. sleep

`value` 是阶段字符串，允许：

`in-bed`、`awake`、`asleep`、`asleep-core`、`asleep-deep`、`asleep-rem`、`unknown`。

`endAt` 必填，`durationSec` 由起止时间计算。心率/呼吸等其它睡眠指标按各自的 kind 单独记录。

```json
{"kind":"sleep","value":"asleep-deep","unit":"1",
 "startAt":"2026-10-30T01:12:00+08:00","endAt":"2026-10-30T02:00:00+08:00",
 "source":{"kind":"device","device":"Apple Watch"},
 "evidence":{"file":"export.xml","locator":"line 8821","snippet":"SleepAnalysisAsleepDeep"},
 "confidence":0.9}
```

## 4. hrv

```json
{"kind":"hrv","value":{"metric":"rmssd","value":42.5},"unit":"ms", ...}
```

- `metric`：`rmssd`、`sdnn`、`pnn50`、`lf`、`hf`、`lf-hf-ratio`（其它 ≤ 32 字符也接受）。
- 数值 0–5000；单位别用错：`rmssd/sdnn` → `ms`，`pnn50` → `%`，`lf/hf` → `ms2`，
  比值 → `1`。

## 5. ECG

只有**文件里确实有采样表**时才允许 `kind=ecg`。采样可以写成 output 下的 CSV 或 float32：

```json
{
  "kind": "ecg",
  "value": {"samplingRate": 500, "lead": "II", "sampleCount": 15000},
  "unit": "mV",
  "startAt": "2026-10-30T08:00:00+08:00",
  "endAt": "2026-10-30T08:00:30+08:00",
  "source": {"kind":"device","device":"Apple Watch"},
  "evidence": {"file":"electrocardiograms/2026-10-30.csv","locator":"rows 2-15001"},
  "confidence": 0.99,
  "waveform": {
    "file": "ecg-2026-10-30.csv",
    "format": "csv",
    "column": 1,
    "timeColumn": 0,
    "unit": "mV",
    "lead": "II"
  }
}
```

- `waveform.file` 必须在 `<session>/output/` 下，相对路径、无 `..`。
- `format`：`csv`（默认）或 `f32`（little-endian float32）。
- `csv`：`column` 可以是 0 基列号或列名；`timeColumn` 可选（用于推断采样率）。
- 采样率：`waveform.samplingRate` 或 `value.samplingRate`；都没有时用 `timeColumn` 推断。
- 上限：5,000,000 点 / 64 MB；超出拒绝。
- 单位 `mV`、`uV`、`V` 会换算到 mV。
- 写入走现有波形管线（`storage.write_signal` + signal 表），一条记录可多导联（多次提案同
  `startAt` + 不同 lead 目前各成一条记录，v1 不支持多导联合并）。

**PDF/图片只有报告时禁止创建 `ecg`**：返回 `ecg_waveform_required`。只提取报告里的数值
（心率、血压、结论等）写成对应数值类记录。

## 6. body（身体成分）

`value` 是对象，至少一个字段：

| 字段 | 范围 | 单位 |
|---|---|---|
| `weightKg` | 1–500 | kg |
| `bodyFatPct` | 1–70 | % |
| `bmi` | 5–80 | 1 |
| `muscleMassKg` | 1–200 | kg |
| `waterPct` | 1–80 | % |
| `boneMassKg` | 0.1–20 | kg |
| `visceralFat` | 1–60 | 1 |
| `basalMetabolicRate` | 500–5000 | kcal/d |

单位字段固定 `1`；子字段各自带单位语义。

## 7. 单位别名

| 输入（不区分大小写） | 规范化 |
|---|---|
| `bpm`、`1/min`、`/min`、`counts/min` | `count/min` |
| `step(s)`、`counts` | `count` |
| `lb`、`lbs`、`pound(s)` | `[lb_av]` → 自动换算 kg |
| `mmHg`、`mm hg` | `mm[Hg]`（kPa 自动换算） |
| `percent` | `%` |
| `°C`、`c`、`celsius` | `Cel`（°F 自动换算） |
| `mg/dl` | `mg/dL` |
| `mmol/l` | `mmol/L` |
| `millisecond` | `ms` |
| `mv`、`uv`、`µv`、`v` | `mV` / `uV` / `V`（ECG 内部换算 mV） |

未知单位 → `invalid_record`，不硬猜。

## 8. 与现有导入器的关系

- 已有格式（Apple、小米、Samsung、华为、SCP-ECG、WFDB、EDF、CSV）仍走
  `/api/v1/imports/*` 的确定性适配器；Agent 导入是它们的补充，不替换。
- 两者写同一个 `records` / `signals` 表；`payload` 结构一致（`value/unit/startAt/endAt`）。
- Agent 记录的 `metadata.importSource = "import-agent"`，便于统计与区分。
