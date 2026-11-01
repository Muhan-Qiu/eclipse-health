# eclipse health · UI 组件与设计规范 v1（草案）

> 2026-10-28 · 状态：草案，待用户确认
> 前提：Q4 声明式组件 + 可拖拽网格 + 沙箱 iframe；Q10 官方 UI 也是模块；Q17 官方模块全部内置。
>
> **视觉方向更新（2026-10-28）**：配色转向莫奈低饱和、亮色主界面以白/暖白为主；本文件中的颜色令牌为初稿，待视觉定稿后统一替换。启动日食动画与 logo 方向见 `docs/IDEAS.md`。

## 0. 设计原则

1. **安静**：信息优先，装饰克制；不使用高饱和渐变、玻璃拟态堆叠、过量动效。
2. **临床可信**：数字、单位、时间、来源、置信度必须清楚；异常用颜色 + 图标 + 文字三重表达。
3. **典雅**：衬线标题 + 无衬线正文 + 等宽数字；暖纸白/近黑双主题。
4. **一致但有边界**：声明式组件强制使用核心令牌；自定义 React/CSS 只能运行在沙箱 iframe 或主题作用域内，不得注入主界面 DOM；默认体验由官方组件保证。
5. **可访问**：WCAG AA、键盘可操作、减少动效、色盲友好。

## 1. 设计令牌

模块只能使用语义令牌，不能写死颜色/字体。核心同时提供暗色与亮色。

### 1.1 颜色（暗色，默认）

| 令牌 | 值 | 用途 |
|---|---|---|
| `--eh-bg` | `#0A0C0F` | 应用背景 |
| `--eh-bg-subtle` | `#0E1216` | 次级背景 |
| `--eh-surface` | `#12171D` | 卡片 |
| `--eh-surface-raised` | `#171D24` | 浮层/弹窗 |
| `--eh-border` | `rgba(255,255,255,0.08)` | 分割线/描边 |
| `--eh-text` | `#F1F4F6` | 主文字 |
| `--eh-text-muted` | `#98A4B0` | 次级文字 |
| `--eh-accent` | `#D8A657` | 品牌/主操作（日蚀暖金） |
| `--eh-accent-contrast` | `#1A1206` | 主操作上的文字 |
| `--eh-signal` | `#6FE7D8` | 心电波形/数据主色 |
| `--eh-danger` | `#E06C75` | 危急值/错误 |
| `--eh-warning` | `#E5C07B` | 警告 |
| `--eh-success` | `#98C379` | 正常/完成 |
| `--eh-info` | `#7AA2F7` | 提示 |

### 1.2 颜色（亮色）

| 令牌 | 值 |
|---|---|
| `--eh-bg` | `#F7F5F1` |
| `--eh-bg-subtle` | `#EFEBE4` |
| `--eh-surface` | `#FFFFFF` |
| `--eh-surface-raised` | `#FFFFFF` |
| `--eh-border` | `rgba(20,24,28,0.10)` |
| `--eh-text` | `#171A1D` |
| `--eh-text-muted` | `#5E6974` |
| `--eh-accent` | `#9A6A1E` |
| `--eh-accent-contrast` | `#FFFFFF` |
| `--eh-signal` | `#0F7C72` |
| `--eh-danger` | `#B4363F` |
| `--eh-warning` | `#8A5A00` |
| `--eh-success` | `#2F7D32` |
| `--eh-info` | `#2C5AA0` |

> 两套主题都必须通过对比度校验；模块不得自行覆盖这些值。

### 1.3 字体

| 令牌 | 用途 | 字体 |
|---|---|---|
| `--eh-font-display` | 标题/品牌 | 思源宋体 / Noto Serif SC，600 |
| `--eh-font-body` | 正文/控件 | 思源黑体 / Noto Sans SC + Inter，400/500 |
| `--eh-font-mono` | 数字/代码 | Geist Mono / JetBrains Mono，tabular-nums |

| 层级 | 字号/行高 | 字重 |
|---|---|---|
| Display | 40/48 | 600 |
| H1 | 28/36 | 600 |
| H2 | 22/30 | 600 |
| H3 | 18/26 | 600 |
| Body | 15/24 | 400 |
| Small | 13/20 | 400 |
| Caption | 12/18 | 500 |
| Metric | 40/44 | 500，等宽数字 |

- 正文最大行宽 72ch；中文标题可略收紧字距（-0.01em）。
- 模块可自带 **WOFF2** 字体：单文件 ≤ 2MB，单模块 ≤ 4MB；必须在 manifest 声明并计入包体；推荐子集化。TTF/OTF 需转换为 WOFF2 后才允许。

### 1.4 间距、圆角、阴影、动效

- 间距：4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64。
- 圆角：`sm 8`、`md 12`、`lg 16`、`xl 24`。
- 阴影：暗色以描边为主、阴影极轻；亮色 `0 1px 2px rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.06)`。
- 动效：120ms（微交互）、200ms（卡片/页面）、320ms（大面积过渡）；ease-out；尊重 `prefers-reduced-motion`。

## 2. 布局与仪表盘

- 仪表盘 12 列网格，列间距 16px，行高 72px；页面最大宽度 1440px，外边距 32px。
- 组件尺寸用网格单位：`w 1–12`、`h 1–6`；每个组件声明 `defaultW/H`、`minW/H`、`maxW/H`。
- 响应式：≥1280 12 列；≥960 8 列；<960 4 列；小屏自动单列。
- 用户可拖拽、缩放、隐藏、重排；布局按成员保存，可导出/导入 JSON。
- 页面结构：左侧导航（可折叠）+ 顶部上下文栏 + 内容区；不堆叠多层侧栏。
- 首页空状态：导入/示例/了解支持格式三张引导卡；不使用空白页。

## 3. 声明式组件集（v1）

| 分类 | 组件 | 说明 |
|---|---|---|
| 布局 | `stack` | 纵向/横向排列、gap、align |
| 布局 | `grid` | 子项网格 |
| 布局 | `tabs` | 分组切换 |
| 布局 | `divider` | 分割线 |
| 数据 | `metric` | 大数字 + 单位 + 变化 + 迷你趋势 |
| 数据 | `sparkline` | 迷你折线 |
| 数据 | `lineChart` | 折线/面积，支持多序列 |
| 数据 | `barChart` | 柱状/分组柱状 |
| 数据 | `table` | 紧凑表格，支持排序 |
| 数据 | `list` | 记录/事件列表 |
| 数据 | `timeline` | 时间轴 |
| 数据 | `waveform` | ECG 波形（缩略/全宽），支持 R 峰与异常标记 |
| 数据 | `progressRing` | 环形进度/质量分 |
| 反馈 | `badge` | 状态标签 |
| 反馈 | `callout` | 提示/警告/危急值 |
| 反馈 | `button` | 主/次/危险操作 |
| 反馈 | `link` | 内外部链接（外部需确认） |

- 组件属性使用 JSON Schema 约束；核心负责渲染与主题。
- 不提供任意 HTML/CSS 注入；复杂交互走 iframe。
- 组件必须声明 `a11yLabel` 与空/错误状态文案。

## 4. 组件 Manifest

```json
{
  "ui": {
    "widgets": [
      {
        "id": "org.eclipsehealth.hrv-trend",
        "name": "HRV 趋势",
        "description": "最近 30 天 RMSSD 变化",
        "category": "heart",
        "dataSources": [
          { "id": "series", "type": "measurements", "code": "rmssd", "range": "30d" }
        ],
        "configSchema": {
          "type": "object",
          "properties": { "days": { "type": "integer", "default": 30, "minimum": 7, "maximum": 365 } }
        },
        "layout": { "defaultW": 4, "defaultH": 2, "minW": 2, "minH": 1, "maxW": 12, "maxH": 4 },
        "refresh": { "mode": "onRecordChange", "minIntervalSec": 30 },
        "render": {
          "type": "declarative",
          "schema": {
            "type": "lineChart",
            "title": "HRV · RMSSD",
            "x": { "bind": "$.series[].time" },
            "y": { "bind": "$.series[].value", "unit": "ms" },
            "empty": "还没有足够数据"
          }
        }
      }
    ]
  }
}
```

### 4.1 数据源

| 类型 | 参数 | 返回 |
|---|---|---|
| `records` | `recordType`、`tags`、`range`、`limit`、`sort` | 记录摘要数组 |
| `analyses` | `recordId` 或 `range`、`modelId` | 分析结果数组 |
| `measurements` | `code`、`range`、`aggregate` | 时间序列 |
| `moduleMethod` | `method`、`params` | 模块计算的自定义数据 |
| `static` | 内联 JSON | 固定数据 |

- `moduleMethod` 由核心调用模块 worker；组件只拿结果，不执行 Python。
- 数据必须可序列化；大数组走临时文件句柄，不塞组件 JSON。

### 4.2 数据绑定（受限）

```json
{ "bind": "$.series[].value", "transform": ["avg", "number:0"], "fallback": "—" }
```

允许的 transform（白名单，禁止 eval）：

`first`、`last`、`avg`、`sum`、`min`、`max`、`count`、`number:0`、`percent`、`duration`、`date`、`timeAgo`、`unit`。

## 5. 沙箱 iframe（自定义 UI / 任意 React）

- `render: { "type": "iframe", "entry": "ui/widget.html" }`。
- **任意 React 组件也在 iframe 中运行**：模块自带 React 运行时与打包产物，宿主只加载 `ui/widget.html`，绝不把第三方 React 注入主渲染进程。
- 沙箱：`allow-scripts`，**无** `allow-same-origin`。
- 默认 CSP `connect-src 'none'`；获得 `network` 权限后可直连（Q31），CSP 放宽为 `connect-src https:`，安装页必须显著警告。
- 只能加载包内资源；外部图片/字体/脚本默认禁止；需要时由宿主代理并受权限约束。
- 主题由宿主注入 CSS 变量；自定义 UI 可以使用任意 CSS（Q32），但只能作用于自身 iframe。
- 尺寸由网格决定；组件可请求高度调整。
- 网络直连时宿主无法逐请求审计，只能记录“已授予 network 权限”与声明的域名白名单；这是开放换来的可审计性损失。

### 5.1 postMessage 协议

宿主 → 组件：

```json
{ "type": "init", "widgetId": "...", "theme": "dark", "locale": "zh-CN", "size": { "w": 4, "h": 2 }, "config": {}, "tokens": { "--eh-signal": "#6FE7D8" } }
{ "type": "data", "sourceId": "series", "data": [] }
{ "type": "theme", "theme": "light", "tokens": {} }
{ "type": "resize", "w": 4, "h": 3 }
```

组件 → 宿主：

```json
{ "type": "ready" }
{ "type": "resize", "h": 180 }
{ "type": "action", "action": "openRecord", "payload": { "recordId": "rec_..." } }
{ "type": "requestData", "sourceId": "series", "params": {} }
```

- 每条消息带 `widgetId`；宿主校验 `event.source` 与 token。
- 组件不得直接访问 DOM 外部；需要网络时按 Q31 直连或经宿主代理，受 `network` 权限约束。
- 动作由宿主执行并二次校验权限。

## 6. 页面、导航与命令贡献

```json
{
  "ui": {
    "pages": [{ "id": "eeg-lab", "title": "脑电", "icon": "brain", "route": "/m/eeg", "render": { "type": "declarative", "schema": {} } }],
    "commands": [{ "id": "eeg.import", "title": "导入脑电", "action": "module.invoke", "params": { "method": "import" } }],
    "settings": [{ "id": "eeg.general", "title": "脑电设置", "schema": {} }]
  }
}
```

- 导航项顺序由用户可调；模块不能强制占据首屏。
- 命令面板自动收录模块命令；需声明 `keywords` 与 `icon`。
- 设置页按模块分组；危险操作必须二次确认。

## 7. 图表规范

- 调色顺序：`signal` → `info` → `warning` → `accent` → 紫/玫红；避免红绿同时作为唯一区分。
- 折线 1.5px；网格线极淡；不画上/右边框；Y 轴从 0 开始（除非医学指标有明确基线）。
- 时间轴本地时区；跨天显示日期；tooltip 同时显示时间、数值、单位、来源。
- ECG：信号线 `--eh-signal`；异常搏动 amber/red + 形状标记；质量差区段灰色斜纹遮罩。
- 禁止 3D、双 Y 轴、饼图（分类占比用横向条形）。
- 空状态、加载骨架、错误状态由核心统一提供。

## 8. 可访问性

- 对比度：正文 ≥ 4.5:1，大字号 ≥ 3:1；两套主题均校验。
- 焦点环：2px `--eh-accent`，不使用 `outline: none`。
- 全部功能可键盘完成；网格拖拽提供键盘替代（上下移动/调整大小）。
- 图表提供文字摘要与数据表视图。
- 颜色不单独承载信息：异常同时用图标/文字/形状。
- 尊重减少动效；不使用自动播放动画。

## 9. 主题模块

- 主题模块可提供**完整 CSS**（Q32），但只能作用于 `[data-eh-theme-scope]` 根节点，不得修改主界面结构。
- 官方主题仍为默认：`eclipse-dark`、`eclipse-light`、`eclipse-paper`（暖纸）。
- 自定义主题在安装页标注 `custom theme`，提供实时预览与一键重置；主题异常时可回退官方主题。
- 主题模块可声明令牌值（颜色/字体族/圆角/密度）与附加 CSS；核心做基本语法与作用域校验，无法保证美感。
- 用户可导入/导出主题 JSON；第三方主题走同一安装与权限提示。

## 10. 设计校验与视觉回归

- `ehmod ui lint`：组件白名单、令牌使用、对比度、尺寸约束、外部资源、字体体积（单文件 ≤2MB、单模块 ≤4MB）、包体大小。
- 官方组件维护视觉回归快照（暗/亮、空/加载/错误）。
- 新组件需提供：用途、数据源、空状态、错误状态、可访问性说明、截图。
- 社区组件不强制视觉回归，但安装页展示截图与风险等级。

## 11. 决策记录

已定（2026-10-28）：

- Q29 网格：**12 列固定网格**，行高 72px，响应式 12/8/4 列。
- Q30 组件集：**允许任意 React**，但只能运行在沙箱 iframe，不注入主界面。
- Q31 网络：**允许 iframe 直接联网**，需 `network` 权限 + 安装警告；CSP `connect-src https:`。
- Q32 主题：**允许完整 CSS**，但作用于主题作用域；官方主题仍为默认，自定义主题标注并提供预览/重置。
- Q33 字体：**允许自带 WOFF2**，单文件 ≤2MB、单模块 ≤4MB，需声明与计入包体。
- Q34 布局：**支持导出/导入 JSON**，模块缺失时提示安装或跳过。
- Q35 自定义 UI：**仅标注 `custom UI`**；权限、联网与扫描风险仍在安装页按通用规则展示。
- Q36 主题安全：**强制预览 + 一键重置/回退官方主题**。
