# 报告 · G3 健康档案扩展 + 运动记录 + 个性化记忆
状态：完成

## 交付
- 档案新增静息心率（30–200 bpm）、入睡/起床时间（`HH:MM` 或 ISO 8601，可只填一个）与 `sleepTimezone`；复用 `PATCH /members/{id}`，可清空。
- 新增 `backend/src/eclipse_health_backend/exercises/`：记录类型 `org.eclipsehealth.health.exercise`，`POST/GET/PATCH/DELETE /api/v1/exercises`，软删除；仅 `activity`、`durationSec>0`、`startAt` 必填，距离/强度/主观感受/备注可空；列表支持 `activity`/`from`/`to`/`limit`/`offset`。
- 新增 `backend/src/eclipse_health_backend/memory/`：`<EH_DATA_DIR>/memory.json`，`GET/PUT /api/v1/memory`，≤20000 字，原子写入；`memory_context()` 仅返回 `enabled=true` 的内容，损坏文件回退空文档，不写日志。
- 前端 `/profile`：基本信息新增心率与睡眠输入（校验/清空/保存/放弃）；新增「运动记录」卡（快速录入 + 最近 20 条 + 两段式删除）与「个人记忆」卡（文本区、助手开关、保存/放弃、最后更新时间、隐私说明）；zh-CN/en-US 文案补齐。
- `docs/MEMORY.md`：字段、上限、隐私、助手注入方式。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend`：All checks passed。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\metrics backend\tests\exercises backend\tests\memory`：**41 passed in 1.68s**（档案新字段边界/清空、运动最小与全字段创建、非法时长/距离/枚举、过滤分页、PATCH 清空、软删除、记忆 GET/PUT、20000 上限、enabled=false、损坏回退、首跑空态）。
- 相邻回归：`pytest backend/tests/{api,core,export,metrics,exercises,memory}`：**142 passed in 4.88s**。
- `npm run build`（含 `tsc`）：通过，约 4s，0 类型错误。
- 预览（后端 8766 + Vite 1424）：保存档案新字段、录入 4 条运动、保存并启用记忆均成功；亮/暗截图 `reports/screenshots/G3-profile-light.png`、`G3-profile-dark.png`（1600×2200）；浏览器控制台 0 error。

## 未做 / 偏离
- **未改 `api/__init__.py`**（按本轮指令；计划也写明 G2–G5 由指挥官统一挂载）。两个 router 路径自带 `/exercises`、`/memory`，请用 `api_router.include_router(exercises.api.router)` / `memory.api.router` 直接挂载，不要再加 prefix。
- 因路由尚未统一挂载，`backend/tests/exercises/conftest.py`、`backend/tests/memory/conftest.py` 在测试进程内把 router 挂到测试 app（已做存在性判断，指挥官挂载后不会重复）。
- 睡眠时间新增附属字段 `sleepTimezone`（前端保存时自动带本机 IANA 时区），用于 `HH:MM` 场景；纯 ISO 输入也接受。
- 共享 `src/lib/api/types.ts` 的 `Member` 未改，档案页用本地 `ProfileMember` 扩展读取新字段。
- 运动/记忆未做编辑 UI（运动 PATCH 接口已实现并有测试）；未做图表。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 指挥官：把 `exercises.api.router`、`memory.api.router` 挂到 `/api/v1`（无额外前缀）。
- G5 新增的 `backend/tests/ohs/test_api.py` 与 `backend/tests/modules/test_api.py` 同名，全量 `pytest backend/tests` 收集报 import mismatch；需给测试目录加 `__init__.py` 或重命名文件（非本任务范围）。
- 预览时 8765 已被其他后端占用，未干扰；已改用 8766 并在结束后清理临时进程。

## 需要指挥官决策
- 是否把运动记录也展示在「健康数据」时间线（当前只在本页列出，G4 教练已直接读 records）。
- 记忆是否提供「导出/删除」入口（当前清空文本框保存即可）。

## 建议下一批
- 运动记录编辑与周汇总；记忆条目化（多条带标签）而非单文档。
