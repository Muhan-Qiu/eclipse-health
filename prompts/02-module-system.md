# B1-02 · 模块系统内核

> 难度：极难 4/4 · 建议思考强度：**max**（不可用则 xhigh） · 批次：B1 地基
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 这是全项目最关键的架构件。**范围控制比功能数量重要**；做不完就报告，不要开新方向。

## 1. 必读

- `docs/MODULE_CONTRACT_V1.md`：§1 包格式、§2 manifest、§3 类型、§4 生命周期、§5 RPC、§6 权限、§10 版本、§11 安全与审计、§12 错误码。
- `docs/V3_MODULAR_ECOSYSTEM.md`：§4 运行时、§6 信任、§11 开发者体验（只看这些节）。
- `docs/DATA_SCHEMA_V1.md`：§11 存储映射中的 `modules`、`audit_log`。
- `docs/V3_BUILD_PLAN.md`：所有权矩阵。

## 2. 目标

实现**本地模块内核**：一个 `.ehmod` 能被校验、安装、启用、启动、调用、审计、卸载；用一个自带的 echo 模块证明全链路。B1 不做真实 Samsung/Apple 适配、不做注册表下载、不做签名公钥体系、不做每模块独立 venv。

## 3. 你必须交付

1. **Manifest 事实源**
   - `schemas/module.schema.json`：JSON Schema 2020-12，覆盖 §2 全部字段与约束（id 反向域名、SemVer、apiVersion、engines、type 枚举、permissions 枚举、entry、contributes、resources）。
   - `schemas/examples/`：至少 3 个合法 manifest（`device-adapter`、`analysis-model`、`ai-tool`）。
   - 运行时用 Pydantic v2 或 `jsonschema` 校验；错误信息可读。
2. **`.ehmod` 安装器**
   - ZIP 解析；防路径穿越（`..`、绝对路径、符号链接）；必须含 `module.json`、`src/`；`checksums.json` 存在则逐文件校验，缺失则记录警告（B1 不强制）。
   - 安装到 `backend/.data/modules/<id>/<version>/`；原子安装（临时目录 → rename）；失败清理。
   - 支持 `uninstall(id, keepData: bool)`；支持 `update` 到新版本并保留旧版本目录以便回滚（最简实现即可）。
   - 不做网络下载；只接受本地 `.ehmod` 路径（上传/选择文件由 API 层传路径）。
3. **注册表与状态**
   - 数据库表（注册到 B1-01 的 `db/base.py` 的 `Base`）：`installed_modules`（id, version, enabled, manifest_json, installed_at, updated_at）、`module_permissions`（module_id, scope, granted_at）、`audit_log`（id, module_id, action, scope, detail_json, created_at）。
   - 状态机：`installed → enabled → running → stopped/disabled → uninstalled`；崩溃可恢复。
4. **权限**
   - 定义 §6 的 scope 枚举；安装时写入授权；提供查询/撤销；worker 启动时注入已授权 scope；RPC 越权调用返回标准错误码。
   - B1 不实现 UI 授权弹窗（B2 做），但 API 要能列出「安装时将请求的权限」。
5. **审计**
   - 只追加；记录 `module.install/uninstall/enable/disable`、`permission.grant/revoke`、`rpc.call`（方法名、耗时、成功/失败）、`data.read/write`（预留）。
   - **绝不记录波形内容、notes、payload 原文**；只记录 ID/范围/大小。
   - `GET /api/v1/modules/audit` 支持按模块/动作/时间过滤。
6. **Worker 宿主（核心难点）**
   - 每个模块一个子进程，stdio + 按行 JSON-RPC 2.0；懒启动；`initialize` 握手（apiVersion、权限、locale、config）；请求超时；崩溃检测与有限重启（如 1 次）；退出时清理。
   - 注入环境变量：`ECLIPSE_MODULE_ID`、`ECLIPSE_RPC_TOKEN`、`ECLIPSE_API_VERSION`；工作目录限定模块目录；不继承无关环境变量。
   - 用当前解释器 `sys.executable` 启动（venv-per-module 留到 B3，接口要预留 `venvPath`）。
   - 日志写 `backend/.data/logs/modules/<id>.log`，轮转简单实现即可；不要打印到主进程 stdout。
   - 大数组走文件句柄的路径要预留，但 B1 可只实现小 JSON。
7. **API（供 B1-01 挂载）**
   - `modules/api.py` 暴露 `router`（**不带** `/api/v1` 前缀）；端点：
     - `GET /modules`（列表 + 状态 + 权限）
     - `POST /modules/install`（body: 本地 `.ehmod` 路径 + 是否启用）
     - `POST /modules/{id}/enable|disable|start|stop`
     - `DELETE /modules/{id}?keepData=true|false`
     - `GET /modules/{id}/permissions`、`POST/DELETE /modules/{id}/permissions/{scope}`
     - `GET /modules/audit`
     - `POST /modules/{id}/rpc`（调试用，调用指定方法）
   - 所有错误用 §12 错误码；不泄露文件系统绝对路径。
8. **示例模块 `modules/demo.echo/`**
   - 完整可打包的目录：`module.json`、`src/main.py`（stdio JSON-RPC，方法 `initialize`、`hello`、`echo`、`fail`）、`checksums.json`、`README.md`。
   - 提供 `scripts/pack_demo.py`（或等价方式）生成 `.ehmod`，供测试与验收。
9. **测试**
   - `backend/tests/modules/`：manifest 校验（合法/非法）、路径穿越拒绝、安装/启用/调用/审计/卸载全链路、权限越权拒绝、worker 崩溃恢复、并发两次安装同一模块的幂等/冲突。
   - 测试用临时 `EH_DATA_DIR`；不依赖网络。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/modules/**
backend/src/eclipse_health_backend/audit/**        # 若拆分，也可放 modules/audit.py
schemas/**
modules/**
backend/tests/modules/**
backend/tests/fixtures/modules/**
scripts/**                                         # 仅模块打包脚本；不要放其他东西
```

只读：`backend/src/eclipse_health_backend/db/base.py`（B1-01 所有）、`app.py`、`settings.py`、`backend/pyproject.toml`。

不要动：`api/`、`domain/`、`storage/`、`analysis/`、`src/`、`docs/`、`prompts/`、`uploads/`。不要改 `pyproject.toml`；缺依赖写报告。

## 5. 与 B1-01 的契约

- 导入 `from ..db.base import Base, engine, get_session` 来注册你的 SQLModel 表；若这些接口与你预期不同，按它的实际签名适配，不要改它。
- 若开工时 `db/base.py` 还不存在：先做 manifest / 安装器 / RPC 宿主（不依赖 DB），等它出现后再接表；**不要自建第二套 Base/engine**。
- 提供 `eclipse_health_backend/modules/api.py` 的 `router`；B1-01 负责挂载 `/api/v1/modules`。你的路由内部路径从 `/` 开始（例如 `@router.get("")` 对应 `/api/v1/modules`）。
- 不要修改 `app.py`；如果需要启动时初始化，提供 `init_module_system()` 供 B1-01 调用，并在报告里说明。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q
# 全链路演示（脚本名可自定，必须在报告写明）：
backend\.venv\Scripts\python.exe scripts\pack_demo.py
# 然后通过 API 或测试安装 modules/demo.echo 产出的 .ehmod
```

报告写：全链路步骤、审计记录示例、崩溃恢复如何验证、未实现项。

## 7. 明确不做

真实设备格式解析、模型贡献、声明式 UI 渲染、沙箱 iframe、注册表/索引/下载、代码签名公钥验证、每模块独立 venv、跨模块互调、MCP。这些都留到 B2/B3/B4。
