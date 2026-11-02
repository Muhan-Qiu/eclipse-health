# 报告 · B5-01 A1 首次引导示例记录 + D1 收藏与筛选

状态：完成

## 交付

### A1 示例记录
- 新增 `POST /api/v1/imports/samples/{sampleId}`（`importers/api.py`），白名单 `mitdb-100/200/208`，
  未知 ID → 404 `sample_not_found`；请求体可空：`{memberId?, capturedAt?, timezone?, startAnalysis?}`，
  返回 `{recordId, analysisId?}`。`memberId` 缺省时用默认成员「本人」。
- 解析复用现有 WFDB 适配器（`registry.detect` + `adapter.parse`），未复制解析器；
  记录写入抽到新模块 `importers/persist.py::create_record_from_parsed`，原 `commit` 端点改为调用它，
  两条链路共用同一段落库逻辑。
- 记录标记 `metadata.sampleId`、`metadata.isSample=true`，`source.kind="import"`，
  `provenance.fileNameHash=""`（不写用户文件名）。重复调用生成新记录，未去重。
- `startAnalysis=true` 时调用现有 `AnalysisService.submit`；异常被捕获并记 warning，
  记录仍 201 返回，`analysisId=null`。
- 前端仪表盘「载入示例记录」引导卡：无示例 → 按钮载入并 `navigate(/records/{id})`；
  已有示例 → 文案变「打开示例记录」直接跳转。文案 zh-CN/en-US 均注明 MIT-BIH、非诊断。
- 列表/详情行使用新增「示例」徽标（`records.sampleBadge`，虚线描边，不冒充用户数据）。

### D1 收藏
- `RecordFields.favorite: bool = False`（写入 `records.data` JSON，无迁移）；`RecordUpdate.favorite` 可单独 PATCH。
- `GET /api/v1/records?favorite=true|false`：`coalesce(json_extract(records.data,'$.favorite'),0)` 过滤，
  与 `total`/分页同一条 `conditions`，旧记录缺键按未收藏处理。
- 行内星标按钮：原生 `button` + `aria-pressed`，`useToggleFavorite` 乐观更新所有记录列表缓存，失败回滚。
- 记录页新增「只看收藏」按钮，与时间/设备/标签筛选叠加；无结果走既有 EmptyState；后端过滤，计数与分页一致。
- mock 客户端同步支持 `favorite` 字段、筛选、PATCH 与示例导入；`RecordSummary` 增加 `favorite`/`isSample`。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend` → All checks passed。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\imports backend\tests\api -q` → **136 passed in 8.67s**。
  新增用例：示例创建记录+多导联信号+原始波形长度、未知 sample 404、重复导入两条不同记录、
  `startAnalysis` 成功返回 analysisId、分析抛错仍 201 且记录可读；收藏默认 false、PATCH 仅改 favorite、
  favorite 筛选 total/offset 一致。
- `npm run build` → 通过（4.76s；仅有既有 chunk 体积提示）。
- 截图（`reports/screenshots/`，1440×1100，headless Chrome）：`B5-01-dashboard-light.png`、
  `B5-01-dashboard-dark.png`、`B5-01-records-light.png`、`B5-01-records-favorites-light.png`、
  `B5-01-records-dark.png`、`B5-01-sample-record-light.png`；控制台 0 error。
- 端到端实跑：真实后端 + Vite，点「载入示例记录/打开示例记录」→ `#/records/rec_...`；
  星标置位后开启「只看收藏」显示 1/1。

## 未做 / 偏离
- 仪表盘判断「已有示例」只看当前 `useRecords(limit:5)` 的首屏 5 条；若示例已沉到第 6 条以后，
  按钮会再次生成（后端允许重复，不阻断）。后端暂无 `isSample` 查询参数。
- mock 模式的示例导入不自动发起分析（只返回 recordId），与真实后端行为略不同。
- i18n 保留了旧的 `dashboard.guide.example*` 键（已不再引用），避免与 B5-03 的 i18n 改动冲突。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 首次 `npm run build` 失败于 `analysis-panel.tsx`（B5-02 在途改动），未修改该目录；稍后重跑已通过。
- Playwright MCP 浏览器被其他 Agent 占用（profile 锁），本次截图改用 headless Chrome + CDP 脚本完成，
  未终止他人浏览器。
- 后端 8765 / Vite 1420 仍由本任务启动并运行中，供并行批次共用；验收后可关闭。

## 需要指挥官决策
- 示例记录当前默认仅按需 `startAnalysis=true`（仪表盘按钮传 true）。是否要在示例记录上固定提示「非诊断」的更强标记，待 UI 批次统一。

## 建议下一批
- 若希望「打开示例」判断准确，给 `GET /records` 加 `isSample` 过滤参数（后端小改，前端一次查询）。
- B5-02 完成后在记录详情页展示「示例」徽标与收藏状态，保持与列表一致。
