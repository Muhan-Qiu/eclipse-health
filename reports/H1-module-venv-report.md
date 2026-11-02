# 报告 · H1 每模块独立 venv（30 个模块的前置能力）

状态：完成

## 交付

- `schemas/module.schema.json`：新增可选 `dependencies`（数组、≤32、去重、PEP 508 受限子集），顶层 `additionalProperties: false` 不变。
- `modules/manifest.py`：`Manifest.dependencies: tuple[str, ...]`；`validate_dependencies` / `normalize_dependency` 双重校验；拒绝 URL（`@`）、本机路径、`file:`、`-e`、空白项、重复项与 >32 项。
- `modules/package.py`：新增 venv 工具链——`install_module_venv`、`read_ready_venv`、`dependency_digest`、`remove_module_venv`。依赖为空不建 venv；非空时 `sys.executable -m venv <模块版本目录>/venv`，再 `venv/python -m pip install --disable-pip-version-check --no-input --no-warn-script-location <deps…>`，超时 300s；成功后写 `venv/.ready`（依赖 hash + 列表 + 时间 + Python 版本）与 `eclipse_health_module.pth`（模块目录入 sys.path）；任一步失败删除半成品 venv。
- `modules/manager.py`：
  - 安装在 `staging.replace(target)` 后、写注册表前创建 venv；失败回滚新版本目录，旧版本与旧 venv 保留。
  - `module.install` / `module.update` 审计新增 `dependencies` 与 `dependencyHash`，不记录 pip 输出；文件计数在装 venv 前完成。
  - `_describe` 返回 `dependencies`（manifest 摘要可见）。
  - 启动时按 `.ready` + hash 选择 `venv/Scripts/python.exe`，否则核心 Python；声明了依赖但环境未就绪时拒绝启动（`MODULE_CRASH`），日志记录实际解释器。
  - 回滚前校验目标版本 venv，缺失则先重建，失败保留当前版本。
  - 卸载删除模块根目录（含各版本 venv），`keep_data` 只保留 `data/`。
- `docs/MODULE_CONTRACT_V2.md`：新增 §12，覆盖字段规则、安装/联网/许可要求、解释器选择、失败 reason 表。
- `backend/tests/modules/test_module_venv.py`：33 个新用例。

## 验证

- 命令：`backend\.venv\Scripts\python.exe -m ruff check backend`
- 结果：pass（All checks passed）。
- 命令：`backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q`
- 结果：pass，175 passed（原 142 + 新 33），总耗时约 22s；最慢 `test_real_venv_install_from_local_wheel` 约 8s。
- 覆盖：无依赖不建 venv、空数组、合法/非法 PEP 508、URL/路径/`-e`、超 32 项、重复项、未知字段；真实离线 wheel 安装（`PIP_NO_INDEX` + 手工 wheel）并验证 `.pth` 让模块目录可导入；pip 失败/pip 缺失/超时清理半成品；安装失败保留旧版本且仍可 RPC；宿主选择 venv 或核心解释器；缺 venv 拒绝启动；回滚重建 venv；卸载清理 venv。

## 未做 / 偏离

- `errors.py` 不在本批所有权：未新增顶层错误码。安装失败返回 `MODULE_ERROR`，并在 `details.installError` 明确为 `MODULE_INSTALL_FAILED`，`details.reason` ∈ `venv-create-failed / python-venv-missing / pip-missing / pip-install-failed / timeout / disk-full / io-error`。
- `host.py` 不在所有权：未改环境变量注入。模块目录通过 venv 内 `eclipse_health_module.pth` 相对路径加入 `sys.path`（等价 PYTHONPATH，且规避中文路径解码问题）。
- `api.py` 不在所有权：安装预览与 manifest 投影暂未返回 `dependencies`；当前经 `ModuleManager` 摘要、审计与已安装 manifest 可见。
- `audit.py` 未改：现有 `module.install` 动作已能承载 `dependencyHash`，无需新 action。
- 回滚不删除被替换版本的 venv（保留可再次回滚）；卸载会删除全部版本 venv。
- 依赖安装只在安装/升级/回滚补齐时联网，不在 worker 运行时联网。

## 跨区需求（需要别的 Agent 或指挥官处理）

- `modules/api.py`：`_preview_payload`、`get_module_manifest` 增加 `"dependencies": list(manifest.dependencies)`，供安装前 UI 预览；前端显示依赖数量/列表。
- `modules/errors.py`：增加 `MODULE_INSTALL_FAILED`（建议 HTTP 502）并在 RPC 错误表登记，使顶层 code 与文档完全一致。
- 打包/发行批次：若 sidecar 以 PyInstaller 冻结运行，`sys.executable -m venv` 不适用；需随包提供可执行的基础 Python 或改走内置 uv。
- 并行 Agent：本批只改所有权内文件；若他人在 `api.py`/`errors.py` 有改动，请按上述补两处。

## 需要指挥官决策

- 是否要求声明 `dependencies` 的模块必须有 `network` 权限：当前只在安装阶段联网，worker 运行权限不因依赖放宽，故未强制。
- 依赖是否需要锁文件/哈希白名单（防供应链投毒）；本批按提示词不做签名校验。

## 建议下一批

- 依赖锁定（requirements hash）、离线 wheel 缓存与安装失败重试。
- 模块索引/下载与依赖预检合并；30 个模块适配时逐个验证 venv 体积与安装耗时。
