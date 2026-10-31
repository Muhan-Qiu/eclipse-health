# 报告 · F2 主题扩展（3 高饱和 + 2 玻璃）+ 30 句每日健康名言

状态：完成

## 交付
- `src/lib/theme.tsx`：`PALETTES` 扩到 8 套（a/b/c + starry/sunflower/wave/mist/glaze）；新增 `isGlassPalette()`、上下文 `glass`，并在 `<html>` 上写 `data-glass="true"`（仅 mist/glaze）。
- `src/index.css`：5 套新配色各含亮/暗完整令牌（bg/bg-subtle/surface/surface-raised/hover/border/border-strong/text/text-muted/accent/accent-contrast/accent-soft/signal/danger/warning/success/info/chart-1..5/grid-line/shadow）。
- 玻璃层：仅 `html[data-glass="true"]` 生效；侧栏、顶栏、卡片、弹窗（dialog/alert-dialog/popover/dropdown）使用半透明表面 + `blur(18px) saturate(1.15)` + 细边框；背景加低强度径向色雾让模糊可见。
- 回退：`@supports not ((backdrop-filter…) or (-webkit-backdrop-filter…))` 下恢复不透明表面；已确认编译进 dist CSS。
- `src/lib/palettes.ts`：5 套各 5 色预览；设置页/命令面板无需改结构即可自动出现（已截图验证 8 套）。
- `src/lib/quotes.ts`（新建）：30 条 `{zh,en,author,authorEn,source?}`；`dayOfYear(date) % 30` 选择，按本地年月日计算，避开夏令时。
- `src/pages/dashboard.tsx`：页头改为「问候 → 当日名言（中文界面 zh+中文署名 / 英文界面 en+英文署名）→ 本地隐私提示（小字）」，保留日期；移除旧「留一点时间…」文案。
- i18n：`dashboard.description` 改为隐私提示，新增 `dashboard.quote.attribution/anonymous`；新增 `palette.starry/sunflower/wave/mist/glaze` 的 zh-CN/en-US 名称与描述，玻璃主题标注「玻璃 / 高斯模糊」。

## 验证
- 命令：`npm run build`
- 结果：pass；tsc + vite build，2853 modules，3.0–3.1s；仅有既有 chunk >500kB 提示。
- 对比度（WCAG 公式，5 套 × 亮/暗）：正文/背景 14.10–17.88:1，次要文字/背景 5.33–10.17:1，强调按钮文字 5.08–11.68:1，全部 ≥ AA 4.5。
- Chrome CDP（1440×1000，真实 Vite 页面）逐套检查 5 主题 × 亮/暗：
  - `data-palette` 与 `dark` 均正确；
  - 玻璃主题 `data-glass="true"`，卡片/侧栏/顶栏背景为半透明，`backdrop-filter: blur(18px) saturate(1.15)` 生效；
  - 高饱和主题无 `data-glass`、卡片不透明、无模糊，未影响莫奈三套。
- 名言：30 条，`missing=0`；同一天多次调用同一句（stable=true）；2026-10-31（day 304，index 4）为南丁格尔，2026-11-01（index 5）为奥斯勒，跨天已轮换；2026-01-30 与 2026-03-01（day 30/60）按 `%30` 回到同一句。
- 非法 palette：localStorage 写入 `bogus` 后回退 `a`，并回写 `a`；`data-glass` 正确移除。
- 英文界面：名言显示英文原文 + 英文署名，隐私提示为英文。
- 截图：`reports/screenshots/F2-{starry,sunflower,wave,mist,glaze}-{light,dark}-{dashboard,settings}.png` 共 20 张，另 `F2-mist-light-en-dashboard.png`。
- 控制台：F2 代码无 error/exception；仅设置页请求既有后端缺失路由 `/api/v1/external/keys` 返回 404（F3/F4 在途，非本批）。

## 未做 / 偏离
- 未改 `src/pages/settings.tsx`（按所有权由 F4 维护；已通过其 `PALETTES` / `PALETTE_PREVIEWS` 映射自动生效）。
- 未对既有 a/b/c 重复截图（CSS 未改，仅新增块）。
- 无 backdrop-filter 的回退通过 CSSOM/编译产物确认，未在真实低端 WebView 上实测。
- 30 句均取自公开、广泛流传文本；署名存疑者记为佚名，希波克拉底「适量营养与运动」句标注为 Attributed，未编造出处。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `index.html` 首帧内联脚本仍只认 `a/b/c`，刷新时新配色会先闪一帧 `a`，玻璃主题也会先以不透明渲染；需该文件所有者把 5 个新 ID 与 `data-glass` 纳入首帧脚本。
- 设置页（F4）请求 `/api/v1/external/keys` 在当前运行的后端返回 404；截图控制台因此有该网络错误，与本批无关。
- `src/lib/i18n/*` 有其他 Agent 并行新增键；本批键已保留且 build 通过，后续合并需注意不要覆盖。

## 需要指挥官决策
- 是否批准修改 `index.html` 首帧脚本，消除新主题刷新闪烁（本批无权修改）。
- 30 句名言是否需要在设置页提供「关闭每日名言」开关（当前无需求）。

## 建议下一批
- 在 1080/720 宽度与 `prefers-reduced-transparency` 下复核玻璃可读性。
- 为主题切换补一条视觉回归脚本（当前截图脚本为临时 CDP，未入库）。
