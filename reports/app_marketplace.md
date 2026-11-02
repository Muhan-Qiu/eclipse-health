# A3 · 应用内模块市场对齐网站

日期：2026-11-01
分支：`feat/ui-alignment`
范围：`src/features/modules/` 下的市场、安装弹窗、模块详情与已安装模块列表。

## 结论

应用内模块市场已与 `eclipse-health.fit` 的 `module-copy.zh.json` / `module-copy.en.json` 对齐：

- 中英文名称、一句话 tagline、功能清单、怎么用、输入/输出、适合、限制、技术说明均按当前语言显示。
- 首页卡片排序与网站一致：官方自研 → 已验证 → 本地化名称；官方自研内部保持 ECG 在前、睡眠在后。
- 搜索覆盖名称、ID、作者、tagline、features（同时保留 description/summary/usage 等命中）。
- 官方/社区来源完全来自市场索引与当前 tab，没有硬编码；社区模块继续显示“未审核”。
- 详情保留权限、依赖、许可证，并新增 sha256 与扫描结果展示；新增网站文档链接。

## 改动

| 文件 | 内容 |
|---|---|
| `src/features/modules/copy/module-copy.zh.json` | 网站中文文案原样复制，随 Vite 打包 |
| `src/features/modules/copy/module-copy.en.json` | 网站英文文案原样复制，随 Vite 打包 |
| `src/features/modules/copy/index.ts` | copy 类型、按语言/ID 查找、官方自研判断、搜索与排序、网站链接 |
| `src/features/modules/marketplace/marketplace-panel.tsx` | 卡片使用 copy 名称/tagline/功能；客户端搜索与排序；官方自研徽标；结果数量 |
| `src/features/modules/marketplace/module-detail-dialog.tsx` | 详情使用 copy 全量维度；新增 sha256、扫描结果、网站文档链接；官方自研徽标 |
| `src/features/modules/marketplace/api.ts` | 支持索引中的 `scan` 字段；索引查询不再把关键词发给后端（搜索改在本地完成） |
| `src/features/modules/marketplace/types.ts` | 新增 `MarketplaceScan` 类型与 `scan` 字段 |
| `src/features/modules/module-list.tsx` | 已安装列表按当前语言显示 copy 名称，并标注官方自研 |
| `src/features/modules/module-detail.tsx` | 已安装详情显示本地化名称/summary、官方自研徽标与网站文档链接 |
| `src/features/modules/i18n.ts` | 新增中英文市场文案键（官方自研、功能/用法/输入/输出/适合/限制/技术说明、sha256、扫描、网站文档、结果数量） |
| `src/features/modules/install-dialog.tsx` | 修正弹窗宽度（`sm:max-w-4xl`），避免卡片名称在桌面端被压缩截断 |

未改动：安装/校验/签名逻辑、模块 manifest、任何网络请求。文案 JSON 随打包进入应用，不联网加载。

## 验收结果

| 项 | 结果 |
|---|---|
| 官方数量与索引一致 | 应用 32 / 官方索引 32 |
| 社区数量与索引一致 | 应用 0 / 社区索引 0（当前社区索引为空） |
| 中文名称与网站一致 | 32 个模块名称逐项来自网站 `module-copy.zh.json` |
| 英文名称与网站一致 | 32 个模块名称逐项来自网站 `module-copy.en.json` |
| 无 copy 的模块回退 | `getModuleCopy` 返回空时回退索引 `name`/`description`，其余维度不渲染 |
| 搜索 | 中文“睡眠”命中 8 个模块，包含 tagline/features 命中的 `日记与心情`、`习惯追踪` 等 |
| 排序 | 两个 `org.eclipsehealth.*` 置顶（ECG → 睡眠），其余按已验证 + 本地化名称 |
| 官网链接 | `https://eclipse-health.fit/modules.html?module=org.eclipsehealth.relay-ecg` |
| `npm run build` | 通过 |

说明：当前索引没有 `scan` 数据，因此详情中暂不出现扫描行；一旦索引提供 `scan.status/risk/scannedAt/reportUrl`，详情会自动展示。扫描结果展示不改变安装与签名校验逻辑。

## 截图

目录：`reports/app-marketplace/`

- `01-zh-official.png`：中文官方市场，32 个模块，官方自研徽标与网站文案
- `02-zh-detail-ecg.png`：中文 ECG 详情顶部（tagline、summary、事实、sha256、官网链接、功能清单）
- `02b-zh-detail-ecg-sections.png`：详情下半部分（怎么用、输入/输出、适合、限制、技术说明、权限、依赖）
- `03-zh-search-sleep.png`：搜索“睡眠”的结果
- `04-zh-community.png`：社区市场，0 个模块（与索引一致）及“未审核”提示
- `05-en-official.png`：英文官方市场，名称与 tagline 来自英文 copy
- `06-en-detail-ecg.png`：英文 ECG 详情
- `capture-summary.json`：截图时采集的数量、顺序、搜索与链接校验数据

## 冲突说明

工作期间其他 agent 同时修改了 `install-dialog.tsx` 的弹窗宽度类名，桌面端会回落到 `sm:max-w-sm`，导致市场卡片名称被截断。本次将其改为 `w-[calc(100%-2rem)] sm:max-w-4xl`，仅影响布局，不涉及安装逻辑。
