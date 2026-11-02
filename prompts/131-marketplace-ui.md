# H9 · 模块安装 UI：官方市场 / 社区市场 / 本地文件

> 先读 `prompts/00-COMMON.md`、`src/features/modules/**`、`src/pages/modules.tsx`、`backend` 的 marketplace API 契约（prompts/130）。
> **思考强度：low。** 复用现有模块页/安装对话框，不重写。

## 目标

模块页「安装模块」变成三个入口：**官方市场**、**社区市场**、**本地文件**。市场里能搜索、看详情/权限/依赖、安装/更新；社区显著标注“未审核”。

## 后端契约（H8）

- `GET /api/v1/marketplace/index?source=official|community&q=&category=` → `{source, keyId, modules:[...]}`（已验签）
- `GET /api/v1/marketplace/updates` → `{items:[{id,name,installedVersion,availableVersion,...}]}`
- `POST /api/v1/marketplace/install` `{source,moduleId,version}` → 模块摘要
- `GET /api/v1/marketplace/sources` → `{official:{configured,url},community:{...},keyId}`
- 错误：`marketplace_not_configured`、`marketplace_signature_invalid`、`marketplace_download_failed`，前端要可读。

## 交付

- 新建 `src/features/modules/marketplace/`：
  - `api.ts`（本地 fetch，用 `baseUrl`）、`types.ts`；
  - `marketplace-panel.tsx`：tabs（官方/社区/本地）；搜索框、分类筛选；模块卡（名称/版本/作者/许可证/类型/权限数/verified 徽标）；空/加载/错误（未配置时说明“市场地址未配置”）。
  - `module-detail-dialog.tsx`：描述、权限列表（复用 `permission-list`/permission-utils）、依赖列表（提示首次安装会联网）、仓库链接、许可证、安装/更新按钮、进度/错误；社区显示“未审核，风险自担”。
  - `local-install.tsx`：保留现有本地 `.ehmod` 上传/预览/安装流程，作为第三个 tab。
- `src/pages/modules.tsx` / `modules-workspace.tsx` / `install-dialog.tsx`：接入新面板；已安装模块显示“可更新”标记；安装成功后刷新模块列表与 contributions。
- 文案 `src/features/modules/i18n.ts`（新 marketplace.* 键，中英）。
- 验证：`npm run build`；CDP/Playwright 拦截 API：官方列表、搜索、详情权限、安装成功/失败、社区警告、未配置、本地文件 tab；截图亮/暗 `reports/screenshots/H9-*.png`；控制台 0 error。

## 文件所有权（只改这些）

- `src/features/modules/marketplace/**`（新建）
- `src/pages/modules.tsx`
- `src/features/modules/modules-workspace.tsx`
- `src/features/modules/install-dialog.tsx`
- `src/features/modules/i18n.ts`
- `reports/H9-*.md`、`reports/screenshots/H9-*.png`

## 明确不做

- 不改后端（H8）、不做网站/上传表单（H10）、不改核心安装逻辑。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

报告 `reports/H9-marketplace-ui-report.md`，≤80 行。
