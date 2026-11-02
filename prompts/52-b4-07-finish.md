# B5-03 · B4-07 收尾：设置页通知开关 + 手动指标编辑

> 先读 `prompts/00-COMMON.md`，再读本文件。项目根目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`

## 背景

B4-07 报告（`reports/B4-07-report.md`）已完成档案/指标/通知主体，但留了两个跨区缺口：

1. 设置页没有「分析完成通知」开关；watcher 只读 `localStorage["eh-notify-analysis-complete"]`（默认开启）。
2. 手动指标历史只能删除，不能编辑；后端 `PATCH /api/v1/metrics/{id}` 已实现并有测试。

本任务只补这两点，不重做 B4-07。

## 任务范围

### 1. 设置页通知开关

- 在 `src/features/privacy/desktop-panel.tsx` 的桌面偏好卡片里增加第三个开关「分析完成通知」：
  - 直接读写 `localStorage` 键 `eh-notify-analysis-complete`（复用 `src/features/profile/notifications.tsx` 导出的 `ANALYSIS_NOTIFICATIONS_KEY`，不要复制字符串）。
  - 默认开启；关闭后 watcher 下一轮轮询即停止（现有 watcher 已每轮读取，无需改轮询逻辑）。
  - **不要**把它塞进 `DesktopPreference` 类型，也不要调用 Tauri `invoke`/后端 settings API；这是纯前端偏好。
  - 用现有 `Switch` 组件、`Label`、`aria-label`；保存即时生效，toast 可选（建议不弹，避免噪音）。
- 文案加到共享 i18n（`settings.desktop.notifications*`，zh-CN/en-US），说明「仅在本机显示，不含心率数值，非诊断」。
- 设置页在浏览器预览与 Tauri 内都可用；不要求原生通知权限状态展示。

### 2. 手动指标编辑

- `src/features/profile/metrics-panel.tsx` 历史列表每行增加「编辑」入口（现有两段式删除旁边）：
  - 打开现有 Dialog/表单组件，编辑 `measuredAt`、四类数值、`notes`；类型（kind）不可改。
  - 复用 `src/features/profile/api.ts` 的 `updateMetric`（已存在）与现有校验/单位/范围提示；422 错误按现有 toast 展示。
  - 保存成功后刷新列表；取消不写入。
  - 保持两段式删除不变。
- 文案加到 feature-local `src/features/profile/i18n.ts`（zh-CN/en-US），不要改共享 i18n 的 profile 键。
- 若现有 `MetricPatch` 类型缺字段，可在 `src/features/profile/api.ts` 内补，不要动 `src/lib/api/**`（B5-01 所有权）。

### 3. 验收补漏

- 对照 `reports/B4-07-report.md` 的「验证」逐条确认；发现与代码不符的，修小问题或写进报告，不要扩大范围。
- 后端 `PATCH /metrics/{id}` 已有测试；如编辑 UI 暴露了新边界（如只改备注、只改时间），补 1–2 个测试到 `backend/tests/metrics/**`。

## 文件所有权（只改这些）

- `src/features/privacy/desktop-panel.tsx`
- `src/features/profile/**`（含 `api.ts`、`metrics-panel.tsx`、`i18n.ts`、`notifications.tsx`）
- `src/lib/i18n/**`（只新增 `settings.desktop.notifications*` 键）
- `backend/tests/metrics/**`（只补测试，不改生产代码）

## 明确不做

- 不改 `desktop-preferences.ts` 的 `DesktopPreference` 联合类型与 Tauri 命令映射。
- 不做指标趋势图、指标类型扩展、统一时间线。
- 不改 `src/lib/api/**`、`record-detail.tsx`、`records.tsx`、`dashboard.tsx`、`analysis-panel.tsx`。
- 不新增 Python/npm 依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\metrics -q
npm run build
```

手工验证：

- 设置页关闭通知 → localStorage 为 `false`，重新打开仍关闭；打开后恢复。
- 指标历史编辑血压/体重/备注/时间各一次，保存后列表即时更新；非法值显示后端 422 文案。
- 亮/暗截图各一张放 `reports/screenshots/B5-03-*.png`；控制台 0 error。

## 报告

写 `reports/B5-03-report.md`，≤80 行，结构按 `00-COMMON.md` §7。必须写清：通知开关存储方式、编辑 UI 覆盖字段、真实测试输出、B4-07 报告核对结果、未做项。
