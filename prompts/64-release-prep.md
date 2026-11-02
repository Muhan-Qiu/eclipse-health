# A5 · 发布准备：路由懒加载 + README + 依赖声明 + release notes 草稿

> 先读 `prompts/00-COMMON.md`，再读本文件。**不要重打安装包**（等代码轮结束由指挥官统一做）。

## 目标

为发布轮清掉低风险收尾项，不碰平台/引擎/模块代码。

## 交付

### 1. 路由懒加载

- `src/App.tsx`：把页面改为 `React.lazy` + `Suspense`，保留现有 `HashRouter` 与 `AppShell` 结构；首屏只加载 Dashboard/AppShell，其余按路由分包。
- 加载态用现有 `Skeleton` 或简单占位，不要新增大依赖。
- 目标：主包体积明显下降（当前约 1.36 MB）；记录 build 前后主 chunk 大小。
- 不改变任何页面行为/URL。

### 2. README

- 更新根 `README.md`（如已过时）：一句话定位、功能范围（ECG 导入/分析/记录/趋势/报告/助手/模块）、安装与开发命令、数据与隐私（本地优先、无遥测）、已知限制（H5 自动更新、G3 真机格式、SmartScreen 未签名）。
- 命令必须与本机一致：`backend\.venv\Scripts\python.exe -m ...`、`npm run dev/build`。
- 不写营销文案，不承诺未验证功能。

### 3. 依赖声明

- 检查 `backend/pyproject.toml` 的 dependencies 是否覆盖实际运行所需（numpy/scipy/wfdb/neurokit2/onnxruntime/matplotlib/Pillow/Jinja2/litellm/pydantic-ai/sse-starlette/fastapi/sqlmodel 等）。
- 只补声明，**不要 pip install**；缺的写进报告。
- 前端 `package.json` 只核对，不改版本。

### 4. release notes 草稿

- 新建 `docs/RELEASE_NOTES_DRAFT.md`：版本 0.1.0 的功能清单、安装说明、已知限制、校验和占位（由发布轮填）。
- 按用户视角写，不贴 commit 列表。

## 文件所有权（只改这些）

- `src/App.tsx`
- `README.md`
- `backend/pyproject.toml`（仅 dependencies 声明）
- `docs/RELEASE_NOTES_DRAFT.md`（新建）

## 明确不做

- 不跑 `npm run tauri build` / PyInstaller；不改 `src-tauri/**`、`scripts/**`。
- 不改页面组件、后端业务代码、模块/引擎代码。
- 不新增依赖、不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
backend\.venv\Scripts\python.exe -m ruff check backend
```

- 报告 build 前后主 chunk 大小与总 chunk 数。
- 手工打开 Dashboard/Records/Assistant 路由，确认懒加载后无白屏/报错（可用 dev server 或 build preview）。

报告 `reports/A5-release-prep-report.md`，≤80 行。
