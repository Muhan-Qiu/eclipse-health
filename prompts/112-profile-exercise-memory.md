# G3 · 健康档案扩展 + 运动记录 + 个性化记忆

> 先读 `prompts/00-COMMON.md`、`reports/B4-07-report.md`、`src/features/profile/**`、`backend/src/eclipse_health_backend/metrics/**`。
> **思考强度：low。** 复用现有 metrics/records 模式，不新建大框架。

## 交付

### 1. 健康档案新增字段

- 静息心率（`restingHeartRate`，bpm，30–200）、睡眠时间（`sleepStart` / `sleepEnd`，ISO 时间或 HH:MM + 时区；两者可只填一个，不强制）。
- 只做加法；现有出生年/性别/身高/体重/病史/用药/备注保持不变。
- 前端健康档案页表单增加这些字段（可清空、校验、保存/放弃），显示在基本信息区。

### 2. 运动记录

- 新记录类型 `org.eclipsehealth.health.exercise`，payload：
  ```json
  {"activity":"walk|run|cycle|swim|strength|yoga|other","durationSec":1800,
   "distanceKm":3.2|null,"intensity":"low|moderate|vigorous|null",
   "subjective":"轻松|适中|吃力|null","notes":"","startAt":"...","source":"manual|import"}
  ```
- 后端：`POST/GET/PATCH/DELETE /api/v1/exercises`（或复用 records + `recordType` 过滤器），校验可选字段：不必全部填写；durationSec 必填且 >0；distance/intensity/subjective 可空；软删除。
- 前端：健康档案页新增「运动记录」区：
  - 快速录入：活动类型、时长（分钟）、距离（可选）、强度（可选，主观/客观二选一或都填）、备注；
  - 列表：最近 20 条，显示类型/时长/距离/强度/时间，可删除（两段式）。
- 不需要图表；教练会读取这些记录（G4）。

### 3. 个性化记忆文档

- 后端新建 `backend/src/eclipse_health_backend/memory/`：
  - 存储：`<EH_DATA_DIR>/memory.json`（或 DB 单行），结构 `{content: string, enabled: bool, updatedAt: string}`；`content` 为纯文本/Markdown，≤20000 字；
  - `GET /api/v1/memory`、`PUT /api/v1/memory` `{content, enabled}`；空内容允许；
  - 导出给助手用的函数 `memory_context()`（G4 调用），只返回 `enabled=true` 的内容；不写日志。
- 前端健康档案页新增「个人记忆」卡片：
  - 可编辑文本区（Placeholder：心情、近期事件、生活习惯、想让我记住的事）；
  - 开关「允许助手使用」；
  - 保存/放弃；显示最后更新时间；隐私说明「只保存在本机，仅在你使用助手时提供给模型」。
- 文档 `docs/MEMORY.md`：字段、上限、隐私、助手如何注入。

### 4. 测试

- 后端：档案新字段校验/清空；运动创建（仅时长）与全字段、非法时长、软删除、列表过滤；记忆 GET/PUT、长度上限、enabled=false 不返回上下文、文件损坏回退空。
- 前端 `npm run build` 通过；截图亮/暗 `reports/screenshots/G3-*.png`。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/domain/models.py`（仅档案字段）
- `backend/src/eclipse_health_backend/metrics/**` 或新建 `backend/src/eclipse_health_backend/exercises/**`
- `backend/src/eclipse_health_backend/memory/**`（新建）
- `backend/src/eclipse_health_backend/api/__init__.py`（挂 router）
- `backend/tests/metrics/**`、`backend/tests/exercises/**`、`backend/tests/memory/**`（新建）
- `src/features/profile/**`
- `src/lib/i18n/**`（只新增 profile 键）
- `docs/MEMORY.md`
- `reports/G3-*.md`、`reports/screenshots/G3-*.png`

## 明确不做

- 不改评分（G2）、教练/助手（G4）、首页（G1）。
- 不做图表、天气、LLM 调用；不新增依赖；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\metrics backend\tests\exercises backend\tests\memory -q
npm run build
```

报告 `reports/G3-profile-exercise-memory-report.md`，≤80 行。
