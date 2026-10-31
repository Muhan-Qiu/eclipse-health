# eclipse health · 模块契约 v2（贡献点）

> 2026-10-30 · 状态：草案（Stage A / A1）· 事实源：`schemas/module.schema.json`
> v2 只收紧 `contributes`；包格式 `.ehmod`、RPC、权限、生命周期、数据契约继续沿用 `MODULE_CONTRACT_V1.md`。

## 0. 范围

v1 把 `contributes` 当作「保留的任意 JSON」，核心只存不解释。v2 把它升级为**可校验、可查询、可被 UI/工具消费**的契约：

- manifest 校验阶段（安装、升级、回滚）就拒绝不符合形状的贡献；
- 运行期由贡献注册表聚合，通过 `GET /api/v1/modules/contributions` 对外提供；
- UI 只渲染受控组件；工具只能经模块 RPC 执行。

本版不新增包格式字段，不改变 v1 已有贡献点（`models`、`importFormats`、`pipelines`、`exporters`、`themes`、`locales`、`sources`）的形状。

## 1. 通用规则

1. **JSON Schema 是事实源**：文档与实现冲突时以 `schemas/module.schema.json` 为准。
2. **归属由核心注入**：模块只声明 `id`；注册表为每项补 `moduleId` / `moduleName` / `moduleVersion` / `moduleType`，模块无法伪造归属。
3. `id` 在模块内唯一，匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`，≤64 字符。
4. 文本字段有长度上限（见各表）；未知字段一律被拒绝（`additionalProperties: false`）。
5. **禁止**：任意 React/JSX、任意 CSS、内联脚本、`iframe`、模板表达式；数据绑定只允许受限路径。
6. 声明式 UI 不需要 `ui:custom`；数据访问不因 UI 声明而放宽，仍在模块 RPC 时按 `records:*` 校验。

## 2. `contributes.ui.widgets[]`

首页仪表盘组件。稳定形状：

```json
{
  "id": "weight-trend",
  "title": "体重趋势",
  "description": "",
  "size": "md",
  "dataSource": { "type": "module-rpc", "method": "stats", "params": { "days": 30 } },
  "view": { "type": "sparkline", "unit": "kg", "valuePath": "latest.weight" }
}
```

| 字段 | 必填 | 规则 |
|---|---|---|
| `id` | 是 | 模块内唯一，≤64 |
| `title` | 是 | 1～120 字符 |
| `description` | 否 | ≤300 字符 |
| `size` | 是 | `sm` / `md` / `lg` |
| `dataSource` | 是 | 见 2.1，只能绑定本模块 RPC |
| `view` | 是 | 见 2.2，只能使用受控组件 |
| `link` | 否 | 可选站内路径（见 2.3）；点击整张卡片跳转 |

### 2.1 `dataSource`

| 字段 | 必填 | 规则 |
|---|---|---|
| `type` | 是 | 固定 `module-rpc`（核心调用**声明它的模块自身**） |
| `method` | 是 | 模块 RPC 方法名，`[A-Za-z0-9_.:-]+`，≤128 |
| `params` | 否 | 对象，≤32 个键；核心原样透传给模块 |

核心不会把其他模块的地址交给它；跨模块数据需要走 `records:*` 或模块互调（v1 §5）。

### 2.2 `view`

| 字段 | 必填 | 规则 |
|---|---|---|
| `type` | 是 | `stat` / `sparkline` / `list` / `progress` / `text` |
| `valuePath` | 是 | 受限路径，从 RPC 结果取值，如 `latest.weight`、`series[0].value` |
| `unit` | 否 | ≤32，UCUM 推荐（`kg`、`bpm`、`ms`） |
| `label` | 否 | ≤120，覆盖数值前的说明文字 |
| `min` / `max` | 否 | 数值，仅 `progress` 使用 |

`valuePath` 只允许字母、数字、下划线、`.` 与 `[n]`；等价于受限 JSONPath，**不执行表达式**。

### 2.3 `link`

可选的站内跳转目标，只允许应用内路由：

- 必须以单个 `/` 开头（`^/`）；
- 禁止 `//`（协议相对地址）、`://`（外部协议）与任何 `..` 片段；
- 禁止空白与反斜杠，≤512 字符。

前端 `widget-card.tsx` 在渲染前会再次过滤，非法值按「无链接」处理；schema 校验失败会直接拒绝 manifest。

```json
"link": "/modules/io.github.example.weight-trend/pages/weight"
```

## 3. `contributes.ui.pages[]`

模块自有页面。稳定形状：

```json
{
  "id": "weight",
  "title": "体重",
  "icon": "scale",
  "layout": [
    { "component": "text", "text": "最近 30 天" },
    { "component": "table",
      "source": { "type": "module-rpc", "method": "list" },
      "rowPath": "items",
      "columns": [
        { "key": "capturedAt", "label": "时间", "format": "datetime" },
        { "key": "weight", "label": "体重", "unit": "kg", "format": "number" }
      ] }
  ]
}
```

| 字段 | 必填 | 规则 |
|---|---|---|
| `id` | 是 | 模块内唯一，≤64 |
| `title` | 是 | 1～120 字符 |
| `icon` | 否 | 图标名，`[a-z0-9-]+`，≤64 |
| `layout` | 是 | 1～64 个块，按顺序渲染 |

布局块只有五种，全部声明式、无脚本：

| `component` | 必填字段 | 可选字段 | 说明 |
|---|---|---|---|
| `text` | `text`（≤2000） | — | 静态说明文字 |
| `list` | `source` | `title`、`itemPath`、`primaryPath`、`secondaryPath` | 简单列表 |
| `table` | `source`、`columns` | `title`、`rowPath` | 表格；列含 `key`、`label`、可选 `unit`、可选 `format` |
| `detail` | `source` | `title`、`fields` | 键值详情，`fields` 同表格列（含可选 `format`） |
| `form` | `source`、`fields` | `title`、`submitMethod` | 表单；字段类型见下，另可选 `format` |

表单字段类型：`text` / `textarea` / `number` / `date` / `select` / `checkbox`；可选 `required`、`format`、`default`（字符串/数字/布尔）、`options`（`value` + `label`）。提交由核心收集后调用 `submitMethod`，模块不接触 DOM。

`format` 是显示提示，取值 `text` / `number` / `date` / `datetime`，由渲染器决定如何展示；它不改变数据本身，也不允许表达式。

## 4. `contributes.tools[]`

暴露给 LLM / Agent 的工具。稳定形状：

```json
{
  "id": "weight.summary",
  "name": "Summarize weight",
  "description": "Summarize the last N days of weight records.",
  "inputSchema": { "type": "object", "properties": { "days": { "type": "integer" } } },
  "outputSchema": { "type": "object" },
  "longRunning": false,
  "permissions": ["records:read"]
}
```

| 字段 | 必填 | 规则 |
|---|---|---|
| `id` | 是 | 模块内唯一，≤64 |
| `name` | 是 | 1～80 字符 |
| `description` | 是 | 1～500 字符，给模型看的用途说明 |
| `inputSchema` | 否 | JSON Schema 对象；`parameters` 是等价别名，**二选一** |
| `outputSchema` | 否 | JSON Schema 对象 |
| `longRunning` | 否 | 布尔；为真时核心允许 `cancel` |
| `permissions` | 否 | 工具额外需要的 scope，≤16 项；RPC 时仍逐项校验 |

- 工具**只能**通过模块 RPC 执行：核心把参数交给模块，模块返回结果。
- 模块必须声明并获授 `llm` 权限，工具才会出现在贡献注册表和工具目录中；撤销 `llm` 后立即消失。
- 同样，工具内声明的 `permissions` 不会因出现在目录里而自动授予。

## 5. `contributes.recordTypes[]`

沿用 v1 §7.4，不新增字段。v2 补充数据归属规则：

- 模块写入的记录由核心打上 `moduleId`；模块只能读写**自己创建的记录**或**自己声明 recordType 的记录**。
- 模块不得新建数据库表；需要索引的字段通过 `recordTypes[].indexes` 声明，由核心建索引。
- `payload` 按 `recordTypes[].schema` 校验；卸载时保留或删除由用户决定。
- `recordTypes` 仅在模块 `enabled` 时进入贡献注册表；未启用不影响已有记录的可读性（由核心 API 负责）。

## 6. 权限与可见性

| 贡献点 | 出现在注册表的条件 | 执行时校验 |
|---|---|---|
| `ui.widgets` | 模块 enabled | 数据经模块自身 RPC；核心按 `records:*` 校验 |
| `ui.pages` | 模块 enabled | 同上 |
| `tools` | 模块 enabled **且**已授予 `llm` | `llm` + 工具声明的 `permissions` + `records:*` |
| `recordTypes` | 模块 enabled | `records:*` |

声明式 UI 不需要 `ui:custom`；`ui:custom` 只覆盖沙箱 iframe（v1 §8）。注册表不判断 UI 是否「好看」，只保证形状受控。

## 7. 贡献注册表 API

```http
GET /api/v1/modules/contributions
GET /api/v1/modules/contributions?type=widgets|pages|tools|recordTypes
```

无 `type` 时返回四类分组：

```json
{
  "widgets": [ { "id": "weight-trend", "title": "体重趋势", "moduleId": "io.github.example.weight-trend", "moduleName": "Weight Trend", "moduleVersion": "0.1.0", "moduleType": "dashboard-widget" } ],
  "pages": [],
  "tools": [],
  "recordTypes": [],
  "counts": { "widgets": 1, "pages": 0, "tools": 0, "recordTypes": 0 }
}
```

带 `type` 时返回 `{ "type": "widgets", "items": [...] }`；未知 `type` 返回 `422 INVALID_INPUT`（`details.allowed` 列出合法值）。

语义保证：

- 只扫描已安装且 **enabled** 的模块；`tools` 额外要求已授予 `llm`；
- 不启动 worker、不调用 RPC、不读模块数据；
- 每项带 `moduleId` / `moduleName` / `moduleVersion` / `moduleType`；
- 工具输出统一为 `inputSchema`（若 manifest 用的是 `parameters`，注册表会归一化）。

## 8. 兼容性

- `schemaVersion` 仍为 `1.0`；v2 未改变 manifest 结构版本。
- 没有 `ui.widgets` / `ui.pages` / `tools` 的模块不受影响；Cardia 与 demo 模块继续通过校验。
- v1 时期 `ui.widgets` 是任意 JSON；v2 起改为受控结构。仓库内没有依赖旧形状的模块。
- 工具新增 `parameters` 别名与 `permissions` 字段，均为可选。
- `ui.widgets[]` 新增可选 `link`；页面列/字段新增可选 `format`。两者都是增量字段，旧 manifest 不受影响。

## 9. 完整示例 A · dashboard-widget

```json
{
  "schemaVersion": "1.0",
  "id": "io.github.example.weight-trend",
  "name": "Weight Trend",
  "description": "Dashboard widget showing the latest weight and a 30-day sparkline.",
  "version": "0.1.0",
  "apiVersion": "1.0",
  "engines": { "eclipse": ">=1.0 <2.0" },
  "type": "dashboard-widget",
  "author": { "name": "example", "url": "https://example.com" },
  "license": "MIT",
  "repository": "https://github.com/example/weight-trend",
  "permissions": ["records:read"],
  "entry": { "python": "src/widget.py", "factory": "create_module" },
  "contributes": {
    "ui": {
      "widgets": [
        {
          "id": "weight-trend",
          "title": "体重趋势",
          "description": "最近 30 天的体重与变化",
          "size": "md",
          "dataSource": { "type": "module-rpc", "method": "stats", "params": { "days": 30 } },
          "view": { "type": "sparkline", "unit": "kg", "valuePath": "latest.weight" },
          "link": "/modules/io.github.example.weight-trend/pages/weight"
        }
      ]
    }
  },
  "resources": { "memoryMb": 128, "cpu": 0.5, "startupTimeoutMs": 5000 },
  "updateChannel": "stable"
}
```

## 10. 完整示例 B · ai-tool

```json
{
  "schemaVersion": "1.0",
  "id": "io.github.example.hrv-explain",
  "name": "HRV Explain",
  "description": "Explain HRV trends in plain language using the configured LLM.",
  "version": "0.3.1",
  "apiVersion": "1.0",
  "engines": { "eclipse": ">=1.0 <2.0" },
  "type": "ai-tool",
  "author": { "name": "example", "url": "https://example.com" },
  "license": "MIT",
  "repository": "https://github.com/example/hrv-explain",
  "permissions": ["records:read", "llm"],
  "entry": { "python": "src/tool.py", "factory": "create_module" },
  "contributes": {
    "tools": [
      {
        "id": "hrv.explain",
        "name": "Explain HRV",
        "description": "Summarize the last 30 days of HRV measurements and explain possible factors.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "days": { "type": "integer", "minimum": 1, "maximum": 365, "default": 30 },
            "locale": { "type": "string", "default": "zh-CN" }
          },
          "additionalProperties": false
        },
        "outputSchema": { "type": "object", "properties": { "summary": { "type": "string" } } },
        "longRunning": false,
        "permissions": ["records:read"]
      }
    ]
  },
  "resources": { "memoryMb": 256, "cpu": 0.5, "startupTimeoutMs": 8000 },
  "updateChannel": "beta"
}
```

## 11. 未做（Stage B 及以后）

- 首页 widget 渲染器、模块页渲染器、工具注册表 UI（Stage B）。
- 模块 RPC 的 `widget` / `page` 数据通道实现（当前只聚合声明，不执行）。
- `ui.commands` / `ui.settings` 仍为保留字段，v2 不收紧。
