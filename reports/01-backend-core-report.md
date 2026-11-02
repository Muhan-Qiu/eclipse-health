# 报告 · B1-01 后端核心与数据层
状态：完成

## 交付
- `app.py` / `settings.py`：可启动 FastAPI，`/api/v1/health`、OpenAPI、CORS 仅本机、生命周期建库与默认成员「本人」。
- `db/base.py`：`Base` / `engine` / `get_session` / `init_db` / `reset_db` / `session_scope`，SQLite WAL，`schema_migrations` 幂等迁移（无 Alembic）。
- `db/models.py`：`members/records/signals/analyses/measurements/annotations/reports` 7 表，完整对象存 JSON 列，`records.payload` 独立列，软删除 `deleted_at`；未建 `modules`/`audit_log`。
- `domain/`：UUIDv7（自实现，含测试）、ID 前缀校验、Pydantic v2 领域模型（tags/notes/metadata/payload/leads 限制、额外字段拒绝、时区校验）、统一异常。
- `api/`：成员 CRUD、记录分页/过滤/CRUD（DELETE 软删除）、信号写入（内联 float32 或 `imports/` 文件引用）、原始波形读取（`application/octet-stream` + ETag）、`/records/{id}/signals` 元数据。
- `storage/`：原子写、sha256 写入与读取校验、路径包含性检查、报告文件读写（供 B3 使用）。
- `tests/`：`conftest.py`（临时数据目录 + 每例重建库）、`tests/core`、`tests/api`，共 80 例。
- `backend/README.md`：启动、环境变量、数据目录、API 与分页/错误约定。

## 验证
- 命令：`backend\.venv\Scripts\python.exe -m pytest backend\tests\core backend\tests\api --durations=0`
- 结果：`80 passed in 1.08s`（含 ID、模型限制、CRUD、软删除不可见、过滤分页、正弦波逐元素读回一致、`fileRef` 路径穿越拒绝、sha256 篡改检测、超限拒绝）。
- 全量（含并行 Agent 目录，仅观察）：`pytest backend/tests -o addopts="" -q` → `141 passed in 5.64s`。
- 命令：`backend\.venv\Scripts\python.exe -m ruff check backend`
- 结果：`All checks passed!`（含 B1-02/03 目录）。
- 命令：`backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765` + `curl`
- health 响应示例（节选）：
  `{"status":"ok","version":"0.1.0","database":"sqlite:///C:/.../backend/.data/eclipse_health.sqlite3","databasePath":"C:\\...\\backend\\.data\\eclipse_health.sqlite3","dataDir":"...","migrations":["0001_core"],"startedAt":"2026-10-28T13:00:19.716618Z","now":"..."}`
- 数据库位置：`backend/.data/eclipse_health.sqlite3`；波形 `backend/.data/signals/<sig_id>.f32`。
- 启动日志确认 B1-02 路由已自动挂载：`/api/v1/modules*` 12 条路径出现在 OpenAPI 中。

## 未做 / 偏离
- `POST /records` 仅支持单导联单个 `signal`；多导联需分多次写入，或 B2 扩展 `signals[]`。
- 唯一约束冲突（409）只做了 `IntegrityError` 兜底，当前 API 入口不会触发重复导联，无对应集成测试。
- 分页选择 `limit/offset`（非 cursor），已在 README 与 OpenAPI 描述中写明。
- 提示词之外的补充：`includeDeleted` 过滤、`/records/{id}/signals`、ETag/304。
- `PATCH /records` 不可改 `memberId` / `signalIds`；`recordType`、`capturedAt`、`timezone`、`quality` 等可改。
- 软删除 30 天回收站清理任务、报告生成、分析入库均未做（属 B2/B3）；存储层已备 `write_report/read_report`。
- `pyproject.toml` 仅加了 `[tool.pytest.ini_options]` 与 `[tool.ruff]`（line-length/target/src），未新增依赖、未改规则选择。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 无阻塞项。B1-02 已按契约只导入 `db.base.Base/engine` 并提供 `modules.api.router`，核心通过 try/except 挂载到 `/api/v1/modules`。
- 若 B1-03 需要把分析结果入库，表 `analyses/measurements/annotations` 已存在，但写入 API 未开（B2 再接）。

## 需要指挥官决策
- `PATCH /records` 是否允许修改 `memberId`（当前禁止，防止记录被误迁移到别的成员）。
- 删除记录时波形文件是立即删除，还是保留到 30 天回收站清理时再删（当前实现：保留文件、只标记 `deletedAt`）。
- 多导联上传的请求形状：`signals: [...]` 还是多次 POST 后再关联，留待 B2 定。

## 建议下一批
- B2：导入适配器产出 `RecordCreate` → 分析 → 分析结果入库，打通第一条端到端链路；同步补多导联写入与回收站清理任务。
- 前端 API client 可按 `/api/v1` + `{code,message,details}` 统一错误结构编写（当前 UI 仍 Mock）。
