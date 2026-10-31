# D2 · 视觉/可用性 QA（亮暗、对比度、间距、焦点、窄窗）

> 先读 `prompts/00-COMMON.md`、`docs/UI_COMPONENT_SPEC_V1.md`、`src/lib/theme.tsx`、`src/lib/palettes.ts`，再读本文件。

## 目标

在候选包交付前做一轮系统视觉 QA：不改变产品结构，只修一致性问题、可读性问题和小屏/长文本破版。**不做动画**（D1 所有权）。

## 检查范围（每页亮/暗各一遍）

页面：仪表盘（只读，不改 D1 文件）、记录、健康数据、记录详情（只读 D1 文件）、趋势、对比、报告、助手、健康档案、模块、设置、关于。

检查项：

1. **对比度**：正文/次要文字/占位符/禁用态在亮暗两套主题下可读；小字号（caption）不糊。
2. **焦点与键盘**：Tab 顺序合理；焦点环可见；按钮/开关/链接有 `:focus-visible`；图标按钮有 aria-label。
3. **间距与对齐**：卡片内边距、标题/描述/操作区节奏一致；表格数字右对齐/等宽；图标与文字基线对齐。
4. **长文本/空状态**：长标题、长模块名、长错误信息不溢出；空状态文案不重复、有下一步操作。
5. **窄窗**：1024px 与 1440px 下无横向滚动（除波形/表格预期内）；侧栏折叠正常。
6. **表格/列表**：分页、筛选、选中态、hover、禁用态一致；数值单位不换行错位。
7. **颜色语义**：成功/警告/错误不只靠颜色，均有图标/文字；不新增高饱和色。
8. **暗色**：卡片/边框/阴影层次可辨；波形底色/网格线不刺眼。

## 交付

- 新建 `reports/D2-visual-audit.md`：逐页问题清单（问题、严重度、是否修复、截图）。
- 修复范围内的问题；每个修复点保持设计令牌，不写死颜色。
- 截图：修复前后关键页亮/暗各一组，放 `reports/screenshots/D2-*.png`。
- 若问题属于 D1 文件（dashboard/record-detail/branding/layout/common/waveform），只记录不修，写「跨区需求」。

## 文件所有权（只改这些）

- `src/pages/records.tsx`、`health-data.tsx`、`trends.tsx`、`compare.tsx`、`reports.tsx`、`assistant.tsx`、`profile.tsx`、`settings.tsx`、`modules.tsx`、`about.tsx`
- `src/components/ui/**`
- `src/components/records/**`（`waveform-viewer.tsx` 及其 waveform 子组件除外）
- `src/features/**`（`modules/widgets/**`、`modules/pages/**` 除外）
- `src/lib/i18n/**`（只修文案/长度问题，不改结构）
- `reports/D2-visual-audit.md`、`reports/screenshots/D2-*.png`

## 明确不做

- 不改 `src/pages/dashboard.tsx`、`record-detail.tsx`、`src/branding/**`、`src/components/layout/**`、`src/components/common/**`、`src/index.css`、`src/lib/motion.ts`（D1 所有权）。
- 不改 `src/features/modules/widgets/**`、`modules/pages/**`、`src/components/records/waveform-viewer.tsx`。
- 不改业务逻辑/接口/数据；不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
```

- 逐页截图对照，控制台 0 error。
- 报告必须给出「修了哪些、没修哪些、为什么」。

报告 `reports/D2-visual-audit.md`，≤100 行（审计表可紧凑）。
