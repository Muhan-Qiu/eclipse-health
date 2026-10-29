# 报告 · B3-02 趋势 + 记录状态 + 两条记录对比

状态：完成

## 交付
- 后端记录列表：`GET /records` 每条附带 `latestAnalysisStatus`（`none|queued|running|completed|failed`）、`latestAnalysisId`、`latestAnalyzedAt`。用一条窗口函数查询（`ROW_NUMBER() OVER (PARTITION BY record_id ...)`）取每条记录最新分析，不做 N+1；分页/过滤/旧字段不变，单条 `GET /records/{id}` 形状不变；软删除记录不进入列表。`cancelled` 归为 `failed`；`latestAnalyzedAt` 仅在完成时给出（取分析创建时间，DB 无 completed_at 列）。
- 趋势 API：`GET /trends?metrics=&from=&to=&memberId=`。返回 `series[{metric,label,unit,ucum,points[{t,value,recordId,analysisId}],summary{min,max,mean,count}}]`；只取未删除记录的**最新一次 completed 分析**，缺值跳过不补 0；默认最近 30 天、默认 `heart_rate_mean,rmssd`、点位按采集时间升序；白名单为 Schema §7 的 15 个核心码，未知码 422 `unknown_metric`，`from>to` 422 `invalid_range`。`from/to` 用记录 `capturedAt` 做时间轴。
- 对比 API：`GET /records/compare?ids=a,b`（2–4 条、去重、禁止重复）→ `{records, analyses:[{recordId, latestCompleted:{summary+measurements}|null}]}`；只返回最新 completed 分析，不动点/软删除 404 `record_not_found`，数量/重复 422 `invalid_ids`。
- 前端共享层：`types.ts` 新类型（`LatestAnalysisStatus`、趋势/对比响应），`adapters.ts` 新增 `normalizeTrends/normalizeCompare`、`RecordSummary` 派生分析状态，`client.ts` 新增 `fetchTrends/fetchRecordCompare`（mock 模式返回空集合），`queries.ts` 新增 `useTrends/useRecordCompare` 与分析/删除后失效。
- 记录列表：状态徽标（颜色+图标+文字）覆盖未分析/排队/分析中/已分析/失败，已分析显示最近分析时间；复选框最多 2 条，已选满时其余禁用，工具条显示「已选 2 / 2 条」「清除选择」「对比」，进入 `/#/compare?ids=...`。
- 趋势页：指标多选（默认平均心率+RMSSD，最多 6 项，至少 1 项）、范围 7/30/90/全部、每个指标独立 Recharts 折线图（不同单位不共用 Y 轴）、悬停显示日期与数值、点数据点（支持 Tab/Enter）跳记录详情、数据表折叠视图、空状态引导去记录、加载骨架/错误重试。线色用 `--eh-signal`/`--eh-accent`，网格用 `--eh-grid-line`。
- 对比页：URL 带入或页内两条选择器；并排波形（复用 `WaveformViewer` compact，无信号显示占位）；指标表 HR/RMSSD/SDNN/N/SVEB/VEB/F/质量/时长，差异用中性底色+`±` 徽标，不判断好坏；缺一侧显示「一侧缺少数值」；无分析时给「先分析 + 打开记录」提示。
- i18n：`trends.*`、`compare.*`、`recordStatus.*`、`records.selected/select/compare/...`，zh-CN 与 en-US 同步；已在渲染页面核对英文无裸 key。
- 截图：`reports/screenshots/B3-02-trends-light.png`、`B3-02-trends-dark.png`、`B3-02-compare.png`、`B3-02-records-status.png`、`B3-02-records-selection.png`、`B3-02-compare-no-analysis-en.png`（真实 MIT-BIH 100/200/208，5 条不同日期记录）。

## 验证
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\trends -q` → **22 passed**（状态聚合、最新分析、软删除、分页；趋势默认/显式指标/去重/未知码/仅最新完成/缺值不补 0/from-to/默认 30 天/成员过滤/空数据/非法区间；对比参数、最新完成、软删除）。
- `... -m pytest backend\tests\trends backend\tests\api -q` → **56 passed**（确认记录列表旧行为未回归）。
- `... -m ruff check`（本批新增/修改路径）→ `All checks passed!`。
- `npm run build` → **pass**（tsc + Vite；产物 1,175 kB / gzip 365 kB，>500 kB 提示沿用基线）。构建期间系统内存被并行 Agent 占满（可用 <1GB），多次触发 Rust OOM；释放本机后端/浏览器后最终重跑通过。
- 真实后端临时 `EH_DATA_DIR` + Vite 1423：导入 MIT-BIH 100×3、208、200（不同 `capturedAt`）→ 5 条分析完成 → `/trends` 返回 5 点（HR 75.47–98.01，RMSSD 66.65–323.55）→ `/records/compare` 两两对比。UI 实测：状态徽标与「分析于」正确；勾选 2 条后对比按钮启用并跳转；趋势点点击进入对应记录；1080×700 两页横向溢出均为 0；去掉 ResponsiveContainer 后改用 ResizeObserver 自量宽度，趋势页控制台 0 warning/0 error。
- 英文与空态：`eh-locale=en-US` 重载后对比页无裸 key；「尚未分析」提示、无信号占位与「一侧缺少数值」均显示。

## 未做 / 偏离
- 修改了所有权清单外的 4 个文件：`backend/src/.../api/__init__.py`（挂载 `/trends` 路由，一行 include）、`src/pages/records.tsx`（列表勾选/对比入口，交付必需）、`src/lib/nav.ts`（新增不进侧栏的 `/compare` 隐藏路由，否则顶栏面包屑显示「页面不存在」）、`src/lib/i18n/*` 的 `nav.compare`。其余改动均在清单内。
- 趋势每指标一张图（遵守 UI §7 禁止双 Y 轴），未做单图叠加；没有预测/拟合/异常面积图（原为可选）。
- 对比只比较最新完成分析；没有跨成员、没有 CSV 导出、没有节律条 Overview（B4）。
- mock 模式下趋势/对比返回空集合，不伪造示例趋势。
- `latestAnalyzedAt` 语义为「最近完成分析的时间（用分析创建时间）」，不是分析结束时间。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `ruff check backend` 全量当前不通过，报错文件均属其他 B3 Agent（`db/assistant_repo.py`、`db/base.py`、`llm/agent.py` 等），本批未动。
- B3-03 已在 `api/__init__.py` 增加 reports 挂载；本批保留其改动，trends 挂载与之不冲突。
- Recharts 进入共享包后 JS 首包增加约 410 kB；如需要可对 `/trends`、`/compare` 做 `React.lazy` 路由分包（需改 `App.tsx`，属共享层）。

## 需要指挥官决策
- 对比页是否放进左侧导航：目前只在记录列表勾选进入，`nav.compare` 仅参与面包屑/标题。
- `latestAnalyzedAt` 是否接受「分析创建时间」口径；若要精确到完成时间，需给 `analyses` 表加 `completed_at` 列（跨 B1 数据层）。
- 趋势指标上限 6 项是否合适（当前选择器禁用第 7 项）。

## 建议下一批
- B4：节律条 Overview、趋势自定义区间与数据导出、报告页接入对比（B3-03 报告已可生成）。
- 大记录库下 `/trends` 分页或按天聚合缓存；路由级懒加载拆分 Recharts。
