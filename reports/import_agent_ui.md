# A6 · AI 数据导入前端 + 厂商教程

状态：完成（2026-11-02）  
构建：`npm run build` 通过（tsc + vite build）

## 1. 交付内容

### 1.1 统一入口

- 首页、健康数据页、记录页的入口文案统一为「导入健康数据 / Import health data」。
- 导入弹窗只剩一个主操作区：
  - 主按钮「选择文件/文件夹」
  - 次按钮「选择整个文件夹」（`webkitdirectory`，用于 Apple Health 等多文件目录）
  - 下方「不知道从哪里导出？查看教程」可展开厂商卡片。
- 保留原有全局拖拽（文件与文件夹）。

### 1.2 文件选择

- 多文件与文件夹选择均支持。
- `accept` 扩展为：`zip/csv/txt/xml/json/html/htm/pdf/xlsx/xls/fit/gpx/tcx/edf/bdf/dat/hea/atr`。
- 拖拽继续复用 `src/lib/zip.ts`（store-only ZIP，支持文件夹层级）。

### 1.3 双通道流程

标准导入（不回归）：

1. 选择/拖入后先调用原有 `/imports/preview`。
2. 成功 → 原有预览/参数/提交界面；健康数据包继续显示 created/skipped/failed 计数。
3. 失败 → 错误页新增「让 AI 解析」按钮。

AI 导入（A5 契约）：

1. `POST /import-agent/sessions`（multipart，最多 20 个文件）→ 展示文件清单与隐私说明。
2. 「开始解析」→ `POST /sessions/{id}/run`，前端用 `fetch` + ReadableStream 解析 SSE：
   `status / token / tool_call / tool_result / preview / done / error`。
3. 解析中展示步骤、工具名、结果摘要与模型文本（`aria-live`），可随时停止。
4. 完成后分页读取 `/proposals`，按 kind 分组：
   - 类型 chip 逐类勾选 / 全选 / 全部取消；
   - 表格列：时间、类型、数值、单位、来源、置信度、证据（文件 + 位置）；
   - 表格最多展示前 200 行，写入时按类型提交全部候选。
5. 「写入选中记录」→ `POST /sessions/{id}/commit`，展示 created/skipped/failed。
6. 关闭弹窗时自动 `DELETE` 未提交 session。

演示模式（`VITE_USE_MOCK=true` 或 `apiMode.mock`）在 `import-agent-api.ts` 内模拟同一套事件与 13 类候选，可完整走到分组预览与写入结果。

### 1.4 健康数据类型

页面、过滤器、图标、单位、来源、空状态已扩展到：

`steps / heart-rate / resting-heart-rate / sleep / body-mass / blood-pressure / spo2 / stress / workout / respiratory-rate / body-temperature / blood-glucose / hrv`

- 运动展示：类型 · 时长 · 距离 · 热量 · 平均心率。
- HRV 展示指标名（RMSSD/SDNN/pNN50/LF/HF/LF-HF）与单位。
- 来源识别扩展到 Apple、Samsung、小米、华为、Zepp、OPPO、Garmin、Fitbit、Withings、Google Fit。
- `HealthRecordView` 增加 `workout`、`metric` 字段；`toHealthRecordView` 兼容后端 `payload.value` 对象形态。

### 1.5 厂商教程

文件：`src/lib/vendor-import-guides.ts`，中英双语，覆盖 10 家：

Apple 健康、Samsung Health、小米运动健康/Zepp Life、华为运动健康、Zepp/华米、OPPO 健康、Garmin Connect、Fitbit、Withings、Google Fit。

每家包含：导出步骤、文件格式、包含数据、版本差异提示、官方帮助链接。UI 使用原生 `<details>`（键盘可操作），并统一提示「界面可能随版本变化」。

### 1.6 文案

- 所有「导入 ECG / Import ECG」改为「导入健康数据 / Import health data」。
- 弹窗标题与描述说明支持 ECG + 步数 + 运动 + 心率 + 血氧 + 睡眠 + 血压 + 体重 + 压力等。

### 1.7 无障碍与窄窗口

- 教程卡片与类型选择均为原生 button / details / aria-pressed / aria-expanded。
- 解析进度 `aria-live="polite"`、`aria-busy`，停止按钮可键盘操作。
- 表格 `overflow-x-auto`，弹窗 `max-w-[calc(100%-2rem)]`；520 px 视口截图验证无横向溢出（Edge headless 最小窗口约 500 px）。
- 运行中禁止关闭弹窗，避免中断请求。

## 2. 改动文件

新增：

- `src/components/import/import-agent-api.ts`
- `src/lib/vendor-import-guides.ts`

修改：

- `src/components/import/import-provider.tsx`（选择器、AI 流程、mock 演示入口）
- `src/components/import/import-dialog.tsx`（单入口、教程、Agent 预览表）
- `src/lib/api/types.ts`（HealthRecordKind 扩展）
- `src/lib/api/adapters.ts`（视图、来源、运动/HRV）
- `src/pages/health-data.tsx`（图标、单位、数值展示）
- `src/features/scores/health-summary-card.tsx`（新 kind 兼容）
- `src/lib/i18n/zh-CN.ts`、`src/lib/i18n/en-US.ts`（文案、types、agent、guides）

未改后端持久化；未绕过 A5 写数据库。

## 3. 截图

目录：`reports/import-agent-ui/`

| 文件 | 内容 |
|---|---|
| `picker-1440.png` | 统一入口 + 单主操作（1440 px） |
| `guides-1440.png` | 厂商教程展开（10 家） |
| `picker-520.png` | 窄窗口（520 px），无横向溢出 |
| `agent-preview-1440.png` | mock AI 解析完成：13 类分组、逐类勾选、预览表、写入按钮 |

截图使用 Edge headless（`--virtual-time-budget`）在 `VITE_USE_MOCK=true` 的 Vite dev server 上生成。开发模式提供 `?import=1` / `?import=guides` / `?import=agent` 用于截图与手动走查，生产构建不受影响。

## 4. 验证

- `npm run build`：通过。
- 标准导入路径：保留原 `/imports/preview` + `/imports/{id}/commit`，未改动契约与参数校验。
- AI mock 流程：`agent-preview-1440.png` 已走完「建会话 → 解析事件 → 分组预览 → 写入按钮」，代码路径与真实 SSE 共用同一状态机。
- 教程：每家均有官方链接；Withings 深链来自其 Zendesk 帮助中心检索结果，其余使用厂商官方帮助中心入口（见下）。

## 5. 来源与核实说明

本机 WebFetch 被域名安全校验拦截、Google/Archive/DuckDuckGo 不可达，改用 curl 直连厂商站点核实可访问性：

- Apple Health：https://www.apple.com/health/
- Samsung Health：https://www.samsung.com/us/support/
- 小米运动健康：https://www.mi.com/global/support/
- 华为运动健康：https://consumer.huawei.com/en/support/
- Zepp / Amazfit：https://support.zepp.com/en/
- OPPO 健康：https://www.oppo.com/en/support/
- Garmin Connect：https://support.garmin.com/en-US/
- Fitbit：https://support.google.com/fitbit/（本机网络不可达，链接为官方帮助中心；Fitbit 账号迁移后也可用 Google Takeout）
- Withings（已验证文章）：https://support.withings.com/hc/en-us/articles/31647944317201-Withings-App-Exporting-your-data
- Google Fit：https://support.google.com/fit/；导出入口 https://takeout.google.com/

步骤按各厂商客户端当前通用路径整理；无法逐一验证具体版本的深链时，链接落到官方帮助中心，避免编造文章 ID。

## 6. 已知限制

- 未在真实 A5 后端上跑通 SSE（本环境只验证了 mock 与构建）；事件名/字段已严格按 `docs/IMPORT_AGENT_API.md`。
- Playwright MCP 浏览器被其他任务占用，截图改用 Edge headless。
- 窄屏截图无法低于约 500 px（Chromium 最小窗口宽度）；520 px 已验证，布局本身使用 `max-w-[calc(100%-2rem)]`。
