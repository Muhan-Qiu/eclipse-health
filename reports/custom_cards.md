# A8 · 自定义仪表盘卡片 — 验收报告

日期：2026-11-01  
范围：让用户导入压力、血氧、血压、运动等健康数据后，无需安装模块即可生成简单仪表盘卡片；助手可生成草稿，用户确认后才保存。不执行任意代码，不绕开 `records` 读文件，不修改既有模块 widget 契约。

## 完成内容

### 后端

新增包 `backend/src/eclipse_health_backend/dashboard_cards/`：

| 文件 | 作用 |
|---|---|
| `models.py` | Pydantic 请求 / 响应模型；`kind`、`aggregation`、`view`、`colorToken` 全部为 `Literal` 白名单，`extra="forbid"` |
| `catalog.py` | kind 目录（记录类型映射、取值规则、默认单位）、按天聚合、内置模板 |
| `service.py` | 卡片 CRUD、聚合查询、草稿创建 / 确认 / 丢弃；REST 与助手工具共用 |
| `api.py` | `/api/v1/dashboard/...` 路由 |

数据表（`db/models.py`，随 `Base.metadata.create_all` 幂等建表）：

- `dashboard_cards`：`id`、`member_id`、`kind`、`data`(JSON：title / aggregation / windowDays / view / unit / colorToken / createdBy)、`created_at`、`updated_at`
- `dashboard_card_drafts`：助手草稿，确认前不进入正式表

ID 前缀新增：`dcr_`（卡片）、`ddr_`（草稿）。

#### 支持的数据类型（白名单）

`steps`、`heart-rate`、`sleep`、`body-mass`、`blood-pressure`、`exercise`、`spo2`、`stress`、`glucose`

- 同时读取 `org.eclipsehealth.health.<kind>` 与 `org.eclipsehealth.metric` 中对应的 `kind`（体重 / 血压 / 血氧 / 血糖）；
- 睡眠、运动按 `durationSec`（或 `startAt`/`endAt`）折算分钟；
- 血压同时返回收缩压 `value` 与舒张压 `secondaryValue`；
- 压力未假设单位（各厂商标度不一），缺失时显式返回 `unitSource="missing"`。

#### API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/dashboard/cards?memberId=&includeData=true` | 列表；`includeData` 一次带回聚合结果 |
| POST | `/api/v1/dashboard/cards` | 创建（201） |
| GET | `/api/v1/dashboard/cards/{id}` | 读取 |
| PATCH | `/api/v1/dashboard/cards/{id}` | 更新 |
| DELETE | `/api/v1/dashboard/cards/{id}` | 删除（204） |
| GET | `/api/v1/dashboard/cards/{id}/data` | 单卡聚合数据 |
| GET | `/api/v1/dashboard/card-templates` | 内置模板 |
| GET | `/api/v1/dashboard/card-drafts` | 助手草稿（含预览数据） |
| POST | `/api/v1/dashboard/card-drafts` | 手动创建草稿 |
| POST | `/api/v1/dashboard/card-drafts/{id}/confirm` | 确认并写入正式卡片 |
| DELETE | `/api/v1/dashboard/card-drafts/{id}` | 丢弃草稿 |

聚合语义：

- `value` 为整个时间窗的聚合值；`series` 为按天聚合的趋势点（`latest` 直接返回原始点）；
- `latest / avg / min / max / sum / count` 六种聚合；
- 无数据时 `value = null`、`series = []`、`hasData = false`、`missingReason = "no_data"`，**从不返回 0**；
- `unit` 优先用卡片自定义，其次用类型默认；都没有时 `unitSource="missing"`。

#### 助手工具（`llm/tools.py`）

- `list_card_templates`：列出内置模板；
- `create_dashboard_card`：**只创建草稿并返回预览**，`saved=false`，不写 `dashboard_cards`；
- `confirm_dashboard_card`：用户明确确认后才把草稿写入正式卡片。

三个工具与 REST 共用 `CardFields` 校验，模型无法通过工具绕过白名单。系统提示同步补充：只有用户明确同意后才能确认草稿。

### 前端

新增 `src/features/dashboard-cards/`：

- `types.ts`：kind / aggregation / view / colorToken 常量与颜色令牌解析；
- `api.ts`：基于共享 `baseUrl` / `ApiError` 的请求封装；
- `use-dashboard-cards.ts`：卡片、模板、草稿查询与增删改 / 确认 / 丢弃 mutation；
- `custom-card.tsx`：stat / sparkline / line / bar 四种视图，空数据、加载失败、单位缺失均有明确状态；
- `mini-chart.tsx`：纯 SVG 折线 / 柱状图，不新增图表依赖；
- `card-form-dialog.tsx`：数据类型、聚合、图表、时间窗、标题、单位、颜色表单 + 「让助手创建」；
- `draft-card.tsx`：草稿卡片，「添加」才落库，「忽略」丢弃。

布局集成（`src/features/layout/layout.ts`、`src/pages/dashboard.tsx`）：

- 新增布局类型 `custom-card`，布局 id 前缀 `custom:<cardId>`；
- `mergeLayout` 同时合并模块卡片与自定义卡片；任一侧未加载完时保留已保存顺序，避免误删；
- 自定义卡片自动进入编辑器的拖拽排序、宽度调整、隐藏；删除走确认对话框；
- 仪表盘顶部新增「添加卡片」；卡片查询失败时单卡显示重试状态；
- 助手草稿在仪表盘单独成组展示，带预览数据；点「添加」调用 `confirm`，点「忽略」丢弃。

内置模板：压力（最新 / 趋势）、血氧（最新 / 趋势）、血压（最新 / 趋势）、运动（周汇总）、睡眠（时长趋势），同时可作为表单快捷模板。

i18n：`zh-CN` / `en-US` 均补齐 `dashboard.customCards.*`。

### 兼容与安全

- 未改模块 widget 契约；模块卡片逻辑保持原样；
- 卡片只保存「查什么 / 怎么聚合 / 怎么画」，限制 `windowDays` 1–365、标题 80 字、单位 16 字；
- 所有查询限定当前成员且 `deleted_at IS NULL`；
- 不支持用户输入 SQL / JS / 模板表达式；
- 不直接读文件，只读 `records` 表。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -m "not slow" -q`：全部通过（新增 10 个用例，含 CRUD、白名单、聚合、空数据、血压对值、时长换算、单位缺失、草稿确认/丢弃、成员隔离、助手工具草稿→确认流程）。
- `./.venv/Scripts/python.exe -m ruff check ...`：通过。
- `npm run build`：通过（tsc + vite build）。
- 仅剩既有的 FastAPI duplicate operation id 警告（exercises / memory），与本次改动无关。

## 已知限制

- `stress` 类型没有公认单位，卡片默认不填单位并显示「单位未知」，用户可在表单自定义；
- 压力 / 血氧卡片的数据密度取决于导入器是否写入对应记录类型；没有数据时卡片明确显示空状态，而不是 0；
- 「让助手创建」依赖用户已配置可用的 LLM provider；未配置时仍可直接在表单保存。
