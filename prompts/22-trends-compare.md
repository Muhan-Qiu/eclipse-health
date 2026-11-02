# B3-02 · 趋势 + 记录状态 + 两条记录对比

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B3 功能
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 你是本批的**前端共享层所有者**：`App.tsx`、`src/lib/api/*`、`src/lib/i18n/*` 由你改；B3-03/04 只加 feature 目录。

## 1. 必读

- `docs/INTERNAL_API_V1.md`：§1 记录、§4 数据形状、§5 视图模型。
- `docs/DATA_SCHEMA_V1.md`：§6 AnalysisResult、§7 Measurement（测量码）。
- `docs/V3_FEATURE_BACKLOG.md`：D1 记录库、D3 趋势、D4 对比、B6 节律条（可选）。
- `docs/UI_COMPONENT_SPEC_V1.md`：§2 布局、§7 图表。
- `reports/B2-03-report.md`、`reports/B2-01-report.md`。
- 代码：`src/pages/trends.tsx`、`src/pages/records.tsx`、`src/lib/api/`、`src/components/records/`、`backend/src/.../api/records.py`、`db/analysis_repo.py`。

## 2. 目标

- 记录列表能看出「未分析 / 分析中 / 已分析 / 失败」，不用逐条打开。
- 趋势页把 HR、HRV、异常比例按时间画出来，能点回记录。
- 选两条记录并排比较波形与指标。

## 3. 你必须交付

### 后端

1. **记录列表状态**
   - `GET /records` 每条增加可选字段：`latestAnalysisStatus`（`none|queued|running|completed|failed`）、`latestAnalysisId`、`latestAnalyzedAt`。
   - 用一条聚合查询/子查询实现，禁止逐行 N+1；软删除记录不参与。
   - 保持现有分页/过滤形状不变；旧字段不动。
2. **趋势 API**
   - `GET /trends?metrics=heart_rate_mean,rmssd,sdnn,n_ratio&from=&to=&memberId=`：
     ```json
     {
       "series": [
         {
           "metric": "heart_rate_mean",
           "label": "平均心率",
           "unit": "bpm",
           "ucum": "/min",
           "points": [{ "t": "...", "value": 75.5, "recordId": "rec_...", "analysisId": "ana_..." }],
           "summary": { "min": 62, "max": 91, "mean": 74.2, "count": 12 }
         }
       ]
     }
     ```
   - 只取 `completed` 分析、非删除记录；缺值的记录跳过，不用 0 填充。
   - 默认最近 30 天；`from/to` 为 RFC 3339；`memberId` 可选（首版单成员）。
   - 指标白名单：§7 核心码；未知指标 422 `unknown_metric`。
3. **对比 API（可选但推荐）**
   - `GET /records/compare?ids=rec_a,rec_b`：2–4 条记录，返回 `{ records: [...], analyses: [{ recordId, latestCompleted: {...summary+measurements} }] }`；只返回最新完成分析。
   - 若实现成本高，可让前端用现有 `GET /records/{id}` + `GET /records/{id}/analyses` 并发取，报告说明。
4. **测试**：状态聚合（无分析/运行中/完成/失败/软删除）、趋势过滤/排序/空数据/未知指标、对比参数校验。

### 前端

1. **共享层（你独占）**
   - `src/App.tsx`：新增 `/compare` 路由；`/trends` 保持。
   - `src/lib/api/{client,types,queries,adapters}.ts`：新类型/查询；保持现有接口兼容。
   - `src/lib/i18n/{zh-CN,en-US}.ts`：`trends.*`、`compare.*`、`recordStatus.*` 文案；B3-03/04 用 feature-local bundle，不会改这两个文件。
2. **记录列表**
   - 状态徽标（颜色 + 图标 + 文字）；已分析显示最近分析时间；点击仍进详情。
   - 批量选择两条进入对比（复选框 + 「对比」按钮），不超过 2 条；移动端/窄屏不塌。
3. **趋势页**
   - 指标多选（默认 HR + RMSSD）；范围 7/30/90/全部；Recharts 折线/散点；悬停显示值与日期；点数据点跳记录详情；空状态引导先做一次分析；加载/错误重试。
   - 图表要遵守设计令牌（线色用 `--eh-signal`/`--eh-accent`，网格低对比）；暗色可读。
   - 可选：异常比例用面积图；不做预测/拟合。
4. **对比页**
   - 选择两条记录（从列表带入或页内选择）；并排波形（复用 `WaveformViewer` 或缩略版）+ 指标表（HR/RMSSD/SDNN/N/SVEB/VEB/F/质量/时长）；差异用中性色标注，不判断「更好/更差」。
   - 无分析时提示先分析；单条记录时提示再选一条。
5. **质量**：i18n 全量、键盘可达、1080×700 不横向溢出、无 console error；截图 3 张到 `reports/screenshots/`（趋势亮/暗、对比）。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/trends/**
backend/src/eclipse_health_backend/api/trends.py
backend/src/eclipse_health_backend/api/records.py          # 仅加 latestAnalysis* 字段
backend/tests/trends/**
src/App.tsx
src/lib/api/client.ts
src/lib/api/types.ts
src/lib/api/queries.ts
src/lib/api/adapters.ts
src/lib/i18n/zh-CN.ts
src/lib/i18n/en-US.ts
src/pages/trends.tsx
src/pages/compare.tsx
src/components/trends/**
src/components/records/record-row.tsx
src/components/records/record-list*.tsx（如需）
```

不要动：`src/pages/reports.tsx`、`src/pages/assistant.tsx`、`src/features/**`、`src-tauri/**`、`backend/analyses*`、`backend/importers/**`、`modules/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\trends -q
npm run build
# 后端 + dev server，造 2–3 条不同日期的分析记录，走趋势/对比
```

报告写：状态聚合实现、趋势口径（哪些测量码/单位）、对比交互、截图路径、未做项。

## 6. 明确不做

报告 PDF/PNG（B3-03）、LLM（B3-04）、节律条 Overview（除非时间充裕，放 B4）、12 导联、预测/拟合、跨成员对比、导出 CSV。
