# 报告 · B4-04 导出/备份 + 隐私中心 + 诊断日志 + 设置

状态：完成

## 交付

- 后端 `export/`：`archive.py` 流式生成备份（ZIP/JSON/CSV），`restore.py` 校验 manifest/版本/路径/哈希后以新 ID 恢复；恢复前自动写 `data/backups/pre-restore-*.zip`。ZIP 含 `manifest.json`、`records.json`、`signals.json`、`records.csv`、`measurements.csv`、`analyses/*.json`、`signals/*.f32`、`reports/*`、`reports.json`；文件名只含日期时间，不含成员/备注/原文件名。
- 后端 `privacy/`：存储用量统计（各表数量、波形/报告/导入/数据库字节、数据目录）；清空记录/信号/分析/测量/标注/报告（保留成员与设置），先写 append-only 审计再删除，并清理 `signals/`、`reports/`、`imports/` 内文件；`data/settings.json` 持久化 `closeToTray/splashEnabled/locale`，`telemetryEnabled` 恒为 false。
- 后端 `diagnostics/`：`GET /diagnostics/bundle` 生成 ZIP（`diagnostics.json`、`system.txt`、`logs.txt`）；含应用/Python/ORT/DB schema 版本、系统信息、数据量、最近日志（单文件 200KB、总计 512KB 截断）；不含波形、notes、payload、成员姓名、记录 ID；用户目录/用户名脱敏为 `<user>`、数据目录为 `<data>`。新增 `data/logs/backend.log`（RotatingFileHandler，2MB×3）作为日志来源。
- API：`api/export.py`（GET `/export/backup`、POST `/import/backup`）、`api/privacy.py`（GET `/privacy/storage`、DELETE `/privacy/all?confirm=DELETE_ALL`）、`api/diagnostics.py`、`api/settings.py`（GET/PUT `/settings`）；`api/__init__.py` 挂载四组路由并 try/except 挂载 B4-07 的 `metrics.api.router`（路径已含 `/metrics` 则直接挂载，否则补前缀）。
- 前端：`src/features/export/**`（ZIP/JSON/CSV 下载、ZIP 选择 + 二次确认 + 结果统计、诊断包下载）、`src/features/privacy/**`（存储用量、数据目录、确认词 `DELETE` 后清空、遥测禁用说明、关闭到托盘/启动动画开关）；`settings.tsx` 组合新卡片并保留外观/语言/关于；i18n 新增 `export.*`、`privacy.*`、`diagnostics.*`、`settings.desktop.*`（zh-CN/en-US）。

## 验证

- `ruff check`（本任务全部文件）→ All checks passed。
- `ruff check backend` → 1 error，位于 B4-01 的 `backend/packaging/serve.py:186`（RUF100 未使用 noqa），本任务文件无错误。
- `pytest backend/tests/export backend/tests/privacy backend/tests/diagnostics -q` → **27 passed，exit 0，5s**（含导出→清空→恢复、信号 sha256 与测量值一致、CSV 结构、损坏/截断/版本不兼容 422、隐私清空、审计、设置持久化、遥测拒绝、诊断包 PHI 排除与用户名脱敏、空数据）。
- `pytest backend/tests/api backend/tests/export backend/tests/privacy backend/tests/diagnostics -q` → **61 passed，exit 0，8s**（核心路由无回归）。
- `npm run build` → pass（tsc + vite 1.55s；1,222.84 kB / gzip 378.05 kB，仅沿用 >500 kB 提示）。
- UI（真实后端 + 临时数据目录）：1440×1100 亮/暗截图；设置页显示存储用量（1 记录/1 波形/14KB 信号）、数据目录、清空区、桌面开关、诊断按钮；console 0 error。
- UI 手测：ZIP 导出成功下载；输入 `DELETE` → 确认清空 → 记录/波形归零；选择同一 ZIP 恢复 → 记录/波形恢复、显示“导入 1 条记录…”与自动备份文件名；桌面“关闭到托盘”开关写入 `settings.json`（`closeToTray:false`）；诊断包下载后用 Python 检查无用户名、`dataDir=<data>`。
- 截图：`reports/screenshots/B4-04-settings-light.png`、`B4-04-settings-dark.png`、`B4-04-settings-light-bottom.png`。

## 未做 / 偏离

- JSON 导出不内嵌波形，只给 `storage.relativePath + sha256`，`signalPolicy` 已说明；需要波形本体请用 ZIP。
- ZIP 比提示词多写 `signals.json` 与 `reports.json`：否则记录只能恢复 `signalIds` 而无 fs/lead/sha、报告无元数据，无法可靠还原。
- 恢复策略：记录沿用原 `memberId`（存在时），否则归到当前默认成员；成员本身不导入。`queued/running` 分析恢复为 `failed`，`beatsRef` 置空（B2 未产生该字段）。
- 清空同时清理 `imports/` 临时导入文件（属于本地 PHI），提示词未列出但符合“清空全部”。
- 设置存 `data/settings.json`；`telemetryEnabled=true` 返回 422 `telemetry_not_supported`，不假装有遥测。
- 全量 `pytest backend/tests -m "not slow"` 未跑通：并行 Agent 占满内存，`tests/modules/test_package.py` 与 `tests/imports/test_wfdb_import.py` 报 MemoryError（非本任务代码路径）。
- 未改 `settings.py`（不在所有权内）；`data/logs` 路径在 diagnostics 内派生。

## 跨区需求（需要别的 Agent 或指挥官处理）

- B4-01：`backend/packaging/serve.py:186` 的 RUF100 需清掉，否则全量 `ruff check backend` 失败；Tauri 仍未注册 `set_close_to_tray` / `set_splash_enabled`，前端按契约 `invoke(command, { enabled })` 调用并 try/catch 回退 localStorage（提示“重启后生效”）。
- B4-07：`metrics.api.router` 缺失时自动跳过；若路径已以 `/metrics` 开头直接挂载，否则补前缀。请保持 `metrics/api.py` 导出 `router`。
- `app.py` 仅在 `configure_logging` 增加文件日志安装（try/except，不阻断启动），其余未动。

## 需要指挥官决策

- JSON 导出是否需要提供 base64 波形选项（当前为控制内存明确只给哈希/引用）。
- 清空数据是否也要删除模块注册表/审计；当前保留成员、设置、模块与 append-only 审计。

## 建议下一批

- 超大库的流式 JSON 恢复、恢复进度/取消、备份加密（H4）、云同步（暂不做）。
