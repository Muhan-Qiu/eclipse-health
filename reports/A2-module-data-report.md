# 报告 · A2 模块数据 API（records.* / signals.read）

状态：完成

## 交付
- `modules/manager.py`：`_handle_core_call` 接线 6 个数据方法；新增 `_dispatch_data`、`_records_query/get/create/update/delete`、`_signals_read`、审计与参数校验辅助；内核 Session 改用 `sqlmodel.Session` 以复用 repositories；关闭时清理波形临时句柄。
- `modules/permissions.py`：新增 `declared_record_types`、`record_is_visible`、`record_is_owned`、`require_declared_record_type`；`CORE_RPC_SCOPES` 未改。
- `modules/errors.py`（超出所有权，见「未做/偏离」）：新增 `NOT_FOUND`、`NO_SIGNAL` 两个错误码及 JSON-RPC 映射。
- `tests/modules/test_host_data.py`（新建，11 例）。

## 可见性规则落地方式
- 声明类型来自 `manifest.contributes.recordTypes[].id`；`records.query` 的 SQL 条件是
  `deleted_at IS NULL AND (module_id = caller OR record_type IN declared)`。
- `records.get` / `signals.read`：先取行，再按同一谓词判断；不存在、已软删、越权统一抛 `NOT_FOUND`，不区分原因。
- `records.update/delete`：只认 `module_id = caller`，否则同样 `NOT_FOUND`。
- `records.create`：`recordType` 必须在本模块声明集合内；`moduleId` 强制为调用方；`memberId` 必须存在（否则 `NOT_FOUND`）。

## 每个 method 的返回形状
- `records.query` `{memberId?,recordType?,limit?,offset?,from?,to?}` →
  `{items,total,limit,offset}`；item = `{id,memberId,moduleId,recordType,capturedAt,timezone,tags,notes,metadata,payloadSummary:{keys,bytes}}`（不含 payload 原文与波形）。默认 limit 50、上限 500，按 capturedAt 倒序。
- `records.get` `{recordId}` → 完整 `HealthRecord`（含 payload、signalIds，不含波形）。
- `records.create` `{memberId,recordType,capturedAt,timezone?,payload?,tags?,notes?,metadata?}` → 新 `HealthRecord`；其他字段（含 signalIds/source 等）显式 `INVALID_INPUT`。
- `records.update` `{recordId,payload?/tags?/notes?/metadata?/capturedAt?/timezone?}` → 更新后记录；`memberId/moduleId/recordType/signalIds` 出现即 `INVALID_INPUT`。
- `records.delete` `{recordId}` → `{recordId,deleted:true,deletedAt}`（软删，需 `records:delete`）。
- `signals.read` `{recordId,lead?,start?,count?}` → `{recordId,signalId,lead,fs,unit,dtype,byteOrder,startSample,count,totalSamples}`；
  ≤65536 样本内联 `samples`（float 数组），超出写临时 `.f32` 并返回 `fileHandle:{path,format:"float32-le",byteOrder,bytes}`。多导联未指定 lead → `INVALID_INPUT`；无信号/无该导联 → `NO_SIGNAL`。

## 审计字段
- 每次数据调用写 `core.call`：`module_id` 列 = 调用模块，`scope` 列 = 所需权限，`detail = {method, ok, errorCode?, recordId?}`。
- 成功与失败都记；失败先 rollback 数据改动，再单独提交审计。payload/notes/metadata 不进入审计（沿用 `sanitize_detail`）。

## 验证
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q` → 127 passed，exit 0（含新 11 例）。
- `backend\.venv\Scripts\python.exe -m ruff check backend\src\eclipse_health_backend\modules backend\tests\modules` → All checks passed。
- `backend\.venv\Scripts\python.exe -m ruff check backend` → **失败**，4 个错误全部在 `analysis_service/onnx_engine.py`（A3 并行新增文件，RUF100×2 / RUF046×2），与本任务无关；A2 范围内 ruff 通过。
- 覆盖：创建/读取/查询、时间过滤与分页、跨模块可见性、update/delete 越权、delete 默认未授权、signals 切片/多导联/大文件句柄、审计成功+失败且不含健康数据、空查询与非法参数。

## 未做 / 偏离
- **改了 `modules/errors.py`**（不在任务所有权列表）：`NOT_FOUND`/`NO_SIGNAL` 不在原 `_ERROR_SPECS` 中，`ModuleError` 会直接 `ValueError`；任务又明确要求「按 NOT_FOUND 处理」，只能补两个码，未改表结构。
- 未用 `recordTypes[].schema` 校验 `payload`（契约 §7.4 的 JSON Schema 校验留给后续；当前仅做 HealthRecord 通用字段校验）。
- `signals.read` 文件句柄返回绝对临时路径，尚无 capability token/SDK 解析；临时文件在 `manager.shutdown()` 统一删除，单次运行期间不主动回收。
- 波形读取复用 `storage.files.read_signal`（按全局 `EH_DATA_DIR` 解析），因此整文件读入内存后再切片；2GB 级记录需要后续改为按字节 seek + 分块校验。
- 未动 `files.*`、`models.*`、`llm.complete`，仍返回 `NOT_IMPLEMENTED`。

## 跨区需求
- `docs/MODULE_DEVELOPER_GUIDE_V1.md:77` 仍写「records.* 尚未实现，会返回 NOT_IMPLEMENTED」，需文档负责人更新（本任务不改 docs）。
- A3：`analysis_service/onnx_engine.py` 有 4 个 ruff 报错，导致全量 `ruff check backend` 不绿。

## 需要指挥官决策
- `signals.read` 的句柄最终形态：临时文件绝对路径（当前）还是核心发放的 capability token？SDK 落地前建议先用路径。
- 模块记录是否要在 `records.create` 时强制 `payload` 通过声明 schema（会拒绝现有宽松模块）。

## 建议下一批
- 模块 SDK（Python）封装 core RPC + 句柄解析；`recordTypes[].schema` 校验；`files.*` 接线。
