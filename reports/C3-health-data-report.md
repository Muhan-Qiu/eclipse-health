# 报告 · C3 健康数据页（Apple/小米导入记录可见）

状态：完成

## 交付
- 后端 `api/records.py`：`GET /records` 新增 `recordTypePrefix`（大小写敏感的前缀匹配，`record_type LIKE '<prefix>%'`）；与 `recordType` 同时给出 → 422 `invalid_query`；空字符串视为未传。`total` 与分页复用同一组 conditions。
- `backend/tests/api/test_records.py`：新增 4 个用例（前缀过滤、分页/total、互斥校验、空前缀结果）。
- 前端 `src/pages/health-data.tsx`（新建）：
  - 拉取 `recordTypePrefix=org.eclipsehealth.health.`；类型筛选为具体类型时改用 `recordType`（与后端互斥约定一致），保证服务端分页 total 正确。
  - 类型：全部/步数/心率/睡眠/体重/血压（recordType 后缀映射）；时间：近 7/30/90 天/全部；分页交互沿用记录页（上一页/下一页/第 x / y 页）。
  - 每条显示：类型、值+单位（步数「步」、心率 bpm、体重 kg、血压 `收缩/舒张 mmHg`、睡眠阶段+时长）、起止时间（起止相同则只显示开始）、来源（Apple 健康/小米运动）、导入时间（`createdAt`）。
  - 行内 `<details>` 展开 payload 摘要：value/unit/startAt/endAt/sourceApp + metadata.importSource/externalId。
  - 空状态：「还没有健康数据」+「导入健康数据」按钮，复用 `useImport().openPicker`；筛选无结果时单独给「清除筛选」。
- `src/App.tsx`：lazy 路由 `/health-data`；`src/lib/nav.ts`：「健康数据」放在「记录」之后，图标 `HeartPulse`。
- API 层：`RecordListParams.recordTypePrefix`（contract.ts）；`client.ts` 传参；`mock.ts` 支持前缀过滤并预置 35 条健康数据（7 天 × 5 类，便于演示分页）；`types.ts` 增加 `HealthRecordKind`/`HealthRecordPayload`；`adapters.ts` 增加 `healthKindOf/healthRecordType/toHealthRecordView/normalizeSleepStage`；`queries.ts` 新增 `useHealthRecords`（返回原始 `RecordPage`，因列表摘要不含 payload）。
- i18n：`nav.healthData`、`healthData.*`（zh-CN/en-US 全量对齐）。

## 验证（真实输出）
- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\api -o addopts="" -q` → `41 passed in 3.49s`
- `npm run build` → `✓ built in 6.10s`，无 TS 错误。
- 真实后端（`EH_DATA_DIR` 临时目录，端口 8765）+ Vite（1420）：
  - 用 B4 合成夹具（`tests/fixtures/imports` 的 export_builder/fitness_builder，追加 20 条 9 月步数以便测分页）经 REST 导入：Apple `created=28`（ecg1/steps22/heartRate2/bodyMass1/bloodPressure1/sleep1）、小米 `created=6`；`recordTypePrefix=org.eclipsehealth.health.` total=33，全库 total=34。
  - 页面显示 `20 / 33 条`、`第 1 / 2 页`；下一页 `13 / 33 条`、`第 2 / 2 页`；类型「睡眠」→ `2 / 2 条`、`第 1 / 1 页`；时间「近 7 天」→ `13 / 13 条`，与手算一致；「近 90 天」→ 33。
  - 睡眠阶段显示正确（Apple `asleep-core`→核心睡眠，小米 `deep`→深度睡眠）；血压 `120/80 mmHg`；来源徽标 Apple 健康/小米运动；payload 展开正常。
  - 空状态：软删除临时库中 33 条健康记录后重载，显示 `0 / 0 条` + 空状态文案，点击「导入健康数据」弹出数据源选择（Apple/小米/通用 ECG）。
  - 控制台 error 数：0（含导航、筛选、翻页、展开、导入弹窗）。
  - 截图：`reports/screenshots/C3-health-data-light.png`、`C3-health-data-dark.png`（1440×1000，含展开的 payload）。
- 未 commit；验证用后端/Vite 进程已停止，临时数据目录在系统 TEMP，不触碰 `backend/.data`。

## 未做 / 偏离
- `RecordListParams` 实际定义在 `src/lib/api/contract.ts`（不在任务提示词列出的 types.ts），因此额外改了 contract.ts，一行字段。
- 未改共享的 `useRecords`（返回 RecordSummary，丢 payload）；新增 `useHealthRecords` 满足页面需求。
- 睡眠阶段做了别名归一（`deep/light/rem/inbed` → Apple 命名），否则小米记录显示「未知阶段」。
- 未做图表、睡眠会话合并、ECG 详情跳转、华为/Zepp/Samsung。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 导入对话框健康数据成功面板的「查看记录」仍跳 `/records`（`src/components/import/**` 不在本任务所有权），可择机改为 `/health-data`。
- B4 报告中提到的 imports 扩展字段（recordCounts/created/skipped/failed）仍走局部 raw 客户端，未并入共享类型。

## 需要指挥官决策
- 无。

## 建议下一批
- 睡眠会话合并与按天聚合视图；健康数据行内编辑/删除；健康数据导出（CSV）。
