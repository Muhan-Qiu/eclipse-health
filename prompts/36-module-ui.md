# B4-06 · 模块安装 / 权限 / 审计 UI

> 难度：中等偏难 3/4 · 建议思考强度：**high** · 批次：B4 收口（Wave 2）
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：把 B1-02 的模块内核变成用户可操作的模块页：选 `.ehmod` → 看权限 → 安装 → 启停 → 卸载 → 看审计。

## 1. 必读

- `docs/MODULE_CONTRACT_V1.md`：§1 包格式、§2 manifest、§4 生命周期、§6 权限、§11 安全与审计、§12 错误码。
- `reports/02-module-system-report.md`（内核 API/状态/错误码/示例 echo）。
- `reports/B2-01-report.md`（核心模块安装/自动安装）。
- 代码：`backend/src/.../modules/api.py`、`modules/manager.py`、`modules/permissions.py`、`modules/audit.py`、`src/pages/modules.tsx`、`src/lib/api/client.ts`。

## 2. 你必须交付

### 后端

1. **上传安装**
   - `POST /modules/install-upload`（multipart `.ehmod` + `enable`）：保存临时文件 → 调现有安装器 → 清理；返回与 `POST /modules/install` 相同结构。
   - 大小限制（如 200MB）、扩展名/魔数校验、路径穿越由安装器负责；错误映射到现有 `{code,message,details}`。
   - 安装前返回/展示 manifest 请求的权限（可在 preview 端点或 `GET /modules/pending`；二选一，写进 OpenAPI）。
2. **权限**
   - UI 安装时逐项确认；`records:delete` 等高风险默认不授予，需显式勾选；升级新增权限不自动授予（B2 已定）。
   - `GET/POST/DELETE /modules/{id}/permissions/{scope}` 已存在，补 UI 需要的 `risk`/`label` 元数据（可在响应里加字段，不破坏旧字段）。
3. **审计**
   - `GET /modules/audit?moduleId=&action=&from=&to=&limit=` 已存在；补分页/排序（如缺），UI 可读。
4. **测试**：上传安装/坏包/超大/权限拒绝/卸载保留数据/审计过滤；用 `modules/demo.echo` 打包产物。

### 前端

5. **模块页**（`src/pages/modules.tsx` + `src/features/modules/**`）
   - 顶部「安装模块」：文件选择 `.ehmod` → 权限清单（scope + 风险 + 说明）→ 安装/取消；显示版本/作者/许可证/类型。
   - 已安装列表：名称/ID/版本/类型/状态（enabled/running/stopped/disabled/crashed）、权限数、安装时间；启停/禁用/卸载（保留/删除数据二选一）。
   - 模块详情抽屉/弹窗：manifest 摘要、贡献点、资源限制、模型卡（如有）、权限列表（可撤销）、最近审计。
   - 审计面板：按模块/动作过滤，显示时间/动作/范围，不显示敏感参数。
   - 错误态：坏包、校验失败、版本不兼容、权限拒绝、崩溃；给出可读文案。
6. **i18n/边界**：feature-local bundle（`src/features/modules/i18n.ts`），不改共享 i18n；只读共享 `apiFetch`/类型；截图 `reports/screenshots/B4-06-*.png`。

## 3. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/modules/api.py
backend/src/eclipse_health_backend/modules/permissions.py   # 仅加 risk/label 元数据
backend/tests/modules/**
src/pages/modules.tsx
src/features/modules/**
reports/screenshots/B4-06-*.png
```

不要动：`src/App.tsx`、`src/lib/i18n/**`、`src/lib/api/**`、`src/pages/{settings,profile,record-detail,...}.tsx`、`src/features/{waveform,profile,export,privacy,assistant,reports,trends}/**`、`src-tauri/**`、`backend/{analysis,analysis_service,importers,export,privacy,diagnostics}/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 4. 契约

- 模块内核已实现安装/启停/权限/审计/RPC；你只补上传入口和 UI，不改状态机。
- 高风险权限（`records:delete`、`network`、`ui:custom`）必须在 UI 中显式标注并要求确认。
- 不显示绝对路径/内部 token。

## 5. 验收

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules -q
npm run build
# 打包 demos：python scripts/pack_demo.py → 上传安装 → 权限确认 → 启停 → 审计 → 卸载
```

报告写：上传/权限/审计实现、风险权限清单、截图、未做项。

## 6. 明确不做

注册表/在线下载/签名公钥/社区索引、每模块 venv、模块市场 UI、真实设备模块（B4-03）、沙箱 iframe。只做本地 `.ehmod` 安装与权限审计。
