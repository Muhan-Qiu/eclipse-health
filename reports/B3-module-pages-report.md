# 报告 · B3 模块页渲染器（声明式页面）

状态：完成

## 交付

- `src/App.tsx`：新增 lazy 路由 `/modules/:moduleId/pages/:pageId`。
- `src/pages/module-page.tsx`：读取 `GET /modules/contributions?type=pages`，按 moduleId + pageId 定位页面；加载/错误/卸载/禁用/页面不存在均有空状态与「返回模块」。
- `src/features/modules/pages/page-api.ts`：贡献点拉取、RPC 调用、受限路径查询键；兼容 `dataSource`/`itemsPath`/`rowsPath`/`submit.method` 别名。
- `src/features/modules/pages/page-layout.tsx`：12 列网格与受控块渲染，未知组件降级为「不支持的块」，RPC 失败显示错误卡片不白屏。
- `src/features/modules/pages/page-form.tsx`：受控表单、必填/数字校验、RPC 提交、成功后刷新数据源。
- `src/features/modules/pages/page-value.ts`：受限点路径读取与数值/日期/单位格式化（复用 `src/lib/format.ts`）。
- `src/features/modules/pages/i18n.ts`：feature-local `modulePage.*`（zh-CN/en-US）。
- `src/features/modules/module-detail.tsx`：manifest 下方新增「模块页面」区域，逐页「打开页面」；无页面不渲染。

## 支持的块与字段

| 块 | 字段 |
|---|---|
| `text` | `text`（保留换行，纯文本） |
| `list` | `source`、`itemPath`、`primaryPath`、`secondaryPath`、`title`；省略 `itemPath` 时直接使用数组结果 |
| `table` | `source`、`rowPath`、`columns[{key,label,unit,format?}]`；`format` 支持 `text/number/date/datetime` |
| `detail` | `source`、`fields[{key,label,unit,format?}]`；未声明 `fields` 时自动列出顶层标量 |
| `form` | `source`、`fields[{key,label,type,required,default,options}]`、`submitMethod`；类型 `text/textarea/number/date/select/checkbox` |

- 数据源统一为 `{type:"module-rpc", method, params?}`；同时接受 `dataSource` 别名。
- 网格：`text`/`table` 占 12 列，`list`/`detail`/`form` 占 6 列（移动端单列）。
- 每个数据块有独立刷新按钮；页面级刷新会失效该模块全部页面 RPC。

## submit 协议

- `POST /api/v1/modules/{moduleId}/rpc`，请求体 `{method: submitMethod, params: {...}}`。
- `params` 为扁平字段：文本/日期/下拉取字符串，数字转 number（空值发 `null`），checkbox 发布尔。
- 成功后 toast「已提交」，`dirty` 复位，并失效 `["modules","page-rpc",moduleId]`，所有数据源重新拉取。
- 未声明 `submitMethod` 时按钮禁用并提示，不发送请求。

## 安全限制

- 仅渲染 React 文本与既有 shadcn 组件；无 `dangerouslySetInnerHTML`、无 iframe/脚本/任意 CSS。
- `valuePath` 只接受 `a.b[0].c` 形式的点路径/数组索引，拒绝表达式与 `__proto__`/`constructor`/`prototype`。
- 所有数据读写只走声明它的模块自身 RPC；未新增依赖，未改共享 API/i18n 文件。

## 验证

- 命令：`npm run build`
- 结果：pass（tsc + vite，约 3.2s；仅既有 500kB chunk 警告）。
- Playwright（Chrome headless，生产构建 + 本地 mock API）：**24/24 通过**。
  - text/list/table/detail/form 全部渲染；日期、单位、数字格式化正确。
  - 表单初值由 source 回填；提交后 capture 到 `save`，参数为 `{weight:70.2,note:"测试提交",date:"2026-10-30",mood:"bad",public:true}`，随后 summary/detail/loadForm 重新请求。
  - 未知块显示「不支持的块」；故障 RPC 显示「数据加载失败」且页面其余块正常。
  - `dataSource/itemsPath` 别名页正常；禁用模块显示「模块未启用」+ 返回链接；模块详情 3 个「打开页面」链接可直接跳转。
- 截图：`reports/screenshots/B3-page-light.png`、`B3-page-dark.png`（干净页面，控制台 0 error）。
- 故障页会因故意 500 产生一条浏览器 resource error，属预期。

## 未做 / 偏离

- 未做 widget 渲染器、工具注册表、S2 导入、LLM provider；未 commit。
- 契约以 `schemas/module.schema.json` 为准（`source`/`rowPath`/`submitMethod`/`unit`）；提示词中的别名在渲染层兼容，但 manifest 校验仍按 schema。
- form 字段 key 若含点号，提交时按原样作为扁平键，不做嵌套展开。

## 跨区需求

- `module-detail.tsx` 的页面链接依赖 contributions API；模块启用/禁用后由 `staleTime:0` 重新拉取，无需改 `modules-workspace.tsx`。
- 并行 Agent 的 `src/features/modules/{api,types,i18n}.ts` 变更已被本任务只读复用；构建通过。

## 需要指挥官决策

- 是否允许 form 的 `submitMethod` 省略时回退到 `source.method`（当前禁用提交）。
- `format` 目前不在 JSON Schema 中（仅渲染层兼容）；若要模块真正可用，需要 v2 schema 增加该字段。

## 建议下一批

- 将 `format` 正式写入 page column schema；为页面渲染器补独立单测（路径解析/格式化）。
- 模块详情打开页面后可保留返回时自动展开该模块详情（当前回到模块列表）。
