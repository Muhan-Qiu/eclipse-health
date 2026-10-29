# B4-04 · 导出/备份 + 隐私中心 + 诊断日志 + 设置

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B4 收口（Wave 1）
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 你是本批**后端路由接线所有者**（`api/__init__.py`）；B4-07 的 metrics 路由由你挂载。

## 1. 必读

- `docs/DATA_SCHEMA_V1.md`：§4–§9、§11 存储、§15 隐私。
- `docs/INTERNAL_API_V1.md`：§0 通用、§1 记录。
- `docs/V3_FEATURE_BACKLOG.md`：D5 导出/备份、D6 隐私中心、H6 诊断日志、H1/H2 桌面设置。
- `reports/B2-01-report.md`、`reports/B3-02-report.md`、`reports/B3-03-report.md`。
- 代码：`storage/files.py`、`db/models.py`、`db/repositories.py`、`api/__init__.py`、`app.py`、`src/pages/settings.tsx`。

## 2. 你必须交付

### 后端

1. **导出/备份**
   - `GET /export/backup?format=zip|json|csv`
     - `zip`：`manifest.json`（版本/时间/数量/哈希）+ `records.json` + `records.csv` + `measurements.csv` + `signals/<id>.f32` + `analyses/*.json` + `reports/*`（如有）。流式/临时文件，避免整包进内存。
     - `json`：单文件 JSON（记录/分析/测量；信号给出哈希与 base64 或引用，二选一并说明）。
     - `csv`：记录 + 测量扁平表（不含波形）。
   - `POST /import/backup`：上传 ZIP 恢复；校验 manifest/版本/哈希；冲突策略选「新 ID 导入」并在报告说明；损坏/版本不兼容 422；恢复前自动备份当前库（或明确提示）。
   - 文件名默认脱敏；不包含 `uploads/` 原始文件名。
2. **隐私中心**
   - `GET /privacy/storage`：各表数量、信号/报告字节数、数据目录。
   - `DELETE /privacy/all`：清空记录/信号/分析/测量/报告（保留成员与设置）；需要 body/query 确认令牌；删除前写一条审计（如模块审计可用）。
   - `GET/PUT /settings`：`{closeToTray, splashEnabled, telemetryEnabled:false, locale?}`；落 `data/settings.json` 或 DB；telemetry 永远 false/无实现，不要假装有。
   - 说明「数据只在本机」；不新增遥测。
3. **诊断日志**
   - `GET /diagnostics/bundle`：ZIP 包含应用版本、Python/ORT 版本、DB schema 版本、最近日志（截断）、系统信息；**排除**波形、notes、payload、成员姓名、绝对路径中的用户名（脱敏为 `<user>`）。
   - 日志来源：现有 logging + `data/logs/`；不新增依赖。
4. **接线**
   - `api/__init__.py`：挂载 export/privacy/diagnostics/settings；并 try/except 挂载 B4-07 的 `metrics.api.router`（路径 `/metrics`）。
   - 不要改 `app.py` 以外不需要改的地方；如需 lifespan，写报告。
5. **测试**：导出→恢复往返（记录数/信号哈希/测量）、CSV 结构、隐私清空、设置持久化、诊断包不含 PHI、损坏备份 422。

### 前端

6. **设置页**（`src/pages/settings.tsx` + `src/features/{privacy,export}/**`）
   - 数据与备份：导出 ZIP/JSON/CSV（下载）、恢复备份（文件选择 + 二次确认 + 结果统计）。
   - 隐私：存储用量、数据目录、清空全部（输入确认词）、遥测开关禁用/说明。
   - 诊断：下载诊断包。
   - 桌面：关闭到托盘、启动动画开关；优先 `invoke("set_close_to_tray", ...)` / `invoke("set_splash_enabled", ...)`（B4-01 契约），不可用时回退 localStorage 并提示「重启后生效」。
   - 保留现有外观/语言设置。
7. **i18n/边界**：`settings.*`/`privacy.*`/`export.*` 可用共享 `src/lib/i18n/*`（本批无其他 Agent 改它）；不要动 `src/lib/api/client.ts` 的形状，用 feature-local fetch 或 `apiFetch`。

## 3. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/export/**
backend/src/eclipse_health_backend/privacy/**
backend/src/eclipse_health_backend/diagnostics/**
backend/src/eclipse_health_backend/api/{export,privacy,diagnostics,settings}.py
backend/src/eclipse_health_backend/api/__init__.py
backend/src/eclipse_health_backend/app.py            # 仅必要接线
backend/tests/export/**
backend/tests/privacy/**
backend/tests/diagnostics/**
src/pages/settings.tsx
src/features/privacy/**
src/features/export/**
src/lib/i18n/{zh-CN,en-US}.ts                        # settings/privacy/export 键
```

不要动：`src/pages/{record-detail,modules,profile,assistant,reports,trends,compare}.tsx`、`src/components/records/**`、`src/features/{waveform,modules,profile,assistant,reports,trends}/**`、`src/App.tsx`、`src/lib/nav.ts`、`src-tauri/**`、`modules/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 4. 与其他 Agent 的契约

- B4-01（打包）：Tauri 侧暴露 `set_close_to_tray` / `set_splash_enabled` 命令；你调用时 try/catch。
- B4-07（档案/手动指标）：提供 `backend/src/.../metrics/api.py` 的 `router`（路径 `/metrics/...`）；你负责在 `api/__init__.py` 里 try/except 挂载。
- B4-05/06：不改他们的页面/feature。

## 5. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\export backend\tests\privacy backend\tests\diagnostics -q
npm run build
# 手工：导出 ZIP → 清空 → 恢复 → 数量/波形哈希一致；诊断包无姓名/notes
```

## 6. 明确不做

云同步、加密数据库（H4 暂不加入）、自动更新、通知、模块 UI、设备格式、健康档案/手动指标（B4-07）、波形增强（B4-05）。只做导出/隐私/诊断/设置。
