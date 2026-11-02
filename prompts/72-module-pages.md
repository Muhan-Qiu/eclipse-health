# B3 · 平台 #4 UI：模块页渲染器（声明式页面）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md` 的 `ui.pages` 段，再读本文件。

## 目标

让已安装模块声明的 `contributes.ui.pages` 在应用内打开：按 `layout` 受控块渲染表单/表格/详情/列表/文本，数据通过模块 RPC 读写。第三方只交 JSON，不执行任意 React/CSS/iframe。

## 交付

### 1. 路由与入口

- `src/App.tsx` 增加路由 `/modules/:moduleId/pages/:pageId`（lazy）。
- 新建 `src/pages/module-page.tsx`：读取 contributions，找到对应 page；模块 disabled/卸载/页面不存在 → 友好空状态 + 返回模块页。
- `src/features/modules/module-detail.tsx`：在贡献点区域为每个 `ui.pages` 增加「打开页面」链接；无页面不显示。

### 2. 渲染器

- 新建 `src/features/modules/pages/`：
  - `page-api.ts`：本地 fetch `GET /modules/contributions?type=pages` 与 `POST /modules/{id}/rpc`（不要改 `modules/api.ts`，B1 所有权）。
  - `page-layout.tsx`：按 12 列网格渲染块；未知 component 显示「不支持的块」。
  - 受控块：
    - `text`：标题/段落；
    - `list`：`itemsPath` 读取数组，显示主/次字段；
    - `table`：`columns[{key,label,format?}]` + `rowsPath`；
    - `detail`：`fields[{key,label,format?}]` + `valuePath`；
    - `form`：`fields[{key,label,type:text|number|date|select,options?}]`，提交调用 `submit.method`，参数为表单值；成功后重新拉取 dataSource。
  - 所有数据来自 `dataSource: {type:"module-rpc", method, params}`；刷新按钮/加载/错误状态。
- 安全：纯文本渲染，不注入 HTML；`valuePath` 只支持点路径与数组索引；数值/日期格式化走现有工具。
- 文案放 `src/features/modules/pages/i18n.ts`（feature-local，zh-CN/en-US）。

### 3. 测试

- `npm run build` 通过。
- Playwright/CDP 拦截 contributions + rpc，验证：
  - text/list/table/detail/form 各渲染；
  - 表单提交带正确 method/参数并刷新；
  - 未知块降级、RPC 失败不白屏；
  - 模块 disabled 时页面显示空状态。
- 亮/暗截图 `reports/screenshots/B3-page-*.png`，控制台 0 error。

## 文件所有权（只改这些）

- `src/App.tsx`
- `src/pages/module-page.tsx`（新建）
- `src/features/modules/module-detail.tsx`
- `src/features/modules/pages/**`（新建）

## 明确不做

- 不改 `src/features/modules/api.ts`/`types.ts`/`i18n.ts`（B1 所有权）；不改 dashboard（B1）。
- 不做 widget 渲染器、工具注册表、S2 导入、LLM provider。
- 不支持 iframe/任意脚本；不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
```

报告 `reports/B3-module-pages-report.md`，≤80 行。必须写清：支持的块与字段、submit 协议、安全限制、截图与测试输出、未做项。
