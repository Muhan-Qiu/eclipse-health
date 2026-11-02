# 报告 · A5 发布准备（路由懒加载 + README + 依赖声明 + release notes）

状态：完成

## 交付
- `src/App.tsx`：仅 Dashboard 静态加载；其余 11 个页面改用 `React.lazy`，路由元素外包一层 `Suspense`（fallback 用现有 `Skeleton`）。`HashRouter`、`AppShell`、URL 与页面行为未变；AppShell 不会在切页时卸载。
- `README.md`：重写为发布口径——定位、功能范围、安装/开发/测试命令、数据位置与隐私、已知限制（H5/G3/SmartScreen）。
- `backend/pyproject.toml`：仅补 `sqlalchemy>=2.1.6`、`pydantic>=2.14.1`、`starlette>=1.10.0` 三条直接依赖（源码中大量直接 import，原先只靠传递依赖）。
- `docs/RELEASE_NOTES_DRAFT.md`：新建 0.1.0 发布说明草稿（功能、安装、已知限制、校验和占位）。

## 验证
- `npm run build` 通过（tsc + vite，2.83 s）。
  - 主 chunk：`index` **1,372.74 kB / gzip 420.89 kB → 583.81 kB / gzip 186.86 kB**（−57%）。
  - JS chunk 数：**3 → 76**（新增多为 icon/共享小组件；最大的路由 chunk 为 `trends` 335.60 kB，仍按需加载）。
  - CSS：140.93 → 140.97 kB（无实质变化）。
- `backend\.venv\Scripts\python.exe -m ruff check backend`：本任务文件无告警；当前全量报 **4 个 RUF100**，全部位于并行 Agent 的 `analysis_service/onnx_engine.py`（A3），未介入。
- 路由冒烟（`vite preview` + headless Chrome/CDP，真实后端 8765）：`/`、`/records`、`/records/does-not-exist`、`/profile`、`/trends`、`/reports`、`/assistant`、`/settings`、`/modules`、`/about`、`/compare`、`/nope` 全部渲染出正文与侧栏，**0 个 console error / page error**；详情页的 2 条 404 是伪造 id 的预期 API 响应。
- `pyproject.toml` 经 `tomllib` 解析通过；共 23 条 dependencies。

## 未做 / 偏离
- 未改 `vite.config.ts`（不在所有权内），因此未手工合并 vendor chunk；76 个 chunk 中约 40 个是 lucide 图标小文件，本地 asset 加载影响可忽略。
- 未 `npm install` / `pip install`，未重打 Tauri/PyInstaller 包，未 commit。
- 依赖核对发现 `jinja2`、`pillow`、`pandas`、`orjson`、`pydantic-ai` 当前 `backend/src` 无直接引用；按要求只补不改，保留原声明。
- README 中「软删除后可彻底清除」按实际能力写成隐私页「清空数据」，未承诺 30 天自动清理（后端目前没有定时清理）。
- release notes 中厂商格式写为 `experimental`，与现有适配器实现一致。

## 跨区需求（需要别的 Agent 或指挥官处理）
- i18n 缺 `nav.profile`：侧栏、档案页标题显示原始 key（B5-03/i18n 区域，非本任务文件）。
- `analysis_service/onnx_engine.py`（A3）的 4 个 RUF100 会让全量 `ruff check backend` 失败；等 A3 完成后需清理。
- 其余并行改动（modules/、schemas/、docs/）未触碰。

## 需要指挥官决策
- 发布轮是否移除上面 5 个「声明但未引用」的依赖（影响打包体积与 PyInstaller 收集范围，本任务无权决定）。
- release notes 的安装包文件名/大小/校验和需在 Stage C 重打包后填写；MSI 当前未验证，已标「可选」。

## 建议下一批
- Stage C：重打包后补 `docs/RELEASE_NOTES_DRAFT.md` 校验和表，统一跑全量 `pytest` + `ruff` + `npm run build`。
- 修 `nav.profile` key；可顺手把 icon chunk 合并进共享 chunk（需改 vite 配置，需授权）。
