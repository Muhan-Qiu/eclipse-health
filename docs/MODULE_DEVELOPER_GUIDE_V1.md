# eclipse health · 第三方模块接入指南 v1

> 2026-10-30 · 面向模块作者、Agent、核心维护者
> 事实源：`docs/MODULE_CONTRACT_V1.md`、`schemas/module.schema.json`、`modules/demo.echo/`、`modules/official/cardia/`、`backend/src/eclipse_health_backend/modules/`
> 结论口径：**「能装、能启、能调」已经成立；「自动出现在主界面/导入/分析/报告/LLM 工具里」除内置 Cardia 外尚未接线。**

## 0. 一句话结论

| 你想要的「接进来」 | 现在能不能 | 难度 |
|---|---|---|
| 打包 `.ehmod`、安装、启停、授权、审计 | **可以** | 低 |
| 通过 `/api/v1/modules/{id}/rpc` 调用模块方法 | **可以** | 低 |
| 模块读写记录/波形/分析（直接访问数据库） | **不可以**，只能由核心传数据 | 中（核心补回调） |
| 第三方分析模型自动出现在「分析」按钮/引擎选择 | **不可以**，当前只有 Cardia 内置桥接 | 中（核心补通用 loader） |
| 第三方导入器自动出现在「导入」格式列表 | **不可以**，导入器是核心内置 | 中（核心补 adapter bridge） |
| 第三方导出器/报告模板自动出现 | **不可以**，报告生成是核心内置 | 中 |
| 第三方 AI 工具自动出现在助手工具列表 | **不可以**，LLM 工具是核心内置 | 中低 |
| 第三方首页组件/主题/语言包自动渲染 | **不可以**，声明式 UI 渲染器尚未实现 | 高 |
| 模块跑在独立 venv、代码签名、在线注册表 | **未实现**（当前共用核心 Python、仅 checksums） | 高，后续批次 |

**适合现在做的模块**：独立算法/工具型模块（通过 RPC 调用）、分析模型原型（先走 RPC，后续接 UI）、数据源原型、批处理脚本。
**现在不适合做的模块**：直接替换导入/报告/LLM/首页 UI 的模块；这类需要核心侧先补 contribution loader。

---

## 1. 设计逻辑

### 1.1 为什么是「核心 + 独立进程模块」

- 核心（Tauri/React + FastAPI + SQLite）负责：数据、权限、UI、审计、生命周期。
- 模块是独立 Python 进程，核心**不 import 模块代码**；双方只通过 stdio JSON-RPC 通信。
- 目的：模块可安装/卸载/替换/崩溃隔离；官方与第三方同一套接口。
- 代价：模块不能直接摸数据库/波形文件；所有数据由核心通过 RPC 参数或临时文件句柄传入。

### 1.2 `.ehmod` 包

ZIP 包，最小结构：

```
module.json          # 必需，manifest
src/                 # 必需，代码
models/              # 可选，本地权重
ui/                  # 可选，声明式 UI
checksums.json       # 可选但推荐；安装时逐文件校验
signature.json       # 预留，当前不做公钥验证
README.md / LICENSE
```

安装到：`<dataDir>/modules/<module-id>/<version>/`。
开发期 dataDir 默认 `backend/.data`；生产为 `%LOCALAPPDATA%\eclipse-health`。

### 1.3 Manifest 是事实源

- `schemas/module.schema.json` 是唯一事实源（JSON Schema 2020-12），运行时用 `jsonschema` 校验，再映射到 Pydantic。
- 关键字段：`id`（反向域名、安装后不可变）、`version`（SemVer）、`apiVersion`、`engines.eclipse`、`type`、`permissions`、`entry.python`、`contributes`、`resources`。
- **注意**：`entry.factory` 目前只是元数据，核心**不调用**它；核心直接执行 `entry.python` 脚本。模块必须在脚本里自己跑 stdin/stdout 循环。

### 1.4 生命周期

```text
discover → verify → resolve → install → enable → start → initialize → operate
                                                         ↓
                                              crash / disable / stop / uninstall
```

- `start`：核心启动 worker，注入 `ECLIPSE_MODULE_ID`、`ECLIPSE_RPC_TOKEN`、`ECLIPSE_API_VERSION`、`ECLIPSE_PERMISSIONS`、`ECLIPSE_LOCALE`、`ECLIPSE_MODULE_DIR`。
- `initialize`：模块返回能力/健康状态；核心不强制字段，但建议返回 `{moduleId, apiVersion, capabilities}`。
- 崩溃：自动重启，连续 3 次失败后停在 `crashed`，需手动 `start`。
- `uninstall`：`keepData=true` 保留模块目录/数据；`false` 删除。

### 1.5 RPC 协议

- JSON-RPC 2.0，**每行一条 JSON**，stdin/stdout。
- 请求：`{"jsonrpc":"2.0","id":1,"method":"echo","params":{...}}`
- 响应：`{"jsonrpc":"2.0","id":1,"result":{...}}` 或 `{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"...","data":{"code":"INVALID_INPUT"}}}`
- 单条消息 ≤4MB（`MAX_INLINE_JSON_BYTES`）；大数组/大结果请写临时文件，把路径+sha256 放进 JSON。
- 模块 → 核心的受限回调：当前只实现 `log.write`、`events.emit`、`audit.write`。`records.*`、`signals.read`、`files.*`、`llm.complete` 等已声明权限但**尚未实现**，会返回 `NOT_IMPLEMENTED`。

### 1.6 权限与审计

Scope 目录（`permissions.py`）：

| scope | 风险 | 含义 |
|---|---|---|
| `records:read` | low | 读记录/测量/分析 |
| `records:write` | medium | 创建/更新记录 |
| `records:delete` | **high** | 删除记录；默认不授予 |
| `files:user-selected` | low | 读用户选择的文件 |
| `files:export` | medium | 写入用户确认的目录 |
| `network` | **high** | 访问 manifest `allowedHosts` |
| `llm` | medium | 调用用户配置的 LLM |
| `models:download` | medium | 下载权重 |
| `ui:custom` | **high** | 沙箱自定义 UI |
| `system:notify` | low | 系统通知 |
| `system:background` | medium | 最小化后继续运行 |

- 安装时写入授权；升级新增权限**不自动授予**。
- 运行时通过 `ECLIPSE_PERMISSIONS` 告诉模块已授权项；核心回调会校验。
- 审计表 append-only；记录安装/启停/权限/RPC 调用，不记录波形/notes 内容。

### 1.7 数据与隐私

- 模块**不直接访问** SQLite/波形文件；核心通过参数/临时文件传数据。
- 模块返回结果必须是可 JSON 序列化的数据；大结果用 `resultRef` 文件。
- 不记录患者姓名/notes/原始文件名；ID 与哈希可以。
- 模块目录视为只读；需要写临时文件时用系统 temp 或核心传入的路径（模块数据目录 API 尚未实现）。

### 1.8 UI 设计

- 官方 UI 走设计令牌（`--eh-*`）+ 声明式组件；第三方任意 React/CSS 只能进沙箱 iframe 或主题作用域（契约 §8）。
- **当前核心还没有声明式组件渲染器**；`contributes.ui` 会被 manifest 保存，但不会渲染。B4-06 已实现模块安装/权限/审计 UI，但**不渲染模块贡献的页面/组件**。

### 1.9 信任边界（重要）

- 当前模块与核心**共用同一个 Python 环境和 `sys.executable`**；没有 per-module venv、没有 OS 级沙箱。
- `PATH` 会继承；`network` 权限只是声明，运行时**没有**网络隔离。
- 只安装你信任的 `.ehmod`；社区模块在补齐沙箱/签名/每模块 venv 前不要当不可信代码运行。
- `checksums.json` 能防损坏/篡改包内文件，但**不能**证明作者身份（`signature.json` 尚未验证）。

---

## 2. 当前能力矩阵（按模块类型）

| type | 安装/启停/RPC | 自动接进主流程 | 缺什么 | 核心工作量 |
|---|---|---|---|---|
| `device-adapter` | ✅ | ❌ | 核心导入 registry 没有模块 loader；`contributes.importFormats` 未被消费 | 中：新增 module↔ImportAdapter 桥 |
| `signal-engine` | ✅ | ❌ | 没有 pipeline contribution loader | 中高 |
| `analysis-model` | ✅ | ⚠️ 仅 Cardia | `analysis_service/bridge.py` 写死 `org.eclipsehealth.cardia`、`warmup/health/analyze`；没有通用引擎注册/选择 | 中：抽象为通用 model bridge + UI 引擎选择 |
| `health-domain` | ✅ | ⚠️ 数据层部分 | `recordType/payload` 能存；没有 recordType 注册、导航、页面贡献 | 中高 |
| `dashboard-widget` | ✅ | ❌ | 没有声明式组件渲染器 | 高 |
| `exporter` | ✅ | ❌ | 报告生成写死在内置 `reports/`；没有 exporter registry | 中 |
| `ai-tool` | ✅ | ❌ | `llm/tools.py` 是内置工具；没有模块工具 loader | 中低 |
| `theme` | ✅ | ❌ | 没有主题贡献加载/校验 | 中 |
| `locale` | ✅ | ❌ | 没有语言包贡献加载 | 低中 |
| `data-source` | ✅ | ❌ | 未实现实时数据流 | 高，后续 |

> 说明：✅ 表示模块能被安装、授权、启动、通过 `/rpc` 调用；不代表 UI/主流程会自动用它。

---

## 3. 三条接入路径

### 路径 A：纯 RPC 模块（现在就能用，推荐先做）

适合：独立算法、批量处理、分析模型原型、数据转换、外部工具桥。

流程：

1. 写 `module.json` + `src/main.py`（stdio JSON-RPC 循环）。
2. `pack_demo.py` 或自己的打包脚本生成 `.ehmod`。
3. 通过 `POST /api/v1/modules/preview-upload` 预览权限，再 `POST /install-upload` 安装。
4. `POST /modules/{id}/start`，再 `POST /modules/{id}/rpc` 调用。
5. 结果由调用方（你的脚本/另一个模块/核心后续 glue）消费。

限制：不会自动出现在 UI；不能直接查库；不能读波形文件（除非核心把路径传给你）；大结果走文件。

### 路径 B：接进核心流水线（需要核心侧小改动）

| 目标 | 核心改动 | 模块侧提供 | 工作量 |
|---|---|---|---|
| 第三方分析模型出现在「分析」 | 通用 `AnalysisModelBridge`：从 manifest `contributes.models` 读引擎，替换写死的 Cardia 常量；引擎注册/选择 API；结果映射 | `initialize/warmup/health/analyze` RPC；结果符合 `AnalysisResult` | 1–2 天 |
| 第三方导入格式 | `importers/registry.py` 增加 `ModuleImportAdapter`，把 `detect/preview/parse` 桥到 RPC；文件走临时句柄 | 三个 RPC 方法 + `contributes.importFormats` | 1–2 天 |
| 第三方导出器 | 新增 exporter registry；`reports/service.py` 按 manifest 选择内置或模块；文件返回 | `export` RPC，返回文件路径/字节 | 1 天 |
| 第三方 AI 工具 | `llm/tools.py` 增加模块工具注册；工具调用桥到 RPC；权限 `llm/records:read` | `tool.call` RPC + `contributes.tools` | 0.5–1 天 |
| 声明式 UI/主题/语言包 | 贡献加载器 + 组件白名单 + 渲染器 + sandbox | `ui/` JSON 或 iframe bundle | 3–5 天 |

### 路径 C：UI/主题/语言包（最晚）

需要先实现「声明式组件渲染器」和贡献注册表；当前 `contributes.ui` 只被保存，不会渲染。主题/语言包同样没有加载器。建议放到模块生态稳定后。

---

## 4. 最小模块教程（可直接照做）

### 4.1 目录

```
my-module/
  module.json
  checksums.json        # 打包时生成
  README.md
  src/main.py
  models/               # 可选
```

### 4.2 `module.json`（最小可用）

```json
{
  "schemaVersion": "1.0",
  "id": "io.github.yourname.my-module",
  "name": "My Module",
  "description": "What it does, in one sentence.",
  "version": "0.1.0",
  "apiVersion": "1.0",
  "engines": { "eclipse": ">=1.0 <2.0" },
  "type": "ai-tool",
  "author": { "name": "Your Name" },
  "license": "MIT",
  "permissions": ["files:user-selected"],
  "entry": { "python": "src/main.py", "factory": "create_module" },
  "contributes": {
    "tools": [
      {
        "id": "my.tool",
        "name": "My Tool",
        "description": "Does one thing.",
        "inputSchema": { "type": "object", "properties": { "text": { "type": "string" } }, "required": ["text"] }
      }
    ]
  },
  "resources": { "memoryMb": 256, "cpu": 0.5, "startupTimeoutMs": 5000 }
}
```

- `id` 必须反向域名；不要用 `io.github.<owner>` 以外的社区身份规则之外的格式（注册表未上线，但先按此写）。
- `type` 见 §2；`contributes` 当前只被保存，不会被核心消费（Cardia 也是硬编码桥）。
- `factory` 目前不执行；真正入口是 `entry.python` 脚本。

### 4.3 `src/main.py`（最小 stdio 循环）

```python
from __future__ import annotations
import json, os, sys
from typing import Any

MODULE_ID = os.environ.get("ECLIPSE_MODULE_ID", "")
API_VERSION = os.environ.get("ECLIPSE_API_VERSION", "")
PERMISSIONS = [p for p in os.environ.get("ECLIPSE_PERMISSIONS", "").split(",") if p]

class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data

def write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {"moduleId": MODULE_ID, "apiVersion": API_VERSION, "permissions": PERMISSIONS,
                "capabilities": ["initialize", "echo", "health", "deactivate"]}
    if method == "echo":
        text = params.get("text")
        if not isinstance(text, str):
            raise RpcError(-32602, "params.text must be a string", {"code": "INVALID_INPUT"})
        return {"text": text, "length": len(text)}
    if method == "health":
        return {"ok": True}
    if method == "deactivate":
        return {"ok": True}
    raise RpcError(-32601, f"method not found: {method[:64]}", {"code": "METHOD_NOT_FOUND"})

def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if not isinstance(msg, dict) or "method" not in msg or "id" not in msg:
            continue
        try:
            write({"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg["method"], msg.get("params") or {})})
        except RpcError as e:
            err = {"code": e.code, "message": e.message}
            if e.data is not None:
                err["data"] = e.data
            write({"jsonrpc": "2.0", "id": msg["id"], "error": err})
        except Exception as e:
            write({"jsonrpc": "2.0", "id": msg["id"],
                   "error": {"code": -32603, "message": f"internal error: {type(e).__name__}",
                             "data": {"code": "MODULE_ERROR"}}})
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

要点：

- 不要 print 到 stdout（会破坏 RPC）；日志写 stderr 或 `ECLIPSE_MODULE_DIR` 下的文件。
- 每行必须是一个完整 JSON；不要多行格式化。
- 收到 `deactivate` 返回后退出循环。
- 超时/崩溃由核心处理；不要自己 kill 父进程。
- 大结果写临时文件，返回 `{ "resultRef": { "path": "...", "sha256": "...", "bytes": 123 } }`。

### 4.4 打包

复刻 `modules/demo.echo`，或用现有脚本：

```powershell
backend\.venv\Scripts\python.exe scripts\pack_demo.py --demo-dir modules\my-module --out dist\my-module-0.1.0.ehmod
```

`pack_demo.py` 会生成 `checksums.json` 并打包；生产模块建议自己写打包脚本，确保 `checksums.json` 包含所有文件。

### 4.5 安装（REST）

```powershell
# 1) 预览：manifest + 权限 + 校验和
curl.exe -X POST http://127.0.0.1:8765/api/v1/modules/preview-upload `
  -F "file=@dist\my-module-0.1.0.ehmod"

# 2) 安装并启用；permissions 只列你确认的 scope
curl.exe -X POST http://127.0.0.1:8765/api/v1/modules/install-upload `
  -F "file=@dist\my-module-0.1.0.ehmod" `
  -F "enable=true" `
  -F "permissions=[\"files:user-selected\"]"
```

本地开发也可以走路径安装：

```powershell
curl.exe -X POST http://127.0.0.1:8765/api/v1/modules/install `
  -H "Content-Type: application/json" `
  -d "{\"path\":\"C:\\\\path\\\\to\\\\my-module-0.1.0.ehmod\",\"enable\":true}"
```

### 4.6 启动与调用

```powershell
curl.exe -X POST http://127.0.0.1:8765/api/v1/modules/io.github.yourname.my-module/start

curl.exe -X POST http://127.0.0.1:8765/api/v1/modules/io.github.yourname.my-module/rpc `
  -H "Content-Type: application/json" `
  -d "{\"method\":\"echo\",\"params\":{\"text\":\"hello\"}}"
```

预期：`{"result":{"text":"hello","length":5}}`（实际外层由 API 包装，见 OpenAPI）。

### 4.7 审计与卸载

```powershell
curl.exe "http://127.0.0.1:8765/api/v1/modules/audit?moduleId=io.github.yourname.my-module&limit=20"
curl.exe -X DELETE "http://127.0.0.1:8765/api/v1/modules/io.github.yourname.my-module?keepData=true"
```

### 4.8 日志与排错

- 模块日志：`<dataDir>/logs/modules/<module-id>.log`
- 核心日志：`<dataDir>/logs/backend.log`（B4 起）
- 状态：`GET /api/v1/modules/{id}` 看 `state`、`lastError`、`restartCount`
- 常见错误：`MODULE_CRASH`（进程退出）、`MODULE_TIMEOUT`（超时）、`MODULE_ERROR`（模块内部异常）、`PERMISSION_DENIED`（核心回调越权）、`CHECKSUM_MISMATCH`（包被改）、`INCOMPATIBLE_API`（apiVersion/engines 不匹配）。

### 4.9 权限行为

- 安装时 `permissions` 必须 ⊆ manifest；高风险 scope 需要显式列出。
- 运行时 `ECLIPSE_PERMISSIONS` 只含已授权项。
- 模块调用核心 `records.*` 等会先检查 scope，但当前实现只完成 `log.write`/`events.emit`/`audit.write`；其他会返回 `NOT_IMPLEMENTED`，不要依赖。

---

## 5. Agent 直接上手模板

给 Agent 的现成提示词：`prompts/40-module-author-template.md`。
它包含：

- 必读文档顺序；
- 选择模块类型的决策树；
- 生成 `module.json`/`src/main.py`/`checksums.json`/README 的步骤；
- 打包、安装、调用、审计、卸载的验收命令；
- 明确告知：如果要做 UI/自动导入/自动分析接入，需要同时修改核心 glue，不能只交一个 `.ehmod`。

推荐用法：

> 阅读 `prompts/40-module-author-template.md`，按其中步骤实现并自测；完成后写 `reports/module-<id>-report.md`。

---

## 6. 核心侧接入方法（按类型，给维护者/Agent）

> 以下改动不在当前批次，属于把「能装能调」升级为「自动接入」的核心 glue。

### 6.1 通用 `analysis-model` loader

现状：`analysis_service/bridge.py` 写死 `CARDIA_MODULE_ID = "org.eclipsehealth.cardia"`、`CARDIA_ENGINE`、`warmup/health/analyze`；`analysis_service/service.py` 直接用它。第三方分析模块即使安装，也不会出现在分析按钮里。

建议：

1. 新建 `analysis_service/registry.py`：从已启用模块的 manifest `type=="analysis-model"` + `contributes.models` 生成引擎列表。
2. 把 `CardiaBridge` 抽象为 `AnalysisModelBridge(module_id, engine, model_id, model_version)`；`ensure_installed` 只对内置官方模块自动安装，第三方不自动装。
3. `warmup/health/analyze` 作为通用 RPC 约定；结果按 `AnalysisResult` 校验，缺字段给 `INVALID_INPUT`。
4. `GET /engine` 支持 `?moduleId=`；`POST /records/{id}/analyses` 的 `engine` 字段解析到模块。
5. 前端 `AnalysisPanel` 增加引擎选择（C7）；默认 Cardia；第三方引擎失败要可切回。

工作量：1–2 天；风险：结果结构不统一、不同模型对短记录/采样率要求不同，需要能力声明。

### 6.2 `device-adapter` 模块桥

现状：`importers/registry.py` 的 `build_default_registry()` 只注册内置 WFDB/CSV/EDF/SCP/Apple/Samsung/华为适配器；manifest `contributes.importFormats` 未被消费。

建议：

1. 定义 RPC 约定：`detect({fileName, headBase64?, path?})`、`preview({path, params})`、`parse({path, params})`；大文件传路径+sha256，模块只读临时目录。
2. 新建 `importers/module_adapter.py`，实现 `ImportAdapter` 协议，内部调 `manager.call(module_id, ...)`。
3. 安装/启用模块时，把 `contributes.importFormats` 注册进 `AdapterRegistry`；禁用/卸载时注销。
4. 权限：模块至少需要 `files:user-selected`；核心传入的临时路径由核心清理。
5. 前端导入格式下拉从 `GET /imports/formats` 读取，不再写死。

工作量：1–2 天；风险：大文件/多导联/单位传递、跨进程错误映射。

### 6.3 `exporter` 模块桥

现状：`reports/` 内置 PDF/PNG 生成；没有 exporter 注册表。

建议：

1. 定义 `export` RPC：输入报告内容（记录/分析/模板/脱敏标记），输出文件路径 + mime + sha256。
2. `reports/service.py` 先查内置模板，再查已启用 exporter 模块；失败回退内置。
3. 权限：`files:export`；核心只接受模块写到用户确认目录/临时目录的文件。
4. UI 报告页增加模板来源标记（内置/模块）。

工作量：约 1 天。

### 6.4 `ai-tool` 模块桥

现状：`llm/tools.py` 是内置工具；`contributes.tools` 未被消费。

建议：

1. 启动时扫描已启用 `ai-tool` 模块，把 `contributes.tools` 注册到工具表。
2. 工具调用走 `manager.call(module_id, "tool.call", {name, arguments})`；参数按 `inputSchema` 校验。
3. 权限：`llm`（调用模型）+ 工具自身需要的 `records:read`；透明面板记录工具名/参数摘要。
4. 模型返回的工具调用与内置工具同一路由；失败/超时降级为文本说明。

工作量：0.5–1 天。

### 6.5 声明式 UI / 主题 / 语言包

现状：`contributes.ui` 只保存不渲染；没有组件白名单/沙箱。

建议：

1. 在 `schemas/module.schema.json` 固定 `contributes.ui` 结构（pages/widgets/theme/locales）。
2. 核心新增 `ui/contributions.py`：安装时校验组件/数据源/布局；前端从 `/ui/contributions` 拉取。
3. React 渲染器只允许白名单组件（`metric`、`line-chart`、`table`、`text`、`image`…），数据绑定只允许只读 query；禁止任意 JS。
4. 任意 React/CSS 走 iframe sandbox + postMessage 协议（契约 §5），权限 `ui:custom`。
5. 主题/语言包：加载 `theme.json` / `locale.json`，校验令牌白名单与文件大小（WOFF2 ≤2MB/模块 ≤4MB）。

工作量：3–5 天；这是最大的一块，建议在模块生态有真实需求后再做。

---

## 7. 版本、升级、卸载

- `schemaVersion`：manifest 结构版本，目前只支持 `1.0`。
- `apiVersion`：模块使用的契约版本；核心 `CORE_API_VERSION=1.0`；不兼容返回 `INCOMPATIBLE_API`。
- `engines.eclipse`：核心版本范围（SemVer）；不满足返回 `INCOMPATIBLE_API`。
- 升级：安装到新版本目录 → 原子切换；失败可 `POST /modules/{id}/rollback {version}`。
- 升级新增权限：不自动授予；UI/API 需重新确认。
- 卸载：`keepData=true` 保留模块数据；`false` 删除。
- 弃用策略：模块 API 严格 semver + 2 个 minor 弃用期（契约约定，当前尚未有弃用流程）。

---

## 8. 验收清单

### 模块作者

- [ ] `module.json` 通过 `schemas/module.schema.json` 校验
- [ ] `src/main.py` 在纯 Python 3.12 下能跑（不依赖核心包）
- [ ] `initialize` 返回 `moduleId/apiVersion/capabilities`
- [ ] `echo`/主方法正常；错误返回 `error.data.code`
- [ ] `checksums.json` 覆盖所有文件；`pack_demo.py` 能打包
- [ ] 预览/安装/启动/调用/审计/卸载全链路通过
- [ ] 崩溃/超时不会拖垮核心；日志写到 stderr/文件
- [ ] 大结果走文件，不塞 >4MB JSON

### 核心接入者（把模块接进 UI/流程）

- [ ] 模块类型有对应 loader，且禁用/卸载时会注销
- [ ] 权限在调用前校验；越权有审计
- [ ] 结果符合数据 Schema；错误映射到标准错误码
- [ ] 失败可回退（内置引擎/内置格式/内置报告）
- [ ] 前端有引擎/格式/模板来源标记与错误态
- [ ] 端到端测试覆盖：正常、权限拒绝、崩溃、超时、卸载

### 命令

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q
backend\.venv\Scripts\python.exe scripts\pack_demo.py
curl.exe -X POST http://127.0.0.1:8765/api/v1/modules/preview-upload -F "file=@dist\demo.echo-1.0.0.ehmod"
```

---

## 9. 已知限制与路线图

| 限制 | 影响 | 建议优先级 |
|---|---|---|
| 没有 per-module venv | 模块共用核心依赖；依赖冲突风险 | 中 |
| 没有 OS 沙箱 | 模块可读写文件/网络，权限只是声明 | 高（安全） |
| 签名未验证 | 无法证明作者/来源 | 中 |
| 没有在线注册表 | 只能本地 `.ehmod` 安装 | 中 |
| 没有 UI 渲染器 | UI/主题/语言包模块无法自动接入 | 高（生态） |
| 核心回调只实现 log/events/audit | 模块不能读记录/波形 | 高（能力） |
| 没有模块数据目录 API | 模块只能写临时目录/模块目录 | 中 |
| 没有通用 analysis/import/export/tool loader | 第三方功能不能自动出现在 UI | 高（生态） |

**推荐顺序**：通用 analysis loader → device adapter bridge → ai-tool registry → exporter registry → 模块数据目录/回调 → per-module venv/沙箱 → UI 渲染器 → 注册表/签名。

---

## 10. API / 环境变量 / 错误码速查

### REST（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/modules` | 已安装模块列表 |
| POST | `/modules/preview-upload` | 上传 `.ehmod` 预览（不安装） |
| POST | `/modules/install-upload` | 上传安装（`file`, `enable`, `permissions`） |
| POST | `/modules/install` | 本地路径安装（`{path, enable}`） |
| GET | `/modules/{id}` | 模块详情/状态 |
| GET | `/modules/{id}/manifest` | manifest |
| POST | `/modules/{id}/enable` / `disable` / `start` / `stop` | 生命周期 |
| POST | `/modules/{id}/rollback` | 回滚到旧版本 |
| POST | `/modules/{id}/rpc` | 调用模块方法 `{method, params}` |
| GET | `/modules/{id}/permissions` | 已授予/请求权限 |
| POST/DELETE | `/modules/{id}/permissions/{scope}` | 授权/撤销 |
| DELETE | `/modules/{id}?keepData=true` | 卸载 |
| GET | `/modules/audit` | 审计事件 |
| GET | `/modules/permission-catalog` | 全部 scope 与风险 |

### 环境变量（注入模块）

| 变量 | 含义 |
|---|---|
| `ECLIPSE_MODULE_ID` | 模块 ID |
| `ECLIPSE_RPC_TOKEN` | 本次进程 token（预留） |
| `ECLIPSE_API_VERSION` | 核心契约版本 |
| `ECLIPSE_PERMISSIONS` | 已授权 scope，逗号分隔 |
| `ECLIPSE_LOCALE` | 当前语言 |
| `ECLIPSE_MODULE_DIR` | 模块安装目录（视为只读） |

### 错误码（HTTP / RPC `error.data.code`）

`MODULE_CRASH`、`MODULE_TIMEOUT`、`PERMISSION_DENIED`、`INVALID_INPUT`、`INCOMPATIBLE_API`、`MODEL_LOAD_FAILED`、`RESOURCE_EXCEEDED`、`CANCELLED`、`MODULE_NOT_FOUND`、`MODULE_ALREADY_INSTALLED`、`MODULE_DISABLED`、`INVALID_PACKAGE`、`CHECKSUM_MISMATCH`、`UNSAFE_PACKAGE_PATH`、`MODULE_ERROR`、`METHOD_NOT_FOUND`、`NOT_IMPLEMENTED`。

### 路径

- 安装：`<dataDir>/modules/<id>/<version>/`
- 模块日志：`<dataDir>/logs/modules/<id>.log`
- 核心日志：`<dataDir>/logs/backend.log`
- 开发 dataDir：`backend/.data`；生产：`%LOCALAPPDATA%\eclipse-health`

---

## 11. FAQ

**Q：模块能直接读 SQLite/波形吗？**
不能。核心不把数据库路径交给模块；当前也没有 `records.*` 核心回调实现。需要核心先把数据通过 RPC 参数/临时文件传入。

**Q：模块能加一个导入格式，马上在导入页出现吗？**
不能。导入器是核心内置 registry；需要 §6.2 的 bridge。模块可以先通过 `/rpc` 暴露 `parse`，由外部脚本调用。

**Q：模块能替换 Cardia 做分析吗？**
可以写分析模块并通过 `/rpc` 调用；但要出现在「分析」按钮/引擎选择，需要 §6.1 的通用 loader。当前 Cardia 是写死的。

**Q：模块能用 numpy/onnxruntime 吗？**
当前模块用核心的 `sys.executable`，能 import 核心 venv 里的包；但契约目标是每模块独立 venv，未实现。不要依赖核心内部模块（`eclipse_health_backend.*`）。

**Q：模块能联网吗？**
技术上能（`PATH` 继承、无网络隔离）；`network` 权限目前只是声明/审计，不是强制。不要把它当安全边界。

**Q：模块能带自己的模型吗？**
可以放 `models/`，用 `checksums.json` 校验；但核心不会自动加载模型/展示模型卡，需要模块自己在 RPC 里加载。

**Q：`entry.factory` 会被调用吗？**
不会。核心直接执行 `entry.python`；`factory` 是预留元数据。

**Q：模块能加 UI 吗？**
目前不能自动渲染。声明式组件/沙箱 iframe 是目标设计，渲染器未实现。

**Q：怎么调试？**
看 `<dataDir>/logs/modules/<id>.log`、`GET /modules/{id}`、`GET /modules/audit`；用 `/rpc` 直接调方法；坏包先用 `preview-upload` 校验。

---

## 12. 参考

- 契约：`docs/MODULE_CONTRACT_V1.md`
- Schema：`schemas/module.schema.json`
- 最小示例：`modules/demo.echo/`（manifest、main.py、checksums、README）
- 真实示例：`modules/official/cardia/`（analysis-model、模型、worker、模型卡）
- 内核：`backend/src/eclipse_health_backend/modules/`
- 分析桥（当前写死 Cardia）：`backend/src/eclipse_health_backend/analysis_service/bridge.py`
- 导入 registry：`backend/src/eclipse_health_backend/importers/registry.py`
- 报告生成：`backend/src/eclipse_health_backend/reports/`
- LLM 工具：`backend/src/eclipse_health_backend/llm/tools.py`
- Agent 模板：`prompts/40-module-author-template.md`
