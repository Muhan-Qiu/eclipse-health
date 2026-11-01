# eclipse health · 模块契约 v1（草案）

> 2026-10-28 · 状态：草案，待用户确认
> 目标：一套契约同时服务官方与第三方模块；核心只做容器、契约、数据与权限；模块可安装、可替换、可审计。

## 0. 设计约束

- 模块运行在**独立 Python 进程**，独立 venv，由核心自动管理。
- 模块**不得直接访问数据库、文件系统、网络**；所有能力经核心 RPC 代理。
- 边界使用 **JSON-RPC 2.0**；大数组不塞 JSON，使用受控文件句柄。
- UI 贡献优先**声明式 JSON**；自定义 UI 只能跑沙箱 iframe。
- 本地模型仅 **ONNX / safetensors**；远程模型必须声明 `network`。
- 核心 API 严格语义化版本；模块声明兼容范围。

## 1. 包格式 `.ehmod`

ZIP 包，解压到 `%LOCALAPPDATA%/eclipse-health/modules/<id>/<version>/`：

```text
module.json            # manifest（必需）
pyproject.toml         # Python 依赖（可选）
src/                   # 代码（必需）
ui/                    # 声明式 UI 贡献（可选）
models/                # 本地权重（可选，或只放下载描述）
README.md
LICENSE
checksums.json         # 每个文件的 sha256
signature.json         # 第一方/已签名模块
```

安装流程：校验 manifest → 校验 checksums/签名 → 解析依赖 → 创建 venv（uv）→ 安装依赖 → 注册 → 可选启用。

## 2. Manifest `module.json`

```json
{
  "schemaVersion": "1.0",
  "id": "org.eclipsehealth.samsung",
  "name": "Samsung Health ECG",
  "description": "Import Samsung Health ECG exports",
  "version": "1.0.0",
  "apiVersion": "1.0",
  "engines": { "eclipse": ">=1.0 <2.0" },
  "type": "device-adapter",
  "author": { "name": "eclipse health", "url": "https://..." },
  "license": "GPL-3.0-only",
  "homepage": "https://...",
  "repository": "https://...",
  "permissions": ["files:user-selected", "records:write"],
  "entry": { "python": "src/adapter.py", "factory": "create_module" },
  "contributes": {
    "importFormats": [
      { "id": "samsung.csv", "ext": ["csv"], "label": "Samsung Health CSV" }
    ]
  },
  "resources": { "memoryMb": 512, "cpu": 1, "startupTimeoutMs": 10000 },
  "updateChannel": "stable",
  "i18n": { "zh-CN": "ui/zh-CN.json", "en-US": "ui/en-US.json" }
}
```

字段规则：

| 字段 | 必填 | 规则 |
|---|---|---|
| `id` | 是 | 反向域名，全局唯一，安装后不可变 |
| `version` | 是 | SemVer |
| `apiVersion` | 是 | 模块使用的契约版本 |
| `engines.eclipse` | 是 | 兼容的核心版本范围 |
| `type` | 是 | 见模块类型表 |
| `permissions` | 是 | 最小权限集合，安装时逐项确认 |
| `entry` | 是 | Python 入口与工厂函数 |
| `contributes` | 否 | 按类型声明的贡献点 |
| `resources` | 否 | 资源上限，核心强制执行 |
| `signature` | 否 | 分离文件 `signature.json` |

## 3. 模块类型与贡献点

| `type` | 贡献点 | 说明 |
|---|---|---|
| `device-adapter` | `importFormats` | 识别并解析设备/医院导出 |
| `signal-engine` | `pipelines` | 预处理、质量、R 峰、特征 |
| `analysis-model` | `models` | 模型、预处理契约、模型卡 |
| `health-domain` | `recordTypes`, `ui.pages` | 新健康领域 |
| `dashboard-widget` | `ui.widgets` | 首页组件 |
| `exporter` | `exporters` | PDF/PNG/CSV/FHIR |
| `ai-tool` | `tools` | 暴露给 LLM/Agent 的工具 |
| `theme` | `themes` | 主题/字体 |
| `locale` | `locales` | 语言包 |
| `data-source` | `sources` | 实时数据流（未来） |

## 4. 生命周期

```text
discover → verify → resolve → install → enable → start → initialize → operate
                                                         ↓
                                              crash/disable/update/uninstall
```

- **start**：核心按需启动 worker（默认懒启动），注入 `ECLIPSE_MODULE_ID`、`ECLIPSE_RPC_TOKEN`、`ECLIPSE_API_VERSION`。
- **initialize**：模块返回能力、配置 schema、健康状态；核心返回权限、locale、数据源。
- **operate**：核心调用模块方法；模块可回调核心 RPC，也可发事件。
- **update**：下载新版本 → 校验 → 安装到新目录 → 原子切换 → 失败回滚。
- **uninstall**：停止 worker → 注销 → 用户选择保留或删除模块数据。

## 5. RPC 协议

JSON-RPC 2.0，stdin/stdout 按行分隔（每条消息一行 JSON）。大数组使用文件句柄。

核心 → 模块：

| 方法 | 说明 |
|---|---|
| `initialize` | 握手：apiVersion、权限、locale、config |
| `activate` / `deactivate` | 启用/停用 |
| `invoke` | 通用调用：`{ method, params }`，由模块类型定义 |
| `cancel` | 取消长任务 |
| `health` | 存活/资源检查 |
| `configure` | 更新配置 |

模块 → 核心（受限 RPC）：

| 方法 | 说明 |
|---|---|
| `records.query` / `records.get` | 查询/读取记录（需 `records:read`） |
| `records.create` / `records.update` | 写入（需 `records:write`） |
| `signals.read` | 读取波形切片，返回文件句柄 |
| `files.pick` / `files.export` | 用户选择的文件读写 |
| `models.download` / `models.load` | 模型下载与加载 |
| `llm.complete` | 调用已配置 LLM（需 `llm`） |
| `events.emit` | 发送进度/状态事件 |
| `log.write` / `audit.write` | 日志与审计 |

事件（notification）：

- `analysis.progress` `{ jobId, step, percent, message }`
- `log` `{ level, message }`
- `ui.invalidate` `{ widgetId }`
- `record.created` / `analysis.completed`（核心广播）

超时：默认 30s；分析类任务可声明 `longRunning` 并支持 `cancel`。崩溃：指数退避重启，连续 3 次失败自动禁用并提示。

模块互调：允许模块声明依赖并**直接 RPC 互调**，但 peer 地址与 scoped token 由核心发放，调用仍受权限与审计约束；禁止直接 import 其他模块的 Python 代码。

## 6. 权限

| 权限 | 含义 |
|---|---|
| `records:read` | 读取记录、测量、分析结果 |
| `records:write` | 新建/更新记录 |
| `records:delete` | 删除记录（高风险，默认不授予） |
| `files:user-selected` | 读取用户主动选择的文件 |
| `files:export` | 写入用户确认的导出目录 |
| `network` | 访问网络，必须同时声明 `allowedHosts` |
| `llm` | 调用用户配置的 LLM |
| `models:download` | 下载模型权重 |
| `ui:custom` | 使用沙箱 iframe 自定义 UI |
| `system:notify` | 系统通知 |
| `system:background` | 最小化后继续运行 |

规则：默认拒绝；**安装/升级时逐项展示并授权**；升级新增权限必须重新确认；用户可随时撤销；所有使用写审计日志。运行期不再逐次弹窗。

## 7. 数据契约

核心表：`members`、`records`、`signals`、`analyses`、`measurements`、`annotations`、`reports`、`modules`、`audit_log`。

### 7.1 HealthRecord

```json
{
  "id": "rec_...",
  "memberId": "mem_default",
  "moduleId": "org.eclipsehealth.samsung",
  "recordType": "ecg",
  "capturedAt": "2026-10-28T10:00:00+08:00",
  "source": { "kind": "wearable", "device": "Galaxy Watch", "app": "Samsung Health" },
  "samplingRate": 500.0,
  "leads": ["Lead I"],
  "durationSec": 30.0,
  "unit": "mV",
  "signalRef": "sig_...",
  "tags": ["晨起"],
  "notes": "心悸",
  "metadata": {},
  "createdAt": "..."
}
```

### 7.2 Signal

波形存二进制（float32，按导联分块），JSON 只放引用：

```json
{ "id": "sig_...", "recordId": "rec_...", "fs": 500.0, "leads": ["Lead I"], "dtype": "float32", "shape": [15000], "unit": "mV" }
```

模块通过 `signals.read` 获取切片文件句柄，不直接读库。

### 7.3 AnalysisResult

```json
{
  "id": "ana_...",
  "recordId": "rec_...",
  "moduleId": "org.eclipsehealth.cardia",
  "modelId": "cardia-2.0",
  "engineVersion": "2.0.0",
  "status": "completed",
  "summary": "N 96.2% · SVEB 1.1% · VEB 2.4% · F 0.3%",
  "quality": { "score": 0.93, "warnings": [] },
  "measurements": [
    { "code": "heart_rate_mean", "value": 68.0, "unit": "bpm", "confidence": 0.98 }
  ],
  "beats": [
    { "index": 0, "sample": 120, "label": "N", "confidence": 0.99 }
  ],
  "warnings": [],
  "createdAt": "..."
}
```

### 7.4 模块自定义数据

- `records` 表含 `payload_json`，按模块 manifest 中 `recordTypes[].schema` 校验。
- 模块不得新增数据库表；需要索引的字段通过 `recordTypes[].indexes` 声明，由核心建索引。
- 卸载时可选择保留 payload（孤立数据）或彻底删除。

### 7.5 数据契约定义方式（待决策）

- A. JSON Schema 为唯一事实源，生成 Python/TypeScript 类型（推荐）。
- B. Pydantic 模型为事实源，导出 JSON Schema。
- C. Protobuf。

## 8. UI 贡献（声明式）

```json
{
  "ui": {
    "widgets": [{
      "id": "hrv-trend",
      "name": "HRV 趋势",
      "description": "最近 30 天 RMSSD",
      "dataSources": [{ "recordType": "ecg", "query": "last30d" }],
      "layout": { "defaultW": 2, "defaultH": 1, "minW": 1, "minH": 1 },
      "configSchema": { "type": "object", "properties": { "days": { "type": "integer", "default": 30 } } },
      "render": {
        "type": "declarative",
        "schema": {
          "type": "chart",
          "chart": "line",
          "x": "$.records[].capturedAt",
          "y": "$.records[].measurements[rmssd]"
        }
      }
    }],
    "pages": [],
    "commands": [],
    "settings": []
  }
}
```

- 声明式组件集（v1）：`metric`、`text`、`sparkline`、`lineChart`、`barChart`、`table`、`list`、`badge`、`button`、`stack`、`grid`、`tabs`、`divider`。
- 数据绑定只允许受限 JSONPath，不允许执行任意表达式。
- 自定义 UI：`render.type = "iframe"`，`entry: "ui/widget.html"`，沙箱 `allow-scripts`、无 same-origin；通过 postMessage 收数据、发动作；网络默认阻断。
- 设计令牌由核心提供，模块只能用主题变量。
- 报告模板同理：声明式优先，复杂模板用 iframe 沙箱。

## 9. 模型贡献

```json
{
  "models": [{
    "id": "cardia-2.0",
    "name": "Cardia 2.0",
    "task": "beat-classification",
    "format": "onnx",
    "files": [{ "path": "models/cardia.onnx", "sha256": "..." }],
    "input": { "leads": ["MLII"], "fs": 360, "windowSamples": 180, "features": "cardia-104d" },
    "output": { "classes": ["N", "SVEB", "VEB", "F"] },
    "preprocess": { "pipeline": "cardia-v2", "version": "2.0" },
    "runtime": { "device": "cpu", "memoryMb": 512 },
    "modelCard": {
      "trainingData": "MIT-BIH Arrhythmia",
      "metrics": { "composite": 74.0 },
      "limitations": ["MLII only", "360 Hz only"],
      "license": "GPL-3.0-only",
      "nonDiagnostic": true
    }
  }]
}
```

- 本地格式：ONNX / safetensors。
- 远程模型：`format: "remote"`，`endpoint`，`authRef`，必须 `network` 权限 + `allowedHosts`。
- 模型选择：用户按任务选择；可设置回退链；结果标注模型版本。
- 预处理契约必须声明并版本化，避免“换了模型但预处理没换”。

## 10. 版本与兼容

- `schemaVersion`：manifest 结构版本，核心支持当前 + 前一个。
- `apiVersion`：模块契约版本；核心至少兼容 2 个 minor。
- `engines.eclipse`：模块可运行的核心版本范围。
- 弃用：至少提前 2 个 minor 标记，控制台与开发文档提示。
- 模块数据迁移：模块提供 `migrations[]`，核心在事务内执行，命名空间隔离。

## 11. 安全与审计

- worker 环境变量清洗；工作目录隔离；只暴露 RPC。
- 网络：默认阻断；`network` 权限 + 域名白名单；所有请求记审计。
- 数据库：模块无直接连接；核心按权限返回最小切片。
- 模型：拒绝 pickle；ONNX/safetensors 校验哈希；远程模型标注数据出境。
- 扫描：manifest 校验、依赖漏洞、权限变更、可疑行为、签名/哈希。
- 审计事件：`module.install`、`module.enable`、`records.read`、`records.write`、`network.request`、`model.load`、`export.write`。
- 崩溃隔离与自动禁用；资源上限（内存/CPU/启动超时/单次调用超时）。

## 12. 错误码

| 码 | 含义 |
|---|---|
| `MODULE_CRASH` | worker 崩溃 |
| `MODULE_TIMEOUT` | 调用超时 |
| `PERMISSION_DENIED` | 权限不足 |
| `INVALID_INPUT` | 输入不符合 schema |
| `INCOMPATIBLE_API` | 契约版本不兼容 |
| `MODEL_LOAD_FAILED` | 模型加载/校验失败 |
| `RESOURCE_EXCEEDED` | 超出资源上限 |
| `CANCELLED` | 用户取消 |

## 13. 最小示例（仅示意）

Samsung adapter：

```python
from eclipse_sdk import Module, ModuleContext

class SamsungAdapter(Module):
    def activate(self, ctx: ModuleContext) -> None:
        self.ctx = ctx

    def invoke(self, method: str, params: dict):
        if method == "import.detect":
            return {"handled": params["filename"].endswith(".csv")}
        if method == "import.parse":
            return self.parse(params["fileHandle"])
        raise NotImplementedError(method)
```

Widget 只需 manifest 中的声明式 JSON，不需要 Python UI 代码。

## 14. 决策记录

已定（2026-10-28）：

- Q13 RPC 传输：**stdio JSON-RPC 2.0**，大数组走临时文件句柄。
- Q14 数据契约：**JSON Schema 为唯一事实源**，自动生成 Python/TypeScript 类型。
- Q15 worker 生命周期：**懒启动常驻**，长时间空闲可回收。
- Q16 大信号传输：**临时文件句柄**。
- Q17 官方模块：**全部随安装包内置**（Cardia、Samsung/Apple/华为/SCP-ECG、官方 UI）。
- Q18 权限提示：**仅安装/升级时授权**；升级新增权限必须重新确认。
- Q19 API 稳定性：**严格 semver + 至少 2 个 minor 弃用周期**。
- Q20 模块互调：**允许直接互调**，但 peer 与 scoped token 由核心发放，禁止共享 Python 代码。
