# A2 · 模块数据 API：`records.*` 核心回调 + 隔离/权限/审计

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V1.md` §6，再读本文件。

## 目标

把 `manager._handle_core_call` 里目前返回 `NOT_IMPLEMENTED` 的 `records.*` / `signals.read` 真正接线，让模块能在权限内读写自己的健康数据。**只做后端，不做 UI。**

## 权限与可见性规则（必须按此实现）

- `records.query`（`records:read`）：只返回对调用模块**可见**的记录：
  - 模块自己创建的（`module_id == caller`），或
  - `recordType` 在该模块 `contributes.recordTypes` 中声明的记录。
  - 支持 `memberId/recordType/limit/offset/from/to`；返回摘要（id、recordType、capturedAt、tags、notes、payload 摘要、metadata），不含波形。
- `records.get`（`records:read`）：同可见性；返回完整记录对象（不含原始波形）。
- `records.create`（`records:write`）：`recordType` 必须由该模块声明；`moduleId` 强制为调用模块；`memberId` 必须存在；只写 `payload/tags/notes/metadata/capturedAt/timezone`；返回新记录。
- `records.update`（`records:write`）：只能改**自己创建**的记录；不能改 `memberId/moduleId/recordType/signalIds`；返回更新后记录。
- `records.delete`（`records:delete`，默认不授予）：只能软删除**自己创建**的记录；未授权 → 现有 `FORBIDDEN`/`PERMISSION_DENIED` 语义。
- `signals.read`（`records:read`）：同可见性；按 v1 契约返回波形（大文件用临时文件句柄，不内联巨量 JSON）；无信号 → `NOT_FOUND` 或 `NO_SIGNAL`，按 v1 约定。
- 越权/不存在一律不泄漏存在性：按 `NOT_FOUND` 处理。
- 每次调用写审计：`core.call`，含 method、scope、moduleId、ok/errorCode；成功也记录（可只记 method + recordId）。

## 交付

1. `backend/src/eclipse_health_backend/modules/manager.py`：实现 `_handle_core_call` 的 records/signals 分支，复用现有 repositories/domain 服务，不复制业务逻辑。
2. `backend/src/eclipse_health_backend/modules/permissions.py`：新增可见性辅助函数（模块声明的 recordTypes、scope 检查），保持 `CORE_RPC_SCOPES` 不变。
3. `backend/src/eclipse_health_backend/modules/audit.py`：如现有接口不足，补最小字段；不改表结构。
4. 测试 `backend/tests/modules/test_host_data.py`（新建）：
   - 有 `records:write` 的模块可创建声明类型的记录；
   - 未声明 recordType → 拒绝；
   - 只能读自己的/声明类型的记录；别人的 ECG 记录不可见；
   - update/delete 只能作用于自己创建的记录；
   - 未授予 `records:delete` → 拒绝且审计留痕；
   - signals.read 返回正确导联/采样率，越权拒绝；
   - 审计记录包含成功与失败。
   - 使用现有 `modules/official/demo.echo` 或测试 fixture，不启动真实长驻 worker；可直接调用 manager 的 core handler。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/modules/manager.py`
- `backend/src/eclipse_health_backend/modules/permissions.py`
- `backend/src/eclipse_health_backend/modules/audit.py`
- `backend/src/eclipse_health_backend/modules/db_compat.py`（仅当必须）
- `backend/tests/modules/test_host_data.py`（新建）
- `backend/tests/fixtures/modules/host/**`（只加本任务 fixture）

## 明确不做

- 不改 `modules/api.py`、`modules/contributions.py`（A1 所有权）。
- 不改 `analysis_service/**`（A3 所有权）、不改前端。
- 不做 per-module venv/沙箱/签名；不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q
```

报告 `reports/A2-module-data-report.md`，≤80 行。必须写清：可见性规则落地方式、每个 method 的返回形状、审计字段、测试输出、未做项。
