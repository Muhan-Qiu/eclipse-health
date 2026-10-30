# 报告 · B4 S2 多源健康数据直接导入（Apple + 小米）

状态：完成

## 交付
- `importers/apple_health_adapter.py`：Apple `export.zip` / `export.xml` 流式解析（`iterparse`），映射步数、心率、睡眠、体重、血压（Correlation）、`electrocardiograms/*.csv`。
- `importers/xiaomi_adapter.py`：小米 `hlth_center_fitness_data.csv`（`Key,Time,Value`）解析步数/心率/睡眠/体重；加密 ZIP 与错误表头给明确错误码。
- `importers/persist.py`：批量入库 + 去重（整包 `provenance.fileHash`、逐条 `metadata.externalId`），单条失败计数不回滚已写入记录。
- `importers/api.py`：preview 增加 `recordCounts/totalRecords`；commit 增加 `created/skipped/failed/duplicateFile/recordCounts`，返回首个记录的 `recordId/record`。
- `importers/registry.py` / `limits.py` / `store.py`：注册两个适配器；上限与加密 ZIP 检测。
- 前端 `src/components/import/**`：数据源选择（Apple / 小米 / 通用 ECG）、最少步骤摘要、导入数量预览、成功/跳过/失败面板；新增 `health-import-api.ts` 读取扩展字段。
- `src/lib/i18n/**`：只在 `imports` 段新增 `sources` / `health` / 新错误码 / 新警告码（zh-CN、en-US）。
- `docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md`：追加 §10「S2 实现状态」。

## 支持的 Apple 类型与记录形态
- `HKQuantityTypeIdentifierStepCount` → `org.eclipsehealth.health.steps`，单位 `count`。
- `HKQuantityTypeIdentifierHeartRate` → `org.eclipsehealth.health.heart-rate`，单位 `count/min`（`count/s` 自动 ×60）。
- `HKQuantityTypeIdentifierBodyMass` → `org.eclipsehealth.health.body-mass`，单位 `kg`（`lb`/`g` 换算）。
- `HKCategoryTypeIdentifierSleepAnalysis` → `org.eclipsehealth.health.sleep`，`value` 为 `in-bed/asleep/asleep-core/asleep-deep/asleep-rem/awake`，`durationSec` 保存时长。
- `HKCorrelationTypeIdentifierBloodPressure` → `org.eclipsehealth.health.blood-pressure`，`value={systolic,diastolic}`，单位 `mm[Hg]`（`kPa` 换算）。
- `HKDataTypeIdentifierElectrocardiogram` + CSV → `org.eclipsehealth.ecg`，单导联 I、mV（伏特 ×1000）；采样率按时间步长推断，失败按 512 Hz 并告警。
- payload 统一为 `{value, unit, startAt, endAt, sourceApp?}`；`source.kind="import"`；`metadata.importSource="apple-health" | "xiaomi-mi-fitness"`。

## 去重键
- 整包：`provenance.fileHash`（上传文件 sha256）已存在 → 全部跳过并返回 `duplicateFile=true`。
- 逐条：`metadata.externalId`。Apple 优先 `uuid` 属性，缺失时用类型/起止/值/来源指纹；ECG 用 CSV 内容 sha256；小米用 `Key+Time+Value` 指纹。

## 错误码
`encrypted_export`、`unsupported_xiaomi_export`、`apple_export_missing`、`apple_export_empty`、`invalid_apple_export`、`invalid_ecg_csv`、`import_too_many_records`（默认 20,000 条 / 200 段 ECG）。

## 验证（真实输出）
- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\imports` → `111 passed in 6.93s`（原有 99 + 新增 12）
- `npm run build` → `✓ built in 2.93s`，无 TS 错误。
- UI 实测（Playwright + 本机 Chrome，真实后端 8765）：
  - Apple ZIP 预览显示「将导入 8 条记录」（步数 2/心率 2/睡眠 1/体重 1/血压 1/心电图 1），提交成功 8、跳过 0、失败 0（另有一组合成数据含未映射的活动能量记录，预览 9 条、成功 8 条，验证跳过计数）。
  - 小米 CSV 预览/提交成功 6；再次导入同文件返回跳过 6。
  - 控制台 error 数：0。
  - 截图：`reports/screenshots/B4-import-source-light.png`、`B4-import-apple-preview-light.png`、`B4-import-apple-done-light.png`、`B4-import-source-dark.png`、`B4-import-xiaomi-preview-dark.png`、`B4-import-xiaomi-done-dark.png`。
- 单测覆盖：记录数/单位/ECG 采样率/externalId、整包重复、缺 export.xml、坏 ECG CSV、坏 XML、kPa 换算、小米列错误、加密 ZIP、适配器注册。

## 未做 / 偏离
- 未用真实 Apple/小米导出包验证；ECG CSV 列名按 `time,voltage` + `Date:` 元数据行实现（合成夹具验证）。
- 睡眠逐条阶段导入，未合并睡眠会话；Apple `InBed` 等保留为独立记录。
- 小米 `Value` 为列表的行跳过；未知 Key/坏 JSON 逐行计数警告。
- 不做 AES 解密、不做 Health Connect、不做 Huawei/Zepp/Samsung 健康数据。
- 为读取新增字段，导入组件内使用了一个局部 raw fetch 客户端；未改共享 `src/lib/api/types.ts` / `client.ts`（见跨区需求）。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 建议后续把 `recordCounts/totalRecords/created/skipped/failed/duplicateFile` 正式补进 `src/lib/api/types.ts` 与 `client.ts` 的 imports 类型，删除局部 raw 客户端。
- 真实 Apple/小米导出样本到位后，替换合成夹具并复核 ECG CSV 元数据、睡眠阶段与小米 JSON 结构。

## 需要指挥官决策
- 睡眠是否要在后续批次合并为「睡眠会话」记录（当前保留每条阶段）。

## 建议下一批
- 华为/Zepp/Samsung 健康数据适配器（等待脱敏样本）；睡眠会话聚合；健康数据记录列表的专用展示。
