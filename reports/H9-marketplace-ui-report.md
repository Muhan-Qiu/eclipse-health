# 报告 · H9 模块市场安装 UI（官方 / 社区 / 本地）

状态：完成

## 交付

- `src/features/modules/marketplace/types.ts`：索引条目、来源、更新、安装请求类型；对缺省字段按可选处理。
- `src/features/modules/marketplace/api.ts`：本地 `baseUrl` fetch；索引（q/category）、sources、updates、install；归一化 H8 的 `{updates,count}`（`moduleId/latestVersion`）与安装响应外层 `module`；市场错误码映射为可读文案。
- `src/features/modules/marketplace/marketplace-panel.tsx`：官方/社区/本地三 tab；搜索（300ms 防抖）、分类筛选（累积分类选项，避免过滤后选项塌缩）、模块卡（名称/版本/作者/许可证/类型/权限数/已验签/未审核/已安装/可更新）、加载/空/错误/未配置状态。
- `src/features/modules/marketplace/module-detail-dialog.tsx`：描述、版本/类型/作者/许可证/包大小/最低核心/分类、权限清单（复用 `permission-utils`，索引无风险字段时按 scope 保守映射）、依赖与联网提示、仓库链接、安装/更新按钮、安装中进度与可读错误；社区显示“未审核，风险自担”。
- `src/features/modules/marketplace/local-install.tsx`：原 `.ehmod` 选择 → 预览 → 权限确认 → 安装流程完整迁入第三个 tab。
- `src/features/modules/install-dialog.tsx`：改为安装入口外壳（Dialog + MarketplacePanel），保留 `initialTab`。
- `src/features/modules/modules-workspace.tsx`：页头按钮打开市场；新增“模块更新”横幅（可更新标记 + 查看更新）；安装成功后刷新 modules/contributions/audit/updates；移除页头直连隐藏文件选择。
- `src/features/modules/i18n.ts`：新增 `moduleUi.marketplace.*` 中英文案（含 12 个市场错误码）。
- `src/pages/modules.tsx` 未改动（面板由 workspace 接入）。

## 验证

- 命令：`npm run build` → pass（tsc + vite，`✓ built in 12.32s`，仅既有 >500 kB chunk 警告）。
- Playwright（系统 Chrome channel；`**/api/v1/**` 全拦截，H8 真实响应形状）：**17/17 pass**，4 个上下文控制台 error 均为 **0**。
  - 官方列表 + 已验签徽标 + 三 tab；搜索过滤；分类筛选；已安装/可更新徽标。
  - 详情：权限标签/风险、依赖、仓库链接、许可证；点“更新”后 POST body `{source:"official",moduleId,version}` 正确，成功 toast，modules 重新拉取。
  - 社区：顶部未审核警告 + 卡片/详情徽标 + 风险自担文案；社区详情显示 network 权限与依赖。
  - 安装失败（502 `marketplace_signature_invalid`）→ “市场索引验签失败”可读文案。
  - `configured=false` → 官方/社区均显示“市场地址未配置”。
  - 本地 tab：文件选择 → 预览权限 → 安装成功 toast。
  - 亮/暗主题各一张；见下。
- 截图（`reports/screenshots/`）：`H9-official-light.png`、`H9-official-dark.png`、`H9-detail-light.png`、`H9-detail-dark.png`、`H9-community-light.png`、`H9-install-error-light.png`、`H9-not-configured-light.png`、`H9-local-light.png`、`H9-local-preview-light.png`。

## 未做 / 偏离

- 更新标记未写到已安装模块行内：`module-list.tsx` 不在本批所有权，改为 workspace 顶部“模块更新”卡片（含每项 v旧→v新与入口）。
- 索引契约无权限风险分级；详情权限风险由本地保守映射（`records_delete`=高，写/网络/LLM/模型下载/UI/后台=中，其余=低）补齐，仅用于展示。
- 市场安装进度为不确定态（后端单次 POST 完成下载+校验+安装，无流式进度）；失败后可重试。
- 市场安装不传权限与 enable（H8 安装接口仅收 source/moduleId/version，后端默认 `enable=False`）；本地 `.ehmod` 仍保留权限勾选与安装后启用。
- Playwright 自带 chromium 未安装，改用系统 Chrome `channel="chrome"`；未新增项目依赖。
- 未对真实 H8 后端跑联调（按提示词用 API 拦截验证契约）；H8 已落地，可下一批用默认 `file://` 索引实跑。

## 跨区需求（需要别的 Agent 或指挥官处理）

- `src/features/modules/module-list.tsx`：建议接收 updates map，在模块行内显示“可更新”徽标与一键更新入口。
- H8：索引条目若增加权限风险/依赖大小字段，详情可去掉本地风险映射；`/install` 若支持 `permissions`/`enable`，市场安装可与本地安装的权限确认对齐。
- H8 `sources` 返回 `keyIds`（数组）与早期契约 `keyId` 不一致；前端已兼容两者，建议文档统一。

## 需要指挥官决策

- 社区模块安装是否必须二次确认弹窗（当前在详情内以红色警告 + 安装按钮提示）。

## 建议下一批

- 用真实 H8 后端 + 官方索引做端到端安装/更新（含 venv 依赖安装耗时与失败态）。
- 市场详情增加“更新会新增哪些权限”的差异提示（需索引或后端返回已安装 manifest）。
