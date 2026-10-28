# eclipse health v3 · 项目约定

## 核心原则（2026-10-28 新增）

- **开源、开放、本地优先、用户可调**。
- 核心最小化；设备适配、分析模型、健康领域、UI 组件、导出器、AI 工具全部模块化，官方与第三方同一套接口。
- 模块可下载、可卸载、可替换；支持官方索引、社区索引、自定义源、本地 `.ehmod` 安装。
- 提供本地 REST/OpenAPI + MCP，供其他应用与 AI 调用，也支持数据导出。
- UI 模块受设计令牌与声明式布局约束，避免破坏整体美感。
- 模块化与开放生态设计见 `docs/V3_MODULAR_ECOSYSTEM.md`；模块契约 v1 草案见 `docs/MODULE_CONTRACT_V1.md`；注册表与扫描见 `docs/REGISTRY_AND_SCANNING_V1.md`；UI 规范见 `docs/UI_COMPONENT_SPEC_V1.md`；数据 Schema 见 `docs/DATA_SCHEMA_V1.md`。
- 模块契约：stdio JSON-RPC；JSON Schema 为事实源；worker 懒启动常驻；大波形走临时文件句柄。
- 官方模块全部随安装包内置；权限仅在安装/升级时授权，升级新增权限必须重新确认。
- 模块 API 严格 semver + 2 个 minor 弃用期；允许模块直接互调，但 peer/token 由核心发放，禁止共享 Python 代码。
- 注册表：GitHub Pages 静态签名索引；仅静态扫描；不做下载统计；社区 ID 绑定 GitHub 身份（`io.github.<owner>.<name>`）。
- 撤回与治理：作者自行撤回，不做全局封禁；社区索引不治理；非 GitHub 开发者不能进入索引；扫描红色拒绝，黄/橙标注后允许安装。
- UI：12 列网格；声明式组件为主；任意 React/CSS 仅限沙箱 iframe/主题作用域；允许 iframe 直连网络（需 network 权限）；完整 CSS 主题可用但需预览与重置。
- 数据：前缀+UUIDv7；UCUM 单位；模块数据进 `records.payload`；beats 内联≤5 万，超出转文件；JSON Schema 2020-12；文件名默认脱敏；软删除 30 天；导出 WFDB/CSV/原始 float32。
- 字体：模块可自带 WOFF2，单文件 ≤2MB、单模块 ≤4MB；自定义 UI 仅标注；布局支持导出/导入 JSON。
- 运行时已定：独立 Python 进程 + 每模块独立 venv，核心内置 Python/uv 自动管理；用户无需安装额外软件。
- 许可证：核心 GPL-3.0；官方索引仅 OSI 开源模块，社区允许专有/付费并显著标注。
- 对外接口：本地 REST/OpenAPI + MCP + 事件流；模块上架采用自动扫描，不做人工审核。
- 模型格式：本地仅 ONNX / safetensors，远程模型需 `network` 权限。
- 官方功能（Cardia、ECG 分析、设备适配、UI 组件）也做成模块，预装但可卸载/替换。
- 模块更新按模块设置；核心不做支付，专有模块自行放授权/赞助链接。

## 角色（2026-10-28 起）

- Claude 当前只做四件事：**安装/配置工具与依赖、调研功能、写文档、逐条向用户确认**。
- 未经用户明确说「开始开发 / 重新弄 / 实现这个功能」，**不写业务代码、不改 UI、不接后端**。
- 所有 skills / MCP 只装项目内：`.claude/skills/`、`.mcp.json`；不得全局安装。
- 功能候选、难度评估与最终决策记录在 `docs/V3_FEATURE_BACKLOG.md`。

## 已确认的产品与技术决策

| 项 | 决策 |
|---|---|
| 名称 | eclipse health（被忽视的健康） |
| 平台 | Windows 桌面端（Tauri 2 + React 19 + TS） |
| 后端 | Python FastAPI sidecar，复用 Cardia 2.0 |
| LLM | API Key 多厂商 + 本地 Ollama 双通道 |
| 视觉 | 双主题；启动日食动画；logo 黑盘+亮环；配色莫奈低饱和，亮色主体白/暖白；详见 `docs/IDEAS.md` |
| MVP | V2 全部分析能力 + 本地记录库/趋势 + PDF/图片报告 + 工具调用可视化 |
| 扩展 | 暂不新增其他健康功能，只预留模块接口 |
| 功能范围 | 以 `docs/V3_FEATURE_BACKLOG.md` 为准（44 项已确认）；首版含 Samsung/华为/Apple 手表格式、SCP-ECG 医院格式 |
