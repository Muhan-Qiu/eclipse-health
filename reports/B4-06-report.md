# 报告 · B4-06 模块安装 / 权限 / 审计 UI

状态：完成

## 交付
- 后端 `POST /modules/preview-upload`：上传 `.ehmod` 后完整预检（ZIP 魔数、大小、解压安全、manifest schema、核心兼容、layout、checksums），返回 manifest 摘要、权限清单、风险、警告、是否已安装、升级新增权限；不写模块目录。
- 后端 `POST /modules/install-upload`：multipart `.ehmod + enable + permissions`；流式写入临时文件（200MB 上限，超限 507 `RESOURCE_EXCEEDED`），校验扩展名/ZIP 魔数，调用既有安装器后删除临时文件；`permissions` 只允许 manifest 已请求的 scope，安装后按勾选补授/撤销（高风险必须显式列出）。响应与 `/modules/install` 同构。
- 权限元数据：`modules/permissions.py` 新增 `PERMISSION_META` / `HIGH_RISK_SCOPES` / `describe_scope` / `permission_catalog`；`GET /modules/{id}/permissions` 与 grant/revoke 响应新增 `scopes[]`（含 risk/label/description/requested/granted），旧字段不变；新增 `GET /modules/permission-catalog`。
- 审计：`GET /modules/audit` 在既有过滤/limit/offset 基础上补 `limit/offset/hasMore`；仍按时间倒序，UI 采用“最新在前 + 加载更多”。
- 详情数据：新增 `GET /modules/{id}/manifest` 投影（作者/许可证/贡献点/资源/i18n/权限），不含 entry 路径、绝对路径或 token。
- 前端 `src/features/modules/**`：安装对话框（文件 → 预检 → 权限逐项勾选 → 启用开关 → 安装）、已安装列表（状态/类型/版本/权限数/安装时间，启停/启禁/详情/卸载）、详情抽屉（manifest、贡献点/模型卡、权限授予/撤销、最近审计）、审计面板（模块/动作过滤、分页加载）、卸载对话框（保留/删除数据）、完整错误文案映射与 feature-local i18n。
- 风险清单：高风险 `records:delete`、`network`、`ui:custom`（默认不勾选；勾选后安装按钮变为“安装（含高风险权限）”）；中风险 `records:write`、`files:export`、`llm`、`models:download`、`system:background`；低风险 `records:read`、`files:user-selected`、`system:notify`。升级新增权限默认不勾选，低/中风险首次安装默认勾选。
- 页面：`src/pages/modules.tsx` 只组合 `ModulesWorkspace`，未改共享 i18n、App 路由或 API 客户端。

## 验证
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q` → **80 passed**（新增 `test_api_upload.py` 12 例：预检不安装、权限勾选、高风险默认拒绝、未知 scope 拒绝安装、坏包/错扩展名/超大、版本不兼容、manifest 投影、卸载保留/删除数据、审计过滤与分页、升级新增权限、零权限后核心调用 `PERMISSION_DENIED`）。
- `pytest backend\tests\api backend\tests\modules -q` → **114 passed**，exit 0。
- `ruff check backend/src/.../modules backend/tests/modules` → All checks passed。
- `npm run build` → pass（tsc + vite 3.37s；1,331.07 kB / gzip 409.13 kB，仅沿用 >500 kB 提示）。
- 真后端（临时 `EH_DATA_DIR`，端口 8766）+ Vite（1421）手测：高风险包预检显示 4 项权限、2 项高风险未勾选；安装 demo → 列表/详情/启动 → 审计出现 install/start；UI 卸载（保留数据）成功，`GET /modules` 只剩 Cardia，审计 `module.uninstall keepData=true`；console 0 error。
- 截图：`B4-06-install-permissions-light.png`、`B4-06-install-high-risk-light.png`、`B4-06-modules-light.png`、`B4-06-modules-light-running.png`、`B4-06-module-detail-light.png`、`B4-06-audit-light.png`、`B4-06-uninstall-light.png`、`B4-06-modules-dark.png`、`B4-06-module-detail-dark.png`。

## 未做 / 偏离
- 权限勾选在安装后通过 grant/revoke 落地：内核安装器仍会先授予“非默认拒绝”的 scope，API 立即按用户选择撤销；模块此时未启动，不存在越权执行窗口，但审计会多出 `permission.revoke`。
- 内核 `DEFAULT_DENIED_SCOPES` 仍只有 `records:delete`；`network`/`ui:custom` 的“默认不授予”由上传入口的 UI 选择实现，未改状态机/内核默认。
- 审计排序固定最新在前，未加升序参数；`hasMore` 以 `count == limit` 估算，边界时可能多出一次空加载。
- 预检只展示升级新增权限，不展示被移除权限；未做 manifest 权限差异的全量对比。
- 未做：注册表/在线下载/签名、每模块 venv、模块市场、真实设备模块、沙箱 iframe、模块配置表单（按提示词明确不做）。
- 本机 1420 端口被其他进程占用，UI 验证使用 1421 + `VITE_API_BASE` 指向 8766；未改任何配置。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 若希望 `.ehmod` 走系统文件对话框而非 webview `<input type=file>`，需要 B4-01 在 Tauri 侧提供 open-dialog 命令；当前输入框方案与导出/恢复页一致。
- B1-02 的安装器无法接收“安装时选择的权限集合”；本批用安装后 grant/revoke 兼容，后续可考虑 `install(..., permissions=...)` 原生支持。

## 需要指挥官决策
- 高风险权限是否需要“二次弹窗”确认（当前为显式勾选 + 按钮文案变化）；如需要可加一层 AlertDialog。
- 是否把 `network`、`ui:custom` 也加入内核 `DEFAULT_DENIED_SCOPES`，使 API/内核默认一致。

## 建议下一批
- 模块市场/注册表索引、模块配置与密钥设置、每模块 venv、安装进度与取消、升级权限差异全量展示。
