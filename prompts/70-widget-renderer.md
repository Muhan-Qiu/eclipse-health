# B1 · 平台 #2：首页 widget 渲染器（受控组件）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md` 的 `ui.widgets` 段，再读本文件。

## 目标

在仪表盘渲染已安装模块声明的 `contributes.ui.widgets`。第三方只交 JSON，核心用受控组件渲染，不执行任意 React/CSS。

## 交付

### 1. 前端数据层

- `src/features/modules/api.ts` 增加：
  - `listContributions(type?)` → `GET /api/v1/modules/contributions`；
  - `callModuleRpc(moduleId, method, params)` → `POST /api/v1/modules/{id}/rpc`，返回 `result`；
  - 错误复用现有 `errors.ts`。
- `src/features/modules/types.ts` 增加 widget/contribution 类型（与 `MODULE_CONTRACT_V2.md` 一致）。

### 2. 渲染器

- 新建 `src/features/modules/widgets/`：
  - `widget-grid.tsx`：读取 widgets 贡献，按 `size` 排 12 列网格；loading/empty/error 状态。
  - `widget-card.tsx`：标题、模块来源、刷新、错误；数据来自 `dataSource.method` + `params`。
  - 受控视图：`stat`、`sparkline`、`list`、`progress`、`text` 五种；`valuePath` 用安全路径读取（只支持 `a.b.c` 与数组索引，禁止 `eval`）。
  - 所有颜色/间距走现有设计令牌；不引入图表库，sparkline 用现有 `Sparkline` 组件。
- `src/pages/dashboard.tsx`：在「最近记录」上方或下方增加「模块卡片」区域；无 widgets 时整块不显示，不留空壳。
- 点击卡片可跳转模块页（若 `link` 字段存在），否则无交互。
- 文案加到 `src/features/modules/i18n.ts`（feature-local，zh-CN/en-US）。

### 3. 安全与容错

- 只渲染白名单 view type；未知类型显示「不支持的卡片类型」，不崩溃。
- 单个 widget RPC 失败只影响该卡片；不阻塞仪表盘其他内容。
- 不把模块返回的 HTML 当 DOM 渲染；文本按纯文本处理。
- 模块 disabled/卸载后卡片消失（重新拉 contributions）。

### 4. 测试

- `npm run build` 通过。
- 用 Playwright/CDP 拦截 `/modules/contributions` 与 `/modules/{id}/rpc`，验证：
  - 0 个 widget 时无空区域；
  - 5 种 view 各渲染一次；
  - 一个 widget RPC 失败时其他卡片仍显示；
  - 未知 view type 显示降级文案。
- 亮/暗截图放 `reports/screenshots/B1-widgets-*.png`，控制台 0 error。

## 文件所有权（只改这些）

- `src/features/modules/api.ts`
- `src/features/modules/types.ts`
- `src/features/modules/i18n.ts`
- `src/features/modules/widgets/**`（新建）
- `src/pages/dashboard.tsx`

## 明确不做

- 不改后端、不改 `schemas/`、不改 `src/App.tsx`。
- 不做模块页渲染器（B3）、工具注册表（B2）、S2 导入（B4）、LLM provider（B5）。
- 不支持 iframe/任意 React/CSS；不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
```

报告 `reports/B1-widgets-report.md`，≤80 行。必须写清：支持的 view 字段、valuePath 安全规则、失败隔离、截图与测试输出。
