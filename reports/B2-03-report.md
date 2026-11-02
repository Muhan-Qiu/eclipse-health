# 报告 · B2-03 UI 端到端：记录详情 + 波形 + 分析结果

状态：完成

## 交付
- API 层：`src/lib/api/{client,contract,adapters,error,queries,types}.ts`。真实 API 为默认，`VITE_USE_MOCK=true` 才启用演示数据；统一 `ApiError`，仅网络错误自动重试；分析 1s 轮询，完成/失败即停。
- 记录库：真实分页（`limit/offset`）、时间筛选走 API、设备/标签当前页筛选、加载/空/错误重试、上一页/下一页。
- 记录详情：真实波形（uPlot）、按像素 min/max 降采样、滚轮缩放/拖拽平移/键盘、导联切换、R 峰竖线与异常标签、质量区段底色、点击 R 峰显示单搏四类概率；长记录默认展示前 12 秒，可一键看全记录。
- 分析面板：引擎状态（warming 禁用并显示原因）、开始/重新分析、阶段进度、摘要卡（HR/HRV/异常比例/质量）、测量值 + 问号解释与常见范围、置信度/导联/采样率提示、类比例条、模型卡、非诊断声明、失败 code + 重试。
- 导入：全局拖拽 + 按钮选择；多文件/文件夹在浏览器内打 store ZIP（无新依赖），支持 WFDB 目录、`.zip`、CSV；预览 2000 点、自动识别结果、`requires` 标注、参数校正（采样率/导联/单位/极性）、标签/备注/时间；提交后跳转详情；关闭/重选会丢弃临时会话。
- 仪表盘：最近记录、指标概览、最近波形均取真实数据；无分析/无记录回退空状态；mock 仅演示降级，真实数据不带“示例”标识。
- 全量 zh-CN/en-US i18n、颜色+图标+文字三重表达、减少动效、1080×700 无横向溢出；未新增依赖。

## 验证
- `npm run build` → pass；`tsc` 无错误；Vite 1.81s，JS 766.65 kB / gzip 246.86 kB（>500 kB 提示沿用基线）。
- 真实后端（临时 `EH_DATA_DIR`）+ Vite 1422 + Playwright 端到端：
  - CSV：上传 360 Hz 10s CSV → preview（3600 点、fs 359.971、MLII、requires.unit）→ commit → 详情画布正常。
  - WFDB：`backend/resources/samples/100.hea/.dat/.atr` 以 ZIP 和“多选三文件自动打包”两路导入 → preview 650,000 点 / 2274 参考 R 峰 / MLII+V5 / 30:05.6 → commit → 两导联均可切换读取。
  - 分析：引擎 `warming` 时按钮禁用并显示原因；`ready` 后点“开始分析” → 202 → 轮询 → 8585 ms 完成；真实 HR 75.47、RMSSD 66.65、N 99.87%、质量 100%、模型卡与警告均显示。
  - 仪表盘读取到该真实分析的心率/HRV/异常比例/质量。
  - 坏文件（PNG）→ `unsupported_format` 可读错误；无后端时记录页/仪表盘显示错误与重试。
  - mock 模式（`VITE_USE_MOCK=true`，1421）全链路回归，无 console error。
- 性能（本机）：仪表盘首条记录可见约 1.09s；650k 点 WFDB 波形画布约 0.38s（信号已返回后）。
- 截图：`reports/screenshots/B2-03-record-light.png`、`B2-03-analysis-light.png`、`B2-03-analysis-dark.png`、`B2-03-import-preview.png`（均为真实 MIT-BIH 100 数据；暗色为真实分析页）。

## 未做 / 偏离
- 记录列表的 `status` 只由 `signalIds` 推导为 ready/无信号；后端列表不返回分析状态，已分析/分析中仅在详情体现（避免 N+1）。
- 长记录默认前 12 秒视图，“查看完整记录”仍是一条 min/max 包络；节律条缩略导航/Overview 属 B3（B6）。
- 未实现 12 导联网格（B5）、波形 PNG（B7）、趋势/报告/LLM/模块安装（B3）。
- 分析摘要句按结构化字段在前端重新渲染 i18n，后端 `summary` 仅作兜底；测量标签同理由 code 翻译。
- mock 模式提交的记录也标“示例”，真实记录不加；已在真实数据截图中确认。
- 真实引擎本次预热 398.6s（B1 报告约 150s），UI 可等待；非前端问题。

## 跨区需求（需要别的 Agent 或指挥官处理）
- B2-01：`GET /engine` 预热实际约 398.6s（本次复现）；如需固定文案请同步更新 `message`。列表接口若想显示“已分析”，建议 `GET /records` 返回 `latestAnalysisStatus`（可选字段），否则前端只能保持 ready。
- B2-02：CSV 预览可能返回 `requires.unit=true` 与 `non_target_sampling_rate`；前端已处理。若后续支持单 `.hea` multipart（不带 dat）建议返回明确 `invalid_file` 提示，当前 UI 引导上传 `.zip` 或全选同目录文件。
- B2-04：未同时启动 Tauri；1420 的 Vite 已被其他会话占用，本批截图使用 1422。确认 `main.tsx`/branding 包裹 `<App/>` 后页面仍正常（本批未改这些文件）。

## 需要指挥官决策
- 长记录默认视图是否保持“前 12 秒 + 一键全览”，还是在 B3 直接做节律条 Overview。
- 记录列表是否需要“已分析/分析中”状态（会引入每行分析查询或后端字段）。
- 分析面板在 1080 宽度下信息密度是否合适；如需更宽，可把测量值移到波形下方全宽。

## 建议下一批
- B3：节律条缩略导航、心搏列表跳转、质量区段列表、波形 PNG、趋势页真实数据、报告 PDF/PNG；对 650k 点增加 overview 降采样缓存与波形分块加载。
- 路由级 `React.lazy` 降低 766 kB 首包（当前构建提示）。
- 导入参数面板增加 CSV `leadColumn/timeColumn` 选择（后端已支持，B3 UI 再接）。
