# C3 · 健康数据页：让 Apple/小米导入的记录可见

> 先读 `prompts/00-COMMON.md`、`reports/B4-health-import-report.md`，再读本文件。

## 背景

B4 已能把 Apple/小米的步数、心率、睡眠、体重、血压导入为 `org.eclipsehealth.health.*` 记录，但记录页只查 `recordType="org.eclipsehealth.ecg"`，导入的数据在 UI 里看不见。本任务补一个「健康数据」页面。

## 交付

### 1. 后端

- `api/records.py`：`GET /records` 增加 `recordTypePrefix` 查询参数（如 `org.eclipsehealth.health.`），与现有 `recordType` 互斥（同时给 → 422 `invalid_query`）；`total` 与分页一致。
- 测试：前缀过滤、分页/总数、互斥校验、空结果。

### 2. 前端页面

- 新建 `src/pages/health-data.tsx`：
  - 拉取 `recordTypePrefix=org.eclipsehealth.health.` 的记录；
  - 类型筛选：全部 / 步数 / 心率 / 睡眠 / 体重 / 血压（按 recordType 后缀映射）；
  - 时间筛选：近 7/30/90 天 / 全部；分页沿用现有 `RecordPage` 交互；
  - 每条显示：类型、值+单位、起止时间、来源（Apple/小米）、导入时间；血压显示 `收缩/舒张`；睡眠显示时长；
  - 空状态：提示「用 Apple 健康导出或小米 CSV 导入」，并给导入入口（复用现有 `useImport`）。
  - 不做图表；不点进 ECG 记录详情；行内展开显示 payload 摘要即可。
- `src/App.tsx` 增加 lazy 路由 `/health-data`；`src/lib/nav.ts` 增加「健康数据」导航项（图标用现有 Lucide，位置在「记录」之后）。
- `src/lib/api/{types,queries,client,adapters,mock}.ts`：`RecordListParams` 增加 `recordTypePrefix`；mock 支持前缀过滤；`useRecords` 已可用。
- 文案：`src/lib/i18n/**` 增加 `nav.healthData`、`healthData.*`（zh-CN/en-US）。

### 3. 验证

- 后端 `pytest backend/tests/api -q` 通过。
- `npm run build` 通过。
- 用 B4 的合成 Apple/小米夹具导入后（真实后端 + Vite），健康数据页显示对应条数；筛选/分页可用；亮/暗截图 `reports/screenshots/C3-health-data-*.png`，控制台 0 error。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/api/records.py`
- `backend/tests/api/test_records*.py`（只加前缀用例）
- `src/pages/health-data.tsx`（新建）
- `src/App.tsx`
- `src/lib/nav.ts`
- `src/lib/api/types.ts`、`queries.ts`、`client.ts`、`adapters.ts`、`mock.ts`
- `src/lib/i18n/**`（只新增 nav/healthData 键）

## 明确不做

- 不改 dashboard、records、import 组件、模块/助手/LLM。
- 不做图表、睡眠会话合并、华为/Zepp/Samsung。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\api -q
npm run build
```

报告 `reports/C3-health-data-report.md`，≤80 行。必须写清：前缀过滤行为、页面字段/筛选、真实导入验证、截图、未做项。
