# H1 · 每模块独立 venv（30 个模块的前置能力）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V1.md` §6、`docs/MODULE_CONTRACT_V2.md`、`modules/manager.py`、`modules/package.py`。
> **思考强度：low。** 但这是安装/运行安全相关，必须把失败路径写清楚。

## 目标

模块 manifest 可声明 Python 依赖；安装时在模块版本目录创建独立 venv 并安装锁定依赖；worker 用该 venv 的 Python 启动。无依赖模块继续复用核心 venv。安装包不变大，依赖按需联网安装。

## 交付

### 1. Manifest / Schema

- `schemas/module.schema.json`：新增可选 `dependencies`：
  - 数组，≤32 项，每项为 PEP 508 字符串（如 `pandas>=2.1,<3`、`pyedflib==0.1.38`），禁止 URL/path/`-e`；
  - 顶层 `additionalProperties` 仍禁止未知字段。
- `modules/manifest.py`：`Manifest.dependencies: tuple[str, ...]`，校验格式；`module.json` 读写保持兼容。
- `docs/MODULE_CONTRACT_V2.md`：补 `dependencies` 字段、安装/联网/许可要求。

### 2. 安装 venv

- `modules/package.py` / `modules/manager.py`：
  - 安装/升级时，若 `dependencies` 非空：
    1. 在模块版本目录创建 `venv/`：`sys.executable -m venv <dir>`（已确认 pip 24.2 可用）；
    2. `venv/Scripts/python.exe -m pip install --disable-pip-version-check --no-input --no-warn-script-location <deps...>`，超时（如 300s），输出截断记日志；
    3. 成功后写 `venv/.ready`（含依赖列表 hash、时间）；失败删除半成品 venv 并让安装失败，不能留下“已安装但跑不起来”的状态；
  - 依赖为空：不创建 venv，worker 用 `sys.executable`；
  - 升级/替换：先装新版本 venv，成功后再切换；失败保留旧版本；
  - 卸载/回滚：删除对应 venv；不递归删用户数据。
- `modules/manager.py` 启动 host 时：
  - 若版本目录有 `.ready` venv → 用 `venv/Scripts/python.exe` 启动 worker，并把模块目录加入 `PYTHONPATH`；
  - 否则用核心 Python；日志记录实际解释器。
- 权限/审计：安装依赖视为 `network` 行为；安装前把依赖列表返回 UI（预览）；审计 `module.install` 记录依赖列表 hash，不记录完整输出。
- 失败路径：pip 不存在/网络失败/依赖冲突/超时/磁盘不足 → 明确 `MODULE_INSTALL_FAILED`，message 可读，原模块状态不变。

### 3. 测试

- `backend/tests/modules/test_module_venv.py`（新建）：
  - 无依赖模块不建 venv；
  - 依赖格式校验（合法/非法 URL/path/空数组）；
  - venv 创建成功（用空依赖 + 一个本地可安装的纯 Python 测试包；若无法离线，用 `pip install --no-index` 的本地 wheel fixture，或 mock subprocess 并断言参数）；
  - pip 失败 → 安装失败、半成品清理、旧版本保留；
  - host 选择 venv 解释器；
  - 卸载清理 venv。
- 现有模块测试全绿。

## 文件所有权（只改这些）

- `schemas/module.schema.json`
- `backend/src/eclipse_health_backend/modules/manifest.py`
- `backend/src/eclipse_health_backend/modules/package.py`
- `backend/src/eclipse_health_backend/modules/manager.py`
- `backend/src/eclipse_health_backend/modules/audit.py`（仅新增 action）
- `backend/tests/modules/**`
- `docs/MODULE_CONTRACT_V2.md`
- `reports/H1-*.md`

## 明确不做

- 不做模块索引/下载；不做依赖签名校验（后续）；不改前端（安装预览可只更新 manifest 摘要）。
- 不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q
```

报告 `reports/H1-module-venv-report.md`，≤80 行：依赖格式、venv 路径/失败回滚、解释器选择、测试输出、未做项。
