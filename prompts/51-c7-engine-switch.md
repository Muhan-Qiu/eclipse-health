# B5-02 · C7 通用引擎列表 + 选择 + 重新分析

> 先读 `prompts/00-COMMON.md`，再读本文件。项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 任务范围

把原始 44 项里的 C7 收口：分析引擎不再在前后端写死 `"cardia"`，而是由后端注册表提供列表，UI 可选择并重新分析。**本批只注册 Cardia 一个引擎**；第二引擎留给平台 #1 的 ONNX loader，不要自己造模型。

### 后端

1. 新增引擎注册表（建议 `backend/src/eclipse_health_backend/analysis_service/engines.py`）：
   - `EngineDescriptor`：`id`、`name`、`moduleId`、`modelId`、`modelVersion`、`available`、`reason`（不可用时的用户可读原因）。
   - `list_engines()` 返回注册表；`get_engine(id)` 找不到返回 None。
   - 内置注册 `cardia`，数据来自 `bridge.py` 的常量；保持 `CARDIA_ENGINE` 等导出不变，避免破坏现有导入。
2. `backend/src/eclipse_health_backend/api/analyses.py`：
   - 删除写死的 `SUPPORTED_ENGINES = ("cardia",)`，改为注册表校验；未知引擎仍返回 400 `unknown_engine`，`details.supported` 来自注册表。
   - 新增 `GET /api/v1/analyses/engines`（注意路由顺序，不要被 `/{analysis_id}` 吞掉）→ `{"items": [EngineDescriptor...]}`。
   - 保留现有 `GET /api/v1/analyses/engine`（Cardia 运行状态）不变，供旧 UI 与助手使用。
   - 重新分析：确认 `POST /records/{id}/analyses` 在已有 `completed|failed` 分析时会新建一条（现有逻辑应已如此）；补测试。若同记录有 `queued|running` 仍幂等复用，不要改变。
3. 测试（`backend/tests/analyses/**`）：
   - engines 列表含 cardia 且字段完整；
   - 未知 engine 400 + supported 列表；
   - completed 后再次 POST 指定 engine 会创建新 analysis；
   - 现有分析 API 测试全绿。

### 前端

1. 新建 `src/features/analysis/` 特性目录（本地类型 + fetch，不改 `src/lib/api/*`，避免与 B5-01 冲突）：
   - `engine-catalog.ts`：用 `baseUrl`（从 `@/lib/api/client` 导出）请求 `/analyses/engines`，返回本地 `EngineDescriptor[]`；错误用 `ApiError` 或普通 Error。
   - `use-engine-catalog.ts`：`useQuery` 风格或简单 `useEffect` 均可，带 loading/error。
2. `src/pages/record-detail.tsx`：
   - 去掉 `startAnalysis` 里的 `engine: "cardia"` 硬编码；用选中的 engine（默认第一个可用引擎）。
   - 引擎 >1 时显示 `Select`（shadcn/ui 现有组件）；只有 1 个时显示只读文本 + 说明「更多引擎可通过安装分析模块获得」。
   - 分析失败/完成后提供「重新分析」按钮；重新分析可重新选择引擎（若 >1）。进行中保持禁用。
3. `src/components/records/analysis-panel.tsx`：
   - 在合适位置显示当前分析的 engine/model 版本（已有模型卡可复用）。
   - 重新分析入口不要和现有重试/刷新按钮混淆；文案走 i18n。
4. 文案：`src/lib/i18n/**` 只新增 `analysis.engine.*` / `recordDetail.reanalyze*` 键（B5-01/B5-03 也改 i18n，若发现冲突只保留自己的键并写进报告）。
5. 前端测试：`npm run build` 通过；手工验证：单引擎时无选择器但显示说明；mock 一个第二引擎（仅测试时）时选择器出现且重新分析请求带对应 engine。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/analysis_service/**`
- `backend/src/eclipse_health_backend/api/analyses.py`
- `backend/tests/analyses/**`
- `src/pages/record-detail.tsx`
- `src/components/records/analysis-panel.tsx`
- `src/features/analysis/**`（新建）
- `src/lib/i18n/**`（只新增本任务键）

## 明确不做

- 不实现第二个分析引擎、不改 ONNX/Cardia 推理代码、不改 `bridge.py` 的 Cardia 行为（可加只读导出）。
- 不改 `src/lib/api/**`（B5-01 所有权）、不改 records/profile/settings 页面。
- 不做平台 #1–#4、模块贡献 loader、自动更新。
- 不新增 Python/npm 依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\analyses -q
npm run build
```

UI 额外：亮/暗各一张截图放 `reports/screenshots/B5-02-*.png`；控制台 0 error。

## 报告

写 `reports/B5-02-report.md`，≤80 行，结构按 `00-COMMON.md` §7。必须写清：注册表 API 形状、重新分析行为、单引擎 UI 的真实表现、测试输出、未做项。
