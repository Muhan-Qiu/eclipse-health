# V4.5 问题清单（BUGS）

状态图例：`FIXED` 已修复待验证 / `DONE` 已验证。本版所有条目均有自动化或接口级验证。

---

## BUG-501 健康评分显示「缺数据：unknown、unknown、unknown、unknown」

- **状态**：`DONE`
- **优先级**：P0
- **现象**：仪表盘「健康评分」底部显示四个 `unknown`，而不是「睡眠、体重、活动、血压」。
- **根因**：
  - 后端 `scoring/models.py::ScoreReport.missing` 是 `list[str]`，返回分类显示名（`["睡眠","体重","活动","血压"]`），并在 `docs/SCORING.md` 中明确。
  - 前端 `src/lib/api/adapters.ts::normalizeMissingScore` 把它当对象解析 `{id, reason}`，字符串被 `asObject` 丢弃后回退成 `id: "unknown"`。
  - `HealthScores.missing` 类型也错误地写成 `MissingScore[]`。
- **修复**：
  - `types.ts`：`HealthScores.missing` / `ScoreCategory.missing` 改为 `string[]`，删除 `MissingScore`。
  - `adapters.ts`：新增 `normalizeStringList`，兼容旧字符串与数组；新增 `normalizeCategoryId`，统一 `blood_pressure` → `blood-pressure`。
  - `health-score-grid.tsx`：按 id 翻译缺失分类，并为五项都渲染瓦片（缺失项虚线 + 「数据不足」）。
- **验证**：真实 `/scores` 响应显示「睡眠、体重、活动、血压」；`pytest backend/tests/scoring` 通过；浏览器截图确认。

---

## BUG-502 Windows 上带 ONNX 权重的模块安装失败（INVALID_PACKAGE）

- **状态**：`DONE`
- **优先级**：P0
- **现象**：从模块中心或 `POST /modules/install-upload` 安装 `org.eclipsehealth.relay-ecg-0.1.0.ehmod` 返回 `422 INVALID_PACKAGE` / 「模块包安装失败」；同包 `check-module-package.mjs` 校验通过。
- **根因**：
  - `modules/manager.py::ModuleManager.install()` 解压到 `.staging/<uuid>` 后调用 `staging.replace(target)`（即 `os.replace` 重命名整个目录）。
  - 在 Windows 上，当目录中包含刚写入的大体积模型权重（本包约 46 MB）时，目录级重命名会被文件系统/索引/安全扫描短暂占用，稳定返回 `PermissionError [WinError 5]`，被包装成 `INVALID_PACKAGE`。
  - 逐文件移动、单个子目录（<14 MB）移动、项目外路径移动均正常，确认是“大目录整体 rename”触发。
- **修复**：
  - 新增 `_move_tree()`：递归创建目标目录、逐文件 `os.replace`（带 5 次退避重试），最后删除空 staging；替换原来的目录 rename。
  - 注册失败时仍回滚目标目录，行为不变。
  - 新增回归测试 `backend/tests/modules/test_manager_move_tree.py`。
- **验证**：
  - 通过 API 安装 relay-ecg 成功（`200`，模块 `enabled`）。
  - 用 relay-k2 对 30 分钟 MIT-BIH 记录发起分析，`completed`，输出心率/HRV/比例/质量与 5 条警告。
  - 32 个 `.ehmod` 包 `check:packages` 全部通过。

---

## BUG-503 英文界面出现中文评分因子与建议

- **状态**：`DONE`
- **优先级**：P1
- **现象**：切换到 English 后，仪表盘健康评分因子、缺数据项、建议卡片仍是中文。
- **根因**：评分与建议文案在后端 `scoring/service.py`、`scoring/suggestions.py` 中硬编码中文，API 没有语言参数。
- **修复**：
  - `/scores`、`/suggestions` 新增可选 `lang=zh|en`（默认 zh，响应结构不变）。
  - 分类标签、因子、缺失项、免责声明、建议 text/prompt 均有 zh/en 模板。
  - 前端 `useHealthScores` / `useHealthSuggestions` 传当前语言，queryKey 带语言，切换语言即重新拉取。
  - 新增 `backend/tests/scoring/test_scoring_i18n.py`，断言英文响应不含 CJK。
- **验证**：`pytest backend/tests/scoring` 14 passed；英文仪表盘截图无中文评分/建议。

---

## BUG-504 导入警告缺少本地化，英文界面回退到中文长句

- **状态**：`DONE`
- **优先级**：P2
- **现象**：Apple / Samsung / SCP / EDF 等导入警告在英文界面显示后端中文原文；部分警告 code 没有翻译键。
- **根因**：`imports.warningCodes` 只覆盖 24 个 code，后端实际会产出 46+ 个。
- **修复**：补齐 `unit_inferred`、`experimental_format`、`scp_huffman`、`scp_difference_encoding`、`start_time_invalid`、`time_not_monotonic`、`truncated_file`、`channel_*`、`pointer_*`、`samsung_*`、`unit_*` 等 23 个中英文案。
- **验证**：Apple ECG CSV 预览在中文/英文下均显示本地化警告；`check-encoding` 0 错误。

---

## BUG-505 开发模式 Geist 字体 403

- **状态**：`DONE`
- **优先级**：P3
- **现象**：`npm run dev` 时 `@fontsource-variable/geist` 的 woff2 请求返回 403，界面回退到系统字体。
- **根因**：开发机的 `node_modules` 是目录联接（junction），真实路径在项目外；Vite 8 默认只允许工作区根内文件。
- **修复**：`vite.config.ts` 的 `server.fs.allow` 加入项目根与 `node_modules` 的 `realpathSync` 结果。
- **验证**：dev server 控制台无 403，字体正常加载。

---

## BUG-506 中英文模块名与工作台文案混排

- **状态**：`DONE`
- **优先级**：P2
- **现象**：中文界面的 Cardia 工作台显示英文 description；英文界面的模块卡片标题/空状态仍是中文。
- **根因**：工作台直接用 manifest 的 `name/description`；模块文案 `module-copy.*.json` 只用于市场/侧栏，且没有 Cardia 与 widget 标题。
- **修复**：
  - 补齐 Cardia 与 Relay 的中英文 copy（名称、简介、功能、限制、技术说明、widget 标题）。
  - 工作台标题/简介、模块列表/详情、卡片标题统一走 `moduleDisplayName` / `getModuleCopy`。
  - 英文界面下模块返回的纯中文文本用通用「No data」占位，避免中英混排。
- **验证**：中英文工作台、模块中心、仪表盘模块卡片截图确认。

---

## 回滚点

- V4.3 工作树：`V4.3/` 原目录未改动；另见 `V4.5-backup-*.zip`。
- Git：V4.5 分支从 V4.3 基线提交 `209ad4f` 开始，每个修复单独提交。
