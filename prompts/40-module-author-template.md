# 40 · 第三方模块作者模板（Agent 直接使用）

> 用途：让任何 Agent 按统一流程写一个 eclipse health 模块，并完成打包、安装、调用、审计、卸载的闭环。
> 先读 `docs/MODULE_DEVELOPER_GUIDE_V1.md`（设计逻辑、能力矩阵、已知限制）。
> 项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 0. 先判断：你的模块属于哪一类

| 你想做 | 当前可交付 | 备注 |
|---|---|---|
| 独立算法/工具，调用方通过 RPC 用 | **可以** | 本文主路径 |
| 分析模型，想出现在「分析」按钮 | **不能只交模块** | 需核心通用 analysis loader（指南 §6.1） |
| 导入格式，想出现在导入页 | **不能只交模块** | 需核心 adapter bridge（§6.2） |
| 报告模板/导出器 | **不能只交模块** | 需 exporter registry（§6.3） |
| LLM 工具 | **不能只交模块** | 需 ai-tool registry（§6.4） |
| 首页组件/主题/语言包 | **不能只交模块** | 需声明式 UI 渲染器（§6.5） |
| 数据源/实时流 | **未实现** | 后续批次 |

如果属于后几类：**先做 RPC 版模块**（本文流程），并在报告中写清「要自动接入 UI/流水线还缺哪段核心 glue」，不要假装已经接好。

## 1. 必读

1. 根目录 `CLAUDE.md`
2. `prompts/00-COMMON.md`
3. `docs/MODULE_DEVELOPER_GUIDE_V1.md`
4. `docs/MODULE_CONTRACT_V1.md`：§1 包格式、§2 manifest、§4 生命周期、§5 RPC、§6 权限、§11 安全、§12 错误码
5. `schemas/module.schema.json`
6. `modules/demo.echo/`：manifest、`src/main.py`、`checksums.json`
7. `scripts/pack_demo.py`

## 2. 交付物

在 `modules/<your-module-id>/` 下：

```
module.json
src/main.py
models/            # 可选
README.md
checksums.json     # 打包时生成
```

以及 `reports/module-<module-id>-report.md`。

## 3. 步骤

### 3.1 定 manifest

- `id`：`io.github.<owner>.<name>`（社区）或 `org.eclipsehealth.<name>`（官方）；安装后不可变。
- `version`：SemVer；`apiVersion`：`1.0`；`engines.eclipse`：`>=1.0 <2.0`。
- `type`：按用途选（`ai-tool`、`analysis-model`、`device-adapter` 等）；`contributes` 先按目标写，当前核心只保存不消费。
- `permissions`：最小集；高风险（`records:delete`、`network`、`ui:custom`）默认不授予。
- `entry.python`：脚本路径；**核心执行脚本，不调用 `factory`**。
- `resources`：`memoryMb/cpu/startupTimeoutMs` 写实际值。

### 3.2 写 worker

- stdio JSON-RPC 2.0，每行一条 JSON；stdout 只写协议消息，日志写 stderr 或文件。
- 必须实现：`initialize`、`health`、`deactivate`。
- 业务方法：自己定义；错误用 `error.data.code`（契约 §12）。
- 环境变量：`ECLIPSE_MODULE_ID/API_VERSION/PERMISSIONS/LOCALE/MODULE_DIR`。
- 大结果（>4MB）写临时文件，返回 `{resultRef:{path,sha256,bytes}}`；不要把大数组塞进一行 JSON。
- 不 import `eclipse_health_backend.*`（共用环境不等于可以依赖核心内部）。
- 不直接访问 SQLite/波形；需要数据时由调用方通过 params 传入路径/数组。

### 3.3 自测（不装进核心）

```powershell
# 用 demo 的 stdio 方式手动喂一行
"{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}" | backend\.venv\Scripts\python.exe modules\<id>\src\main.py
```

### 3.4 打包

```powershell
backend\.venv\Scripts\python.exe scripts\pack_demo.py --demo-dir modules\<id> --out dist\<id>-<version>.ehmod
```

确认 `checksums.json` 覆盖所有文件；`preview-upload` 能通过。

### 3.5 安装/启动/调用/审计/卸载

```powershell
# 先启动后端（另开终端）
backend\.venv\Scripts\python.exe -m uvicorn eclipse_health_backend.app:app --port 8789

curl.exe -X POST http://127.0.0.1:8789/api/v1/modules/preview-upload -F "file=@dist\<id>-<version>.ehmod"
curl.exe -X POST http://127.0.0.1:8789/api/v1/modules/install-upload -F "file=@dist\<id>-<version>.ehmod" -F "enable=true"
curl.exe -X POST http://127.0.0.1:8789/api/v1/modules/<id>/start
curl.exe -X POST http://127.0.0.1:8789/api/v1/modules/<id>/rpc -H "Content-Type: application/json" -d "{\"method\":\"echo\",\"params\":{\"text\":\"hello\"}}"
curl.exe "http://127.0.0.1:8789/api/v1/modules/audit?moduleId=<id>&limit=20"
curl.exe -X DELETE "http://127.0.0.1:8789/api/v1/modules/<id>?keepData=true"
```

### 3.6 失败路径

至少验证一个：

- 非法 params → `INVALID_INPUT`；
- 模块抛异常 → `MODULE_ERROR`；
- 超时 → `MODULE_TIMEOUT`；
- 未授权核心回调 → `PERMISSION_DENIED`；
- 坏包/篡改 checksums → `CHECKSUM_MISMATCH` / `INVALID_PACKAGE`。

## 4. 验收清单

- [ ] manifest 通过 schema 校验
- [ ] `initialize/health/deactivate` 正常
- [ ] 主方法正常 + 至少一个错误路径
- [ ] 打包 → preview → install → start → rpc → audit → uninstall 全部通过
- [ ] 日志不含健康数据/密钥/绝对路径
- [ ] 大结果走文件
- [ ] 报告写清：模块类型、当前能自动接入到哪一步、缺哪段核心 glue

## 5. 报告

`reports/module-<id>-report.md`：

```markdown
# 模块报告 · <id>
状态：完成 / 部分完成 / 阻塞
## 模块
- 类型、权限、方法、contributes
## 验证
- 打包/安装/启动/调用/审计/卸载结果
## 当前接入边界
- 只能 RPC / 已自动接入（列出证据）
- 需要核心补的 glue（文件/函数）
## 未做 / 风险
```

## 6. 明确不做

- 不修改核心业务代码（除非任务明确要求做核心 glue）。
- 不安装系统级依赖、不新增核心 Python 依赖。
- 不把健康数据/密钥写进日志、不联网上传。
- 不假装 UI 已接入；当前声明式渲染器未实现。
