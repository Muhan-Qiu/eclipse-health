# 报告 · F1 开屏 / Logo / 图标 / 导航转场 / 删副标题

状态：完成

## 交付

- `src/branding/branding.css`：重排开屏时间轴（1600ms，全 linear）；新增深绿涟漪常驻动画。
- `src/branding/SplashScreen.tsx`：主界面不再做入场淡入，遮罩退场即线性交叉溶解；`?splash=1` / `?splash=hold` 保留，新增 `&at=ms` 逐帧冻结（向后兼容）。
- `src/components/common/eclipse-mark.tsx`、`src/branding/Logo.tsx`：4 圈深绿同心圆环 + 中心点；`Wordmark` 默认不显示副标题。
- `src/components/layout/sidebar.tsx`：侧栏使用常驻涟漪 logo，删除「被忽视的健康」副标题；移除 sweep 起点记录。
- `src/components/layout/page-transition.tsx` + `page-transition.css`：纯交叉淡入淡出（新页 200ms / 旧页 180ms），双缓冲保留旧页；删除 clip-path sweep 与覆盖层。
- `src-tauri/icons/**`：全部 Windows PNG / ICO 替换为暖白底 + 深绿涟漪；`icon.ico` 含 16/24/32/48/64/128/256；`icon.icns` 按要求未动。

## 开屏时间轴（1600ms）

- 0–760ms：光晕、黑盘、光环依次就位（scale + opacity，linear）。
- 320–740ms：暗色字标淡入。
- 600–1100ms：亮色暖白幕布自下而上升起（只动 translateY）。
- 900–1240ms：亮色深色字标在幕布上淡入；日食盘与光环保持在幕布之上，不出现纯白空屏。
- 1240–1300ms：静止保持。
- 1300–1600ms：整层 300ms 线性淡出，主界面始终不透明地在其下方待命。
- 所有关键层仅动画 transform / opacity；`will-change` 已加在遮罩、幕布、光晕、盘、环、字标上；无 border-color / filter / box-shadow 逐帧动画。

## Logo / 图标

- 涟漪 logo：128 视口内半径 46/33/21/10、线宽 3.6/3/2.4/1.9；颜色 `color-mix(--eh-signal, --eh-text)`，亮色墨绿、暗色薄荷绿，无金色。
- 循环：10s linear infinite，四环延迟 0 / -2.5 / -5 / -7.5s，scale 1.24 → 0.64 + 透明度包络，呈「由外向内收」；`prefers-reduced-motion` 静止。
- 图标：暖白圆角方块 + 同款 4 环 + 中心点；≤24px 与 ≤48px 使用简化环宽，保证小尺寸可辨；背景非黑、无金环。

## 导航转场

- `useOutlet()` 取真实路由元素做双缓冲（不渲染 `<Outlet />` 占位符，否则旧层会跟着新路由重渲染）。
- 旧层绝对定位、`pointer-events:none`、`aria-hidden`、`inert`，只负责 180ms 淡出；新层 200ms 淡入；260ms 后卸载旧层。
- 侧栏在 main 之外，永不被覆盖；路由切换不阻塞；reduced-motion 直接切换、不保留旧层。

## 验证

- `npm run build`：通过，`tsc` 0 error，Vite built in 3.44s（最终一次 2.82s）。
- `npm run tauri build -- --no-bundle`：通过（exit 0，2m53s），成功读取新 `icon.ico` 并产出 `src-tauri/target/release/v3.exe`。
- 无头 Chrome CDP 实测（1440×900，生产构建）：
  - 开屏逐帧 `?splash=hold&at=`：亮色 350/700/950/1150/1300/1450ms、暗色 350/760/1100/1300/1450ms 均按预期线性推进。
  - 导航中帧：layers=2，旧层 450 字符（标题「晚上好」），旧/新 opacity 0.50/0.45；侧栏右缘 232 = main 左缘 232；body 背景 rgb(247,245,241)，无白屏、无覆盖侧栏。
  - 连续切换 records/health-data/profile/trends/reports：每次旧层均在（含旧标题），260ms 后只剩 1 层；随后 10 个页面 1.1s 稳态均有标题与内容，0 error。
  - `prefers-reduced-motion: reduce`：splash=0、涟漪 animation=none、页面淡入动画=0。
  - `?splash=1`：260ms 时遮罩存在，2060ms 时已移除；涟漪 10s / infinite；`?splash=hold` 冻结且 Esc 可关闭。
  - 全程 console error / exception 均为 0。
- 截图：
  - `reports/screenshots/F1-splash-light-frames.png`（6 帧）、`F1-splash-dark-frames.png`（5 帧）
  - `reports/screenshots/F1-logo-phases.png`（亮/暗 × 两个循环相位）
  - `reports/screenshots/F1-icons-preview.png`（暖白/暗色/中性底 + ICO 实际尺寸）
  - `reports/screenshots/F1-nav-before.png`、`F1-nav-mid.png`、`F1-nav-after.png`
  - 逐帧原图同目录 `F1-splash-*.png`、`F1-logo-*.png`。

## 未做 / 偏离

- 未运行完整 `tauri build` 打包（仅 `--no-bundle`），安装包未重打。
- `icon.icns` 保留旧文件（任务允许）；Android/iOS 图标未动，仅覆盖 Windows 图标。
- 开屏仍保留原金色日食（用户要求「保留日食」）；深绿只用于应用内 logo 与图标。
- `src/index.css` 中 `.eh-nav-sweep` 规则仍存在但已无任何 DOM 使用（F2 所有权，未删）；`markNavOrigin/consumeNavOrigin` 保留但无调用方。

## 跨区需求

- `index.html` / `public/brand/` 的 favicon、apple-touch-icon 仍是旧金色图标，不在 F1 所有权内，建议由对应 Agent 同步替换。
- `src/index.css` 的 `.eh-nav-sweep` 可在后续清理批次删除。
- `src/pages/settings.tsx` 的 About tagline 按任务要求未改（F4 范围）。

## 需要指挥官决策

- 开屏日食是否也改为深绿配色？当前按「保留日食」保持金色日冕。

## 建议下一批

- 所有 Agent 合并后重打安装包，并核对 Windows 任务栏/开始菜单实际图标效果。
- 替换 `public/brand/` 下的 favicon 与触控图标。
