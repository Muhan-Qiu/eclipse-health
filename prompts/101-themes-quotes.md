# F2 · 主题扩展（3 高饱和 + 2 玻璃）+ 30 句每日健康名言

> 先读 `prompts/00-COMMON.md`、`docs/USER_FEEDBACK.md`、`src/lib/theme.tsx`、`src/lib/palettes.ts`、`src/index.css`。
> 用户要求：保留现有莫奈三套与诗意命名；新增高饱和与玻璃主题；每天进入显示一句健康名言。

## 交付

### 1. 主题：3 套高饱和 + 2 套玻璃

- 保留现有 `a/b/c`（睡莲 / 日出·印象 / 日本桥）。
- 新增 5 套，ID 用稳定英文：
  - 高饱和：`starry`（星夜）、`sunflower`（向日葵）、`wave`（神奈川冲浪里）
  - 玻璃：`mist`（晨雾）、`glaze`（琉璃）
- 每套都要有**亮色与暗色**两版完整变量（背景/卡片/侧栏/边框/文字/强调/波形网格/图表色）；高饱和不是荧光，保持文字对比度 ≥ WCAG AA。
- `src/lib/theme.tsx`：`PALETTES` 扩展；新增 `glass: boolean` 或 `data-glass` 标记（仅 mist/glaze）。
- `src/lib/palettes.ts`：补充 5 套预览色（每套 5 色）。
- `src/index.css`：
  - 新增 `html:not(.dark)[data-palette="starry|sunflower|wave|mist|glaze"]` 与 `.dark[data-palette=...]` 变量块；
  - 玻璃主题：对侧栏、卡片、弹窗、顶栏加 `backdrop-filter: blur(18px) saturate(1.15)`、半透明背景、细边框；提供不支持 `backdrop-filter` 时的不透明回退；
  - 玻璃效果只在 `data-glass="true"` 下启用，不影响现有主题；
  - 所有颜色走令牌，不在组件里写死。
- 设置页主题选择自动读取 `PALETTES`/`PALETTE_PREVIEWS`；为 5 套补 `palette.<id>.name/description` 的 zh-CN/en-US 文案（玻璃主题标注「玻璃/高斯模糊」）。
- 验证：逐套亮/暗截图（设置页 + 仪表盘），对比度检查；玻璃主题在低端机/无 backdrop-filter 时可读。

### 2. 30 句每日健康名言

- 新建 `src/lib/quotes.ts`：30 条 `{ zh, en, author, source? }`。
  - 只用真实、广泛流传且可核实的句子；署名不确定时用「佚名 / Anonymous」，**不要编造出处**。
  - 主题偏人文关怀/健康/生活方式；可含希波克拉底、南丁格尔、奥斯勒、史怀哲等，但必须核实。
- 选择规则：按本地日期 `dayOfYear % 30` 选当天一句；同一天多次进入不变，跨天轮换。
- `src/pages/dashboard.tsx`：把「留一点时间，看看自己的心脏。记录与分析都保存在本地。」替换为：
  - 时间问候（已有 morning/afternoon/evening/night）；
  - 当天名言（中文界面 zh + 作者；英文界面 en + author）；
  - 保留数据/隐私提示（可放小字），不要堆两句长文案。
- i18n：新增 `dashboard.quote.*`（如 source line/无作者）与 5 套主题文案；英文界面用英文句子。
- 验证：跨天（改系统日期或 mock date）轮换正确；`zh-CN`/`en-US` 文案完整；截图亮/暗。

## 文件所有权（只改这些）

- `src/lib/theme.tsx`
- `src/lib/palettes.ts`
- `src/index.css`
- `src/lib/quotes.ts`（新建）
- `src/pages/dashboard.tsx`
- `src/lib/i18n/**`（只新增 palette/dashboard.quote 键）
- `reports/F2-*.md`、`reports/screenshots/F2-*.png`

## 明确不做

- 不改 `src/pages/settings.tsx`（F4 所有权；主题列表自动读取 `PALETTES`，无需改设置页结构）。
- 不改 branding/layout/icons（F1）、外部 API（F3/F4）。
- 不新增依赖；不改 `docs/`、`prompts/`、`uploads/`；不 commit。

## 验收

```powershell
npm run build
```

报告 `reports/F2-themes-quotes-report.md`，≤80 行：5 套变量、玻璃实现与回退、30 句来源核对方式、跨天验证、截图、未做项。
