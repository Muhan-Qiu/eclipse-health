# B2-03 · UI 端到端：记录详情 + 波形 + 分析结果

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B2 贯通
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：把 B1 的漂亮外壳接到真后端，完成第一条可演示链路；不要重做设计系统。

## 1. 必读

- `docs/INTERNAL_API_V1.md`：全部（尤其 §2 导入、§3 分析、§5 视图模型）。
- `docs/DATA_SCHEMA_V1.md`：§4–§8。
- `docs/UI_COMPONENT_SPEC_V1.md`：§2 布局、§3 组件、§7 图表、§8 可访问性。
- `docs/V3_FEATURE_BACKLOG.md`：A2 拖拽、B1–B4 波形、C1–C5 分析结果、G2 参数校正。
- `reports/B1-04-report.md`、`reports/01-backend-core-report.md`、`reports/03-cardia-engine-report.md`。
- 现有代码：`src/components/layout/`、`src/pages/`、`src/lib/api/`、`src/index.css`。

## 2. 目标

- 记录列表/详情接真 API；导入文件；发起分析；轮询状态；展示真实波形、R 峰、心搏、质量段、测量与警告。
- 保留 mock 作为 `VITE_USE_MOCK=true` 的降级，但默认走真实 API；UI 上不得把真实数据标成「示例」。
- 不实现趋势/报告/LLM/模块安装。

## 3. 你必须交付

1. **API 层**
   - `src/lib/api/client.ts`：fetch 封装、超时、统一错误、`ApiError`；base `http://127.0.0.1:8765/api/v1`（`VITE_API_BASE` 可覆盖）。
   - `src/lib/api/adapters.ts`：`HealthRecord -> RecordSummary` 映射（见契约 §5）；`AnalysisResult` 类型与后端 camelCase 对齐。
   - 查询：`records.list/get`、`records.signal`（ArrayBuffer → Float32Array）、`analyses.start/get/list`、`engine.status`、`imports.preview/commit`。
   - TanStack Query：合理 `staleTime`、分析轮询（1s，完成/失败即停）、错误重试只对网络错误。
2. **记录列表**
   - 真实分页、按时间/设备/标签过滤（前端或 API 参数）；加载骨架、空状态、错误重试；行内显示日期、设备、导联、采样率、时长、标签；点击进入详情。
3. **记录详情**
   - 顶部：日期/设备/导联/采样率/时长/标签/备注；软删除入口（二次确认）。
   - **波形**：uPlot；从 `/records/{id}/signal?lead=` 读 float32；按像素 min/max 降采样；滚轮缩放、拖拽平移（B1）；R 峰竖线/点；点击单搏显示 `probabilities`（B2）；质量段背景色（B4）；导联切换（单导联优先）；加载/空/错误。
   - **分析面板**：引擎状态（warming 时按钮禁用 + 原因）、「开始分析」/「重新分析」、阶段进度（C1）、摘要卡（C2：心率/HRV/异常比例/一句话）、测量值列表 + 问号解释（C3）、置信度/域外警告（C4）、类比例条（N/SVEB/VEB/F）、模型卡折叠（C6）、非诊断声明。
   - 分析失败：显示 `error.code` 的 i18n 文案 + 重试；不吞错。
4. **导入**
   - 全局拖拽（任意页面）与按钮选择文件；调用 preview → 参数校正弹窗（采样率/导联/单位/极性，G2）→ commit → 跳转详情。
   - 预览波形（前 2000 点）；显示自动识别结果与 `requires`；未知格式/损坏文件给出可读错误。
5. **仪表盘**
   - 最近记录改为真实数据；指标概览取最近一条完成分析的测量；无数据回退空状态；mock 仅作为开发降级。
6. **质量**
   - 全量 i18n（zh-CN/en-US）；键盘可达；颜色 + 图标 + 文字三重表达异常；尊重减少动效；1080×700 不塌。
   - 不引入新依赖（uPlot、TanStack Query 已装）；不写死颜色。
7. **E2E 与截图**
   - 启动后端（B2-01 完成后）+ `npm run dev`，用 Playwright 走：导入 `backend/resources/samples/100.hea`（或预处理好的 payload）→ 提交 → 打开记录 → 分析 → 看到结果。
   - 引擎冷启动可能 150s，等待/超时写清楚；若 B2-01 尚未 ready，用「API 形状 mock」验证 UI，并在报告标注哪段未真连。
   - 截图：`reports/screenshots/B2-03-record-light.png`、`B2-03-analysis-light.png`、`B2-03-analysis-dark.png`、`B2-03-import-preview.png`。

## 4. 文件所有权（只能改这些）

```
src/**
index.html 边界：不改 <title>/favicon（B2-04 所有）
```

具体：`src/pages/**`、`src/components/**`（除 `src/components/layout` 可微调）、`src/lib/**`、`src/index.css`、`src/App.tsx`。

不要动：`src/main.tsx`、`src/branding/**`、`public/brand/**`、`src-tauri/**`、`package.json`、`vite.config.ts`、`tsconfig.json`、`backend/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 与其他 Agent 的契约

- B2-01 提供分析/引擎 API；B2-02 提供导入 API。字段以 `docs/INTERNAL_API_V1.md` 为准；若实现有出入，写进报告并在适配层兼容，不要改后端。
- B2-04 负责 `src/main.tsx` 的启动动画/桌面壳；你保持 `<App/>` 可被它包裹，不要依赖 `main.tsx` 的内部结构。
- 新 logo 由 B2-04 提供；本批侧栏沿用现有标记，不要自己画新 logo。

## 6. 验收命令

```powershell
npm run build
npm run dev
# 另开后端：backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
```

报告写：真实连通的接口、E2E 步骤与截图、未真连/降级部分、性能观察（首次加载、波形渲染）、B3 待办。

## 7. 明确不做

启动动画/logo/托盘（B2-04）、趋势页真实数据、报告 PDF/PNG、LLM 助手、模块安装 UI、12 导联网格、节律条缩略导航（B3）、移动端布局。
