# B4 · S2 多源健康数据直接导入（Apple 优先 + 小米）

> 先读 `prompts/00-COMMON.md`、`docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md`、`docs/INTERNAL_API_V1.md` 的 imports 段，再读本文件。

## 目标

按 S1 结论实现**直接导入我们应用**的首批解析器：Apple Health 导出（`export.xml/zip` + ECG CSV）与小米运动 CSV。不经过三星健康；不做 Health Connect。

## 交付

### 1. 后端适配器

- 新建 `importers/apple_health_adapter.py`：
  - 接受 `.zip`（内含 `export.xml` 与 `electrocardiograms/*.csv`）或单独 `.xml`；
  - 用 `xml.etree.ElementTree.iterparse` 流式解析，避免整文件进内存；
  - 映射：步数、心率、睡眠、体重、血压（correlation）、ECG（HKDataTypeIdentifierElectrocardiogram + 对应 CSV）；
  - ECG CSV：`time,voltage`（秒/伏特）→ 单导联信号，换算 mV；采样率从时间步长推断，缺省 512 Hz；
  - 非 ECG 数据写成记录：`recordType` 用 `org.eclipsehealth.health.<kind>`（如 `steps/heart-rate/sleep/body-mass/blood-pressure`），`payload` 含 `{value,unit,startAt,endAt,sourceApp?}`；`source.kind="import"`，`metadata.importSource="apple-health"`；
  - 去重：文件 sha256 + 记录 `metadata.externalId`（Apple `HKObject` UUID），重复导入跳过并计数；
  - 大文件给进度/上限；超过上限明确报错，不 OOM。
- 新建 `importers/xiaomi_adapter.py`：
  - 接受明文 `hlth_center_fitness_data.csv`（列 `Key,Time,Value`，Value 为 JSON）；按 Key 映射步数/心率/睡眠/体重；
  - 加密 ZIP 或未知列 → 明确 `encrypted_export` / `unsupported_xiaomi_export`，提示用户先解压；
  - 去重同上。
- `importers/registry.py` 注册两个适配器；`preview` 返回按类型计数与警告，`commit` 写记录/信号；不破坏现有 WFDB/CSV/EDF/SCP 适配器。

### 2. 前端导入引导

- `src/components/import/**`：导入对话框增加数据源选择：
  - 「Apple 健康导出（ZIP/XML）」「小米运动（CSV）」「通用 ECG 文件（现有流程）」；
  - 选择后显示该源的最少步骤摘要（来自 S1 文档）+ 上传；预览显示「将导入 N 条步数 / 心率 / 睡眠 / 体重 / 血压 / ECG」；
  - 提交后显示成功/跳过重复/失败计数；错误可读。
- 文案加到 `src/lib/i18n/**` 的 import 段（zh-CN/en-US）；不新增共享顶层键。
- 不做多步向导框架重构；复用现有 preview/commit 流程。

### 3. 文档状态

- 在 `docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md` 末尾追加「S2 实现状态」：已实现 Apple/小米、字段限制、未验证项。

### 4. 测试

- `backend/tests/imports/`：
  - 合成 Apple `export.xml`（含步数/心率/睡眠/体重/血压/ECG 引用）+ ECG CSV，断言记录数、单位、信号采样率、externalId 去重；
  - 加密 ZIP/缺 export.xml/坏 CSV → 明确错误码；
  - 小米合成 CSV：步数/心率/睡眠/体重；重复导入跳过；
  - 现有 imports 测试全绿。
- `npm run build` 通过；UI 用拦截或真实后端走一遍 Apple ZIP 预览/提交，截图 `reports/screenshots/B4-import-*.png`。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/importers/**`
- `backend/tests/imports/**`
- `backend/tests/fixtures/imports/apple-health/**`（新建）
- `backend/tests/fixtures/imports/xiaomi/**`（新建）
- `src/components/import/**`
- `src/lib/i18n/**`（只新增 import 段键）
- `docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md`（只追加 S2 状态）

## 明确不做

- 不做华为/Zepp/Samsung 解析器（等用户样本）；不做 Health Connect。
- 不改 dashboard/records 页面（B1 所有权）；不改 modules/assistant/llm。
- 不做 AES 解密；不新增依赖；不下载受限数据集；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\imports -q
npm run build
```

报告 `reports/B4-health-import-report.md`，≤80 行。必须写清：支持的 Apple 类型、记录类型/单位、去重键、错误码、真实测试输出、未验证项。
