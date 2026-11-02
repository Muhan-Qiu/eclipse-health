# 报告 · B1-02 模块系统内核
状态：完成

## 交付
- Manifest：`schemas/module.schema.json`（2020-12，含类型/权限/engines/条件贡献点/network→allowedHosts）；3 个示例；`modules/manifest.py` 用 jsonschema 校验 + Pydantic 读取，错误带 `$.path`。
- 安装器：`modules/package.py` 防 `..`/绝对路径/符号链接/Windows 保留名与 NTFS 数据流/大小写重复；ZIP 大小与文件数上限；checksums 逐文件校验（缺失仅警告）；staging → rename 原子安装；update 保留旧版本目录；`uninstall(keepData)`。
- 注册表：`modules/registry.py` / `audit.py` 用 SQLModel 继承 `db/base.Base` 注册表（无自建 Base/engine）：`installed_modules`、`module_permissions`、`audit_log`；状态 installed/enabled/running/stopped/disabled/crashed，进程重启后 enabled 模块懒启动。
- 权限：`modules/permissions.py` 11 个 scope + 核心方法→scope 映射；安装授权；升级新增权限不自动授予；撤权重启 worker，越权回调返回 `PERMISSION_DENIED`。
- 审计：`modules/audit.py` 只追加（ORM before_update/delete 直接拒绝）；按模块/动作/时间过滤；detail 白名单式脱敏，不含 params/notes/payload/绝对路径。
- Worker 宿主：`modules/host.py` 每模块独立子进程 + stdio 按行 JSON-RPC 2.0；initialize 握手；调用/启动超时；崩溃检测、连续 1 次自动重启；环境变量清洗；cwd 限定模块目录；日志 `data/logs/modules/<id>.log` 轮转；`venvPath` 预留；单次 JSON >4MB 拒绝（文件句柄预留）。
- API：`modules/api.py` 暴露无前缀 `router`，覆盖列表/安装/启停/启禁用/卸载/权限/审计/调试 RPC，另加 `rollback`；错误体 `{code, message, details}` 与核心一致。
- 示例：`modules/demo.echo/`（initialize/hello/echo/fail/call_core/health/deactivate，fail 支持 error/crash/timeout）+ `scripts/pack_demo.py`。
- 测试：`backend/tests/modules/` 4 个测试文件 + 夹具，共 68 例。

## 验证
- `ruff check backend/src/eclipse_health_backend/modules backend/tests/modules scripts` → All checks passed。
- `pytest backend/tests/modules -o addopts="" -q` → **68 passed in 5.58s**。
- `pytest backend/tests/core backend/tests/api backend/tests/modules -o addopts="" -q` → **148 passed in 6.84s**。
- 全量 `pytest backend/tests` 目前被 B1-03 新增的 `tests/analysis/test_ids.py` 与 `tests/core/test_ids.py` 同名冲突阻断（跨区，不属于本任务文件）。
- `python scripts/pack_demo.py` → `dist/demo.echo-1.0.0.ehmod`，sha256 `424987c8…9884fb`，4 个文件；脚本内含解压+checksums+layout 自校验。
- 真应用 `TestClient(app)`：`GET /api/v1/modules` 200 → install 200 → rpc echo 200 → 未知名方法 404 `METHOD_NOT_FOUND` → audit 200 → delete 200，路由已由 `app.py` 自动挂载。
- 全仓 `ruff check backend` 交稿时通过；`modules/`、测试、`schemas/`、`scripts/` 无告警。

## 全链路步骤
```powershell
backend\.venv\Scripts\python.exe scripts\pack_demo.py
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8765
# POST /api/v1/modules/install {"path":"<绝对路径>/dist/demo.echo-1.0.0.ehmod","enable":true}
# POST /api/v1/modules/org.eclipsehealth.demo.echo/start
# POST /api/v1/modules/org.eclipsehealth.demo.echo/rpc {"method":"echo","params":{"text":"hi"}}
# GET  /api/v1/modules/audit?moduleId=org.eclipsehealth.demo.echo
# DELETE /api/v1/modules/org.eclipsehealth.demo.echo?keepData=true
```
对应自动化：`test_lifecycle.py::test_full_lifecycle`、`test_api.py::test_install_list_start_rpc_audit_uninstall`。

## 审计示例
```json
{"action":"module.install","moduleId":"org.eclipsehealth.demo.echo","detail":{"version":"1.0.0","files":4,"bytes":7843,"enabled":true,"grantedPermissions":["files:user-selected"],"addedPermissions":[],"removedPermissions":[]}}
{"action":"module.start","moduleId":"org.eclipsehealth.demo.echo","detail":null}
{"action":"rpc.call","moduleId":"org.eclipsehealth.demo.echo","detail":{"method":"echo","durationMs":0,"ok":true}}
```

## 崩溃恢复验证
- `test_crash_is_detected_and_restarted_once`：crash → `MODULE_CRASH`，状态仍 running，随后 echo 成功；连续第二次 crash 不再重启 → crashed，普通调用被拒 → `start` 恢复。
- `test_idle_worker_death_is_detected`：手动 kill 空闲进程 → 状态 crashed → 下次调用重启并写 `module.crash`。
- `test_timeout_is_reported_and_module_can_restart`：1s 超时 → `MODULE_TIMEOUT`、状态 stopped → `start` 恢复。

## 未做 / 偏离
- `entry.factory` 通过 schema 校验，但 B1 直接执行 `entry.python`（factory 留给 B3 SDK bootstrap）；调试 RPC 直接调模块方法，未包一层 `invoke`。
- 不做每模块 venv、签名、注册表下载、网络代理、真实数据回调（records/signals 返回 `NOT_IMPLEMENTED`）；核心方法已做权限检查与审计。B1 不做 OS 级文件/网络沙箱（仅独立进程、cwd 与 env 清洗），权限是契约层约束。
- 升级新增权限不自动授予，需 B2 授权 UI 后再 `POST .../permissions/{scope}`；安装时授予请求权限中的非高风险项（`records:delete` 默认不授予，需显式 grant）。
- 同版本重复安装返回 `MODULE_ALREADY_INSTALLED`（无 force）；连续崩溃后不自禁用，需手动 `start`。
- API 卸载默认 `keepData=true`；保留的数据位于 `<data>/modules/<id>/data`。
- 扩展错误码：`MODULE_NOT_FOUND / MODULE_ALREADY_INSTALLED / MODULE_DISABLED / INVALID_PACKAGE / CHECKSUM_MISMATCH / UNSAFE_PACKAGE_PATH / MODULE_ERROR / METHOD_NOT_FOUND / NOT_IMPLEMENTED`。

## 跨区需求（需要别的 Agent 或指挥官处理）
- B1-01：`backend/pyproject.toml` 未声明 `jsonschema`（当前环境已有 4.26.0，模块内核直接依赖它）；建议加入正式依赖。
- B1-01：建议 lifespan 调 `modules.api.init_module_system()` 与 `shutdown_module_system()`；当前为首次访问懒初始化 + `atexit` 兜底。
- B1-03/B1-01：`tests/analysis/test_ids.py` 与 `tests/core/test_ids.py` 同名，导致全量 pytest 收集失败；建议加 `__init__.py` 或改名。
- 文档：`MODULE_CONTRACT_V1` §2 未列 `allowedHosts`，但 §6 要求 network 必须声明；建议补字段。
- 若要把内核错误体接入核心异常体系，可直接复用 `{code,message,details}`（已对齐），无需改 handler。

## 需要指挥官决策
- 升级新增权限的授权交互（B2 UI）以及“拒绝即回滚到旧版本”还是“保持新版本但权限未授予”。
- 连续崩溃是否在第 3 次自动禁用（契约 §5 提到 3 次，本批按提示词只做 1 次自动重启）。
- 安装输入是否限制为 `imports/` 目录或后续改上传接口。

## 建议下一批
- B2：Cardia 打包为 analysis-model 模块、Samsung 适配、权限授权 UI、模块设置页；接线 `records/signals` 回调。
- B3：每模块 venv、临时文件句柄传大数组、空闲回收、`invoke`/`cancel` 契约方法。
