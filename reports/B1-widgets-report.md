# 报告 · B1-widgets 首页 widget 渲染器（受控组件）
状态：完成

## 交付
- `src/features/modules/types.ts`：新增 `ModuleWidget` / `ModuleWidgetView` / `ModuleWidgetDataSource` / `ModuleContributionGroups` 等类型，与 `MODULE_CONTRACT_V2.md §2` 对齐。
- `src/features/modules/api.ts`：`listContributions()`（无参分组、`type` 单组两个重载）走 `GET /modules/contributions`；`callModuleRpc(moduleId, method, params)` 走 `POST /modules/{id}/rpc` 并返回 `result`；新增 `MODULE_CONTRIBUTIONS_KEY`；RPC 超时 60s（首次调用可能冷启动 worker）。
- `src/features/modules/widgets/value-path.ts`：受限路径读取器。
- `src/features/modules/widgets/widget-view.tsx`：五种受控视图 + 未知类型降级。
- `src/features/modules/widgets/widget-card.tsx`：单卡片（标题、模块来源、刷新、逐卡错误/重试、可选站内跳转）。
- `src/features/modules/widgets/widget-grid.tsx`：拉取 contributions，按 `size` 排 12/8/1 列网格，loading/error/empty。
- `src/pages/dashboard.tsx`：引导卡片与主网格之间插入 `<WidgetGrid />`；无 widgets 时整个区块（含标题）返回 `null`。
- `src/features/modules/i18n.ts`：新增 `moduleUi.widgets.*`（zh-CN / en-US）。
- 不使用 iframe / 任意 React/CSS；颜色间距全走现有令牌与 `Card`/`Progress`/`Sparkline`；未新增依赖。

支持的 view 字段（全部只读 `view` 与 RPC 结果，不接受样式/HTML）：

| type | 读取 | 渲染 |
|---|---|---|
| `stat` | `valuePath` → number/string | `eh-num` 大号数值 + `unit`；`label` 作上方说明 |
| `sparkline` | number[] 或 `[{value}]` | 复用 `Sparkline`，`aria-label` 用 `title` |
| `list` | array | 最多 5 行，条目取 `label/name/title/text/key` 与 `value/amount/count`，超出显示「还有 N 项」 |
| `progress` | number | `min`/`max`（默认 0/100）归一化后交给 `Progress`，同时显式写 `aria-valuenow` |
| `text` | string/number/boolean | 纯文本（`whitespace-pre-line`），不解析 HTML |
| 其他 | — | 「不支持的卡片类型（{{type}}）」，不崩溃、不请求额外资源 |

valuePath 安全规则（`value-path.ts`，与 schema `valuePath` 同一条正则）：
- 只接受 `^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+|\[\d+\])*$`，长度 ≤128；不合法直接返回 `undefined`。
- 手写分词 + 逐段读取，不使用 `eval`/`Function`/`new RegExp(路径)`；数组索引仅接受非负整数。
- 只读自有属性（`hasOwnProperty`），显式拒绝 `__proto__` / `constructor` / `prototype`，数组不接受字符串键。
- 实测：`latest.weight→72.5`、`series[1].value→20`、`__proto__.x`/`constructor.name`/`a..b`/`alert(1)`/`latest[0]` 全为 `undefined`。

失败隔离：
- contributions 查询失败 → 只显示一块「无法加载模块卡片 + 重试」，仪表盘其余内容照常；RPC 失败 → 仅该卡片进入错误态（`retry: 0`，不拖慢仪表盘），另有按钮重试。
- 未知 view type / `valuePath` 取不到值 → 卡片内降级文案，不抛异常；模块返回的 HTML 永远按文本渲染。
- 模块 disabled/卸载：`MODULE_QUERY_KEY = ["modules"]` 是 contributions 键的前缀，模块页现有 `invalidateQueries` 会连带重拉，卡片随之消失。
- `VITE_USE_MOCK=true` 时直接返回 `null`（模块 API 没有 mock 通道，避免演示模式出现错误块）。

## 验证
- 命令：`npm run build`（tsc + vite）→ 通过，`✓ 2845 modules transformed`，`✓ built in 5.48s`，仅既有的 >500 kB chunk 警告。
- headless Chrome + CDP（`Fetch` 域拦截 `/modules/contributions` 与 `/modules/{id}/rpc`，后端未启动），结果全部为 true：
  - 7 张卡片按顺序渲染，`stat`=72 bpm、`sparkline` polyline、`list` 含「深睡/1h 42m」与「还有 1 项」、`progress` `aria-valuenow=64`、`text` 两行、模块来源 `Vitals` 可见；
  - 未知类型 `gauge` 显示「不支持的卡片类型（gauge）」；
  - `method=fail` 的 RPC 返回 500 时，只有该卡显示「卡片数据加载失败」，其余卡片数值仍在；
  - 带 `link:"/modules"` 的卡片点击后 `location.hash === "#/modules"`；
  - 0 widgets 时区块、标题、骨架全部不存在，仪表盘其余内容正常；
  - 亮/暗两轮合计 `console.error` / `pageerror` = 0。
- 截图（1440 宽，`reports/screenshots/`）：`B1-widgets-light.png`、`B1-widgets-dark.png`。
- 边界：`value-path.ts` 用 `node --experimental-strip-types` 直跑 11 组用例（见上），原型链与非法语法均返回 `undefined`。

## 未做 / 偏离
- `link` 不在 `MODULE_CONTRACT_V2.md §2` 的 `ui.widgets` 字段表里，`module.schema.json` 的 widget 也是 `additionalProperties: false`：通过后端校验的模块不会带 `link`。按任务要求仍做了容错（仅接受 `/` 开头的站内路径，`//host` 忽略），当前只能由库被外部改写时触发。
- `sparkline` 未画坐标轴/时间轴（复用现有 `Sparkline`，任务要求不引图表库）；`list` 固定最多 5 行。
- 没有新增单元测试框架（仓库未装 vitest），路径解析用一次性 node 脚本验证。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `src/components/ui/progress.tsx` 把 `value` 解构后只用于位移，没有传给 Radix Root，导致 `aria-valuenow` 缺失；本批在 widget 调用处显式补了 `aria-valuenow`，建议 UI 组件负责人修复根因（影响所有进度条）。
- 后端 `collect_contributions` 只做归属包装，不校验 widget 形状；真正的形状校验依赖 manifest 的 `module.schema.json`（现有实现确实在 `manifest.py` 校验）。若将来放宽 schema，前端已有降级兜底。

## 需要指挥官决策
- 是否把 `link` 正式写进 v2 契约与 schema（模块自定义落地页需要它；当前 schema 会直接拒绝带 `link` 的 manifest）。

## 建议下一批
- 72-module-pages 可复用本批的 `valuePath` 与「未知类型降级」思路；模块页的 `link` 目标路由需与 72 一起定。
