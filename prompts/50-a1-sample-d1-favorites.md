# B5-01 · A1 首次引导/真实示例记录 + D1 收藏与筛选

> 先读 `prompts/00-COMMON.md`，再读本文件。项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 任务范围

把原始 44 项里的 A1、D1 收口。两件事同属记录域，按顺序做；A1 先做，D1 后做。

### A1：首次启动引导 + 真实示例记录

目标：用户第一次打开应用，能一键生成一条**真实导入**的示例记录，并直接进入记录详情走完分析流程；不是 `VITE_USE_MOCK` 演示数据。

要求：

1. 后端新增只读白名单样本导入端点，建议 `POST /api/v1/imports/samples/{sample_id}`：
   - 白名单：`mitdb-100`、`mitdb-200`、`mitdb-208`，对应 `backend/resources/samples/{100,200,208}.{hea,dat,atr}`（WFDB）。
   - 内部复用现有 `importers` 的 preview/commit 逻辑，不要复制解析器；`sample_id` 不在白名单 → 404 `sample_not_found`。
   - 记录 `metadata` 标记 `sampleId` 与 `isSample: true`；`source.kind="import"`；不写用户文件名。
   - 端点返回 `{recordId, analysisId?}`；可选参数 `startAnalysis=true` 时后台自动发起 Cardia 分析（复用现有 analysis service），失败只影响 analysis，不阻断记录创建。
   - 同一成员重复调用允许生成新记录，但前端引导按钮应在已有 `isSample` 记录时显示「打开示例」而不是重复生成。
2. 前端 `src/pages/dashboard.tsx`：
   - 空状态/首次引导卡片加「载入示例记录」按钮；成功后 invalidate 记录/分析查询并 `navigate(/records/{id})`。
   - 已存在示例记录时按钮变为「打开示例记录」，直接跳到最近一条示例。
   - 文案走 i18n（zh-CN / en-US），说明「示例数据来自 MIT-BIH，仅用于体验流程，非诊断」。
   - 保持现有设计令牌与卡片结构，不新增大色块/玻璃拟态。
3. 示例记录在列表/详情用现有 `DemoBadge` 或新增「示例」徽标标识；不要伪装成用户数据。
4. 后端测试：白名单成功创建记录+信号、未知 sample 404、重复调用生成两条不同记录、`startAnalysis=true` 不阻断记录创建（可 mock 分析服务）。

### D1：收藏 + 筛选

目标：记录可收藏、可只看收藏；自动保存与时间/设备筛选已存在，不要重做。

要求：

1. 领域模型：`HealthRecord`/`RecordFields` 增加 `favorite: bool = False`；`RecordUpdate` 增加可选 `favorite`；写入 `records.data` JSON，不需要数据库迁移。
2. API：
   - `GET /api/v1/records` 增加 `favorite: bool | None` 查询参数；用 SQLite `json_extract(records.data, '$.favorite')` 过滤（SQLAlchemy `func.json_extract`），必须与分页/总数一致。
   - `PATCH /api/v1/records/{id}` 支持只改 `favorite`，返回完整记录。
   - 若 `json_extract` 在本机 SQLite 不可用：改用 Python 侧过滤并在报告中说明分页影响；**不要**做破坏性迁移。
3. 前端：
   - `src/components/records/record-row.tsx` 增加星标按钮（星形图标，`aria-pressed`），点击调用 PATCH 并乐观更新；键盘可操作。
   - `src/pages/records.tsx` 增加「只看收藏」筛选（与现有筛选可叠加），空结果用现有 EmptyState 文案。
   - `src/lib/api/{types,queries,client,adapters,mock}.ts` 增加 favorite 字段/参数/mutation；mock 也要支持。
   - 不要求改记录详情页（B5-02 正在改，避免冲突）。
4. 测试：后端收藏 PATCH、favorite 筛选+分页、默认 false；前端 build 通过。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/importers/**`
- `backend/src/eclipse_health_backend/api/records.py`
- `backend/src/eclipse_health_backend/api/__init__.py`（仅当必须挂新路由）
- `backend/src/eclipse_health_backend/domain/models.py`
- `backend/src/eclipse_health_backend/db/repositories.py`
- `backend/tests/imports/**`、`backend/tests/api/test_records*.py`
- `src/pages/dashboard.tsx`、`src/pages/records.tsx`
- `src/components/records/record-row.tsx`
- `src/lib/api/types.ts`、`queries.ts`、`client.ts`、`adapters.ts`、`mock.ts`
- `src/lib/i18n/**`（只新增本任务键；B5-03 也会改 i18n，若发现冲突只保留自己的键并写进报告）

## 明确不做

- 不改 `record-detail.tsx`、`analysis-panel.tsx`（B5-02 所有权）。
- 不做多源健康数据导入（Apple/华为/小米/Samsung）。
- 不做 C7 引擎选择、平台 #1–#4、自动更新。
- 不新增 Python/npm 依赖；不改 `docs/`、`prompts/`、`uploads/`。
- 不 commit。

## 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\imports backend\tests\api -q
npm run build
```

UI 额外：亮/暗各一张截图放 `reports/screenshots/B5-01-*.png`；控制台 0 error。

## 报告

写 `reports/B5-01-report.md`，≤80 行，结构按 `00-COMMON.md` §7。必须写清：示例端点路径、收藏存储方式与筛选 SQL、真实测试输出、未做项。
