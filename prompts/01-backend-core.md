# B1-01 · 后端核心与数据层

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B1 地基
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。

## 1. 必读

- `docs/DATA_SCHEMA_V1.md`：§0–§9、§11–§15（重点：ID、HealthRecord、Signal、存储映射、限制、隐私）。
- `docs/V3_BUILD_PLAN.md`：所有权矩阵与验收门。
- `backend/pyproject.toml`、`backend/src/eclipse_health_backend/__init__.py`。

## 2. 目标

把空后端变成**可启动、可测试、可被前端调用**的核心服务：SQLite 持久化 + 成员/记录/信号 API + 文件存储。不要做分析、不要做模块系统、不要做 LLM。

## 3. 你必须交付

1. **应用骨架**
   - `settings.py`：`pydantic-settings`，数据目录 `EH_DATA_DIR`（默认 `backend/.data`）、端口 `EH_PORT`（默认 8765）、CORS 仅本机、日志级别。
   - `app.py`：`create_app()` + `app`；`/api/v1/health` 返回版本、数据库路径、启动时间；挂载 `/api/v1` 路由；OpenAPI 正常。
   - 生命周期里初始化数据库（建表 + 迁移版本表）。
   - **模块路由预留**：用 try/except 导入 `from .modules.api import router`（B1-02 提供），存在则挂到 `/api/v1/modules`；不存在时不能影响启动。不要修改 B1-02 的文件。
2. **数据库**
   - **第一优先级：先交 `db/base.py`**，因为 B1-02 并行依赖它；再做表与 API。
   - `db/base.py`：SQLModel `Base`、engine、session 依赖、`init_db()`、`get_session()`。**这是 B1-02 唯一依赖你的共享文件，接口要稳定。**
   - 表按 Schema §11：`members`、`records`、`signals`、`analyses`、`measurements`、`annotations`、`reports`。`modules` / `audit_log` **不要建**，归 B1-02。
   - 字段能存完整 JSON 对象；`records` 的 `payload` 单独列；软删除 `deleted_at`；UTC 时间。
   - 迁移：`schema_migrations` 表 + 幂等初始化；不引入 Alembic。
3. **领域模型**
   - Pydantic v2 模型对应 Member / HealthRecord / Signal；字段、必填、限制按文档（`tags` ≤32×32、`notes` ≤4000、`metadata` ≤16KB、`payload` ≤1MB 等）。
   - ID：`<prefix>_<UUIDv7>`，自己实现一个小的 UUIDv7 工具（Python 3.12 无标准库 uuid7），带测试。
   - 单位：UCUM 字符串，不做换算。
4. **API（`/api/v1`）**
   - `GET/POST/PATCH /members`，`GET /members/{id}`；首次启动自动建默认成员「本人」。
   - `GET /records`：分页（cursor 或 limit/offset 二选一，写清楚）、按时间/recordType/moduleId 过滤、排除软删除；`GET/POST/PATCH/DELETE /records/{id}`（DELETE 为软删除）。
   - `POST /records` 支持 `signal`（采样率、导联、float32 数组或文件引用）写入；`GET /records/{id}/signal?lead=...` 返回原始 float32（`application/octet-stream`）与元数据。
   - 标签/备注更新走 PATCH。
   - 错误：404 / 409 / 422 语义清楚，响应体含 `code`、`message`、`details`。
5. **文件存储**
   - `storage/`：`data/signals/<sigid>.f32`、`data/reports/`；写时算 sha256；读时校验；原子写（临时文件 + rename）。
   - 路径不得拼接用户输入；不保存原始文件名（只存哈希）。
6. **测试**
   - `backend/tests/conftest.py`（全局 fixture，临时数据目录/临时 DB）+ `tests/core/` + `tests/api/`。
   - 覆盖：ID 格式、模型校验、成员默认值、记录 CRUD、软删除不可见、过滤分页、信号写入/读回逐元素一致、超限拒绝、路径穿越拒绝。
   - 不写真实健康数据；用合成正弦波。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/__init__.py
backend/src/eclipse_health_backend/app.py
backend/src/eclipse_health_backend/settings.py
backend/src/eclipse_health_backend/db/**
backend/src/eclipse_health_backend/domain/**
backend/src/eclipse_health_backend/api/**
backend/src/eclipse_health_backend/storage/**
backend/tests/conftest.py
backend/tests/core/**
backend/tests/api/**
backend/pyproject.toml        # 仅必要时加依赖，并在报告说明
backend/README.md
```

不要动：`analysis/`、`modules/`、`schemas/`、`src/`、`src-tauri/`、`docs/`、`prompts/`、`uploads/`、`backend/resources/`、根 `package.json`、`tsconfig.json`。

## 5. 与 B1-02 的契约

- 它只读你的 `db/base.py`，导入 `Base` / `engine` / `get_session`。
- 它提供 `eclipse_health_backend/modules/api.py` 的 `router`（无前缀）；你负责挂到 `/api/v1/modules`。用 try/except，保证它不存在时服务照常启动。
- 它自己建 `modules` / `audit_log` 表；你不要建、不要改。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\core backend\tests\api -q
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
# 另开终端：curl http://127.0.0.1:8765/api/v1/health
```

报告里写：测试通过数、ruff 结果、health 响应示例、数据库文件位置。

## 7. 明确不做

心电分析、Cardia、模块安装/权限/审计、LLM、Windows 凭据管理器、托盘/Tauri、前端。记录一次分析的自动入库也留到 B2。
