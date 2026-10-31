# D3 · 最终打磨与反馈修复（动画补口 + 视觉一致性 + 用户意见）

> 先读 `prompts/00-COMMON.md`、`reports/D1-motion-report.md`、`reports/D2-visual-audit.md`、`docs/USER_FEEDBACK.md`，再读本文件。

## 目标

把 D1/D2 留下的跨区小口子和已知视觉不一致修完，并处理用户安装候选包后的新增反馈。**这是最终包前的最后一轮代码改动。**

## 用户已确认的动画方向（已由 D1 实现，本批只补缺口）

- 整体「明显丰富」；启动日食、切页/弹窗/主题、卡片/列表入场、数值/图表/波形都要明显。
- logo 进入后慢速循环（8s）；启动收束线性；侧栏导航斜向扩展填满内容区。
- 不要弹跳/旋转、发光/玻璃感、太慢/阻塞、太多同时动。

## 任务（按优先级）

### 1. 波形 R 峰反馈（D1 跨区）

- `src/features/waveform/lead-strip.tsx`（canvas 绘制层）：
  - 选中 R 峰/心搏时，高亮竖线/圆点 120ms 过渡 + 一次性轻微脉冲（不循环）；
  - hover 质量区段/异常标记时轻微 alpha/线宽反馈，不遮挡波形；
  - `prefers-reduced-motion` 时无脉冲，仅颜色变化；
  - 不改变波形数据/缩放/平移逻辑。

### 2. 模块卡片加载态（D1 跨区）

- `src/features/modules/widgets/widget-card.tsx`：RPC 加载/刷新时骨架→内容 200ms 淡入；失败重试保持现有错误态；不改变 B1 的失败隔离。

### 3. 时长格式统一（D2 跨区）

- `src/lib/format.ts#formatDuration` 统一规则：
  - `< 60s`：`0:SS`（整数秒；需要时保留一位小数 `0:SS.S`，但同一列表固定精度）；
  - `>= 60s`：`M:SS` 或 `H:MM:SS`；
  - 默认不显示毫秒；波形/分析内部仍可用毫秒。
- 更新调用点：记录页、仪表盘、报告选择器、健康数据（睡眠时长除外）、记录行；同一列表内精度一致。
- 补/更新相关测试（若有）；无测试则用页面截图核对 3 个列表。

### 4. 仪表盘「最近记录」空白（D2 跨区）

- `src/pages/dashboard.tsx`：最近记录卡片与右列等高导致短列表下方大块空白；改为内容高度自适应（如父网格 `items-start` 或卡片自身 `self-start`），不影响其他卡片布局。

### 5. 报告记录选择器摘要一致（D2 跨区）

- `src/features/reports/record-picker.tsx`：第二行改为与记录页一致的「文件/设备 · 导联 · 采样率」结构，去掉「—」占位；长文本截断。

### 6. 健康数据/模块列表入场（D1 跨区）

- `src/pages/health-data.tsx`、`src/pages/modules.tsx`：列表/卡片前 8–12 行 stagger 入场（复用 `src/lib/motion.ts`），reduced-motion 直接显示；不改变筛选/分页。

### 7. 用户新增反馈（指挥官填写）

- （待填：用户安装候选包后的具体意见。若为空，按上面 1–6 执行。）

### 8. 最终验证

- `npm run build`、`backend/.venv/Scripts/python.exe -m ruff check backend` 通过。
- 亮/暗截图：波形选中、模块卡片、记录/报告/健康数据列表、仪表盘；放 `reports/screenshots/D3-*.png`。
- reduced-motion 模拟无动画、无报错；控制台 0 error。

## 文件所有权（只改这些）

- `src/features/waveform/lead-strip.tsx`
- `src/features/modules/widgets/**`
- `src/lib/format.ts`
- `src/pages/dashboard.tsx`、`records.tsx`、`health-data.tsx`、`modules.tsx`
- `src/features/reports/record-picker.tsx`
- `src/components/records/record-row.tsx`
- `src/lib/i18n/**`（只修文案/长度）
- `reports/D3-*.md`、`reports/screenshots/D3-*.png`

## 明确不做

- 不改后端/接口/数据；不改 `src/components/ui/**`（除非仅修格式导致的显示问题）。
- 不重做动画系统、不改启动/logo/导航转场（D1 已完成）。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
npm run build
```

报告 `reports/D3-final-polish-report.md`，≤80 行。必须写清：每项修复位置、时长格式规则、截图、用户反馈处理结果、未做项。
