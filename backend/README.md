# eclipse health backend · B1 核心服务

本地优先的健康数据服务：FastAPI + SQLModel + SQLite，负责成员、健康记录与波形文件。
分析、模块系统、LLM 不在这里（分别为 B1-03 / B1-02 / 后续批次）。

## 启动

```powershell
# 项目根目录
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
# 或
backend\.venv\Scripts\python.exe -m eclipse_health_backend   # 读 EH_PORT，默认 8765
```

- `GET http://127.0.0.1:8765/api/v1/health`
- OpenAPI: `http://127.0.0.1:8765/docs`

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `EH_DATA_DIR` | `backend/.data` | 数据目录（数据库 + 波形 + 报告） |
| `EH_PORT` | `8765` | `python -m eclipse_health_backend` 监听端口 |
| `EH_LOG_LEVEL` | `INFO` | 日志级别 |

CORS 只放行本机来源：`localhost` / `127.0.0.1`（任意端口）、`tauri://localhost`。

## 数据目录

```
backend/.data/
  eclipse_health.sqlite3   # SQLite（WAL）
  signals/<sig_id>.f32     # 小端 float32，单导联一个文件
  reports/                 # PDF / PNG（B3 生成）
  imports/                 # 用户导入的原始文件，fileRef 只能指向这里
```

波形写入先落临时文件再 `os.replace`；入库记录 sha256，读取时校验，篡改会返回
`500 storage_integrity_error`。数据库不保存原始文件名。

## API 摘要（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 版本、数据库路径、启动时间、迁移版本 |
| GET/POST | `/members` | 成员列表 / 新建 |
| GET/PATCH | `/members/{id}` | 读取 / 更新 |
| GET | `/records` | 分页 + 过滤，见下 |
| POST | `/records` | 新建记录，可同时写入一段信号 |
| GET/PATCH/DELETE | `/records/{id}` | 读取 / 更新标签备注 / 软删除 |
| GET | `/records/{id}/signals` | 信号元数据 |
| GET | `/records/{id}/signal?lead=I` | 原始 float32（`application/octet-stream`，带 `ETag`） |

**分页**：`limit`（1–500，默认 50）+ `offset`（默认 0），按 `capturedAt` 倒序，
响应 `{items, total, limit, offset}`。记录过滤参数：`memberId`、`recordType`、
`moduleId`、`capturedFrom`、`capturedTo`、`includeDeleted`（默认 `false`）。

**POST /records 的 signal**：

```json
{
  "memberId": "mem_...",
  "recordType": "org.eclipsehealth.ecg",
  "capturedAt": "2026-10-28T10:00:00+08:00",
  "samplingRate": 500.0,
  "signal": { "lead": "I", "samples": [0.1, 0.2] }
}
```

`signal.samples` 与 `signal.fileRef` 二选一（后者相对 `imports/`，拒绝绝对路径与 `..`）。
`fs` 缺省时取 `samplingRate`；`durationSec` 缺省时按采样点/采样率计算；`signalIds`
由服务端生成。

**错误**统一为：

```json
{ "code": "record_not_found", "message": "record not found: rec_...", "details": { "id": "rec_..." } }
```

## 测试与检查

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\core backend\tests\api
backend\.venv\Scripts\python.exe -m ruff check backend
```

测试使用临时数据目录，不读写真 `backend/.data`，波形全部是合成正弦波。

## 数据库

7 张核心表（`members/records/signals/analyses/measurements/annotations/reports`）+ `schema_migrations`。
`modules` / `audit_log` 归 B1-02。完整对象存 JSON 列，查询字段单独成列；
`records.payload` 单独一列。软删除为 `deletedAt`，30 天回收站清理留到后续批次。
