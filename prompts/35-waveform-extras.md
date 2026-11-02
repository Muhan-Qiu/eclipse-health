# B4-05 · 波形增强（心搏列表 / 节律条 / 12 导联展示 / PNG）

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B4 收口（Wave 2）
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：把记录详情从「能看」做到「能复查」；分析仍是单导联 Cardia，12 导联只做展示。

## 1. 必读

- `docs/V3_FEATURE_BACKLOG.md`：B3 心搏列表、B5 12 导联布局、B6 节律条、B7 波形 PNG、A6 快捷键。
- `docs/UI_COMPONENT_SPEC_V1.md`：§2 布局、§7 图表、§8 可访问性。
- `docs/INTERNAL_API_V1.md`：§1 信号、§3 分析/beats。
- `reports/B2-03-report.md`、`reports/B3-02-report.md`、`reports/B4-03-report.md`（多导联导入）。
- 代码：`src/components/records/waveform-viewer.tsx`、`src/pages/record-detail.tsx`、`src/lib/waveform.ts`、`src/lib/api/queries.ts`。

## 2. 你必须交付

1. **心搏列表（B3）**
   - 侧栏/表格：所有心搏按时间/类别筛选（N/SVEB/VEB/F），异常优先；显示 index、R 峰时间、类别、置信度、RR。
   - 点击定位到波形（缩放/平移/选中），键盘上下切换；支持「只看异常」。
   - 大记录分页/虚拟滚动（用现有 beats 分页接口或一次性加载上限 5k，超限提示）。
2. **节律条 Overview（B6）**
   - 波形上方/下方全记录缩略条（min/max 包络 + 当前视窗高亮）；点击/拖动跳转；与主波形缩放联动。
   - 长记录（650k 点）不卡：预计算包络，避免每次重算。
3. **12 导联展示（B5）**
   - 多导联记录：3×4 网格或纵向堆叠，导联名/单位/标尺；单导联回退。
   - **明确标注**：分析仅使用主导联（MLII/第一导联），12 导联仅展示；不要把展示说成 12 导联分析。
   - 导联切换与主视图同步；导出 PNG 时包含当前布局。
4. **波形 PNG（B7）**
   - 导出当前视图（或完整记录）PNG：波形 + 导联/采样率/时间范围 + 记录日期 + 「非诊断」水印；前端 Canvas 生成，下载；不依赖后端。
5. **快捷键（A6）**
   - 记录内：`+/-` 缩放、方向键平移、`0` 重置、`[ ]` 上一个/下一个记录（或心搏）、`Esc` 取消选中；不劫持输入框。
6. **质量区段**
   - 质量区段底色 + 图例 + 区段列表（时间/等级/原因），点击定位；与 B4 已有 `quality.segments` 兼容。
7. **质量**：i18n 用 feature-local bundle（`src/features/waveform/i18n.ts`），不改共享 i18n；1080×700 不塌；暗色可读；截图 `reports/screenshots/B4-05-*.png`。

## 3. 文件所有权（只能改这些）

```
src/components/records/waveform-viewer.tsx
src/components/records/beat-list.tsx（新）
src/components/records/quality-legend.tsx（新）
src/features/waveform/**
src/lib/waveform.ts
src/pages/record-detail.tsx
reports/screenshots/B4-05-*.png
```

只读：`src/lib/api/**`（B3-02 已定义 queries/types；需要新查询时在 `src/features/waveform/` 内 fetch，不改共享）。
不要动：`src/App.tsx`、`src/lib/i18n/**`、`src/lib/nav.ts`、`src/pages/{records,trends,compare,reports,assistant,settings,modules,profile}.tsx`、`src/features/{assistant,reports,trends,modules,profile}/**`、`src-tauri/**`、`backend/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 4. 依赖与性能

- 已装 uPlot；不新增图表库。
- 650k 点：主波形继续按像素 min/max 降采样；Overview 用固定桶（如 2,000 桶）预计算；切换导联时缓存。
- 不在渲染中同步做 O(n²) 心搏查找。

## 5. 验收

```powershell
npm run build
npm run dev
# 用 MIT-BIH 100（单导联）与 B4-03 导入的多导联 EDF/SCP-ECG 记录：
# 心搏列表跳转、节律条拖动、12 导联网格、PNG 下载、快捷键
```

报告写：功能清单、性能（首屏/拖动）、单/多导联截图、已知限制（12 导联仅展示）。

## 6. 明确不做

12 导联分析/新模型、打印、PDF（B3-03 已有）、移动端、波形编辑/标注写回、节律条预测。
