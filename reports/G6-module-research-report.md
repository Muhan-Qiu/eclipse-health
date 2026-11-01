# 报告 · G6 第三方健康模块调研（30 个候选）

状态：完成

## 交付
- `docs/MODULE_CANDIDATES_30.md`：6 类 × 5 个候选的完整表（仓库、SPDX、星数、语言、用途、模块类型/ID、适配方式、UI 贡献、工作量、风险），附依赖矩阵、Top 10、5 个拒绝样例、署名清单、待决策项。
- `reports/G6-module-research-report.md`：本报告。
- 未写业务代码，未 clone 大仓库，未下载受限数据，未 commit。

## 验证
- 命令：`curl https://api.github.com/repos/<owner>/<repo>` × 35（匿名配额 60/h）；`curl https://pypi.org/pypi/<pkg>/json` × 23；`curl raw.githubusercontent.com/.../LICENSE` 人工核对 8 个仓库。
- 结果：30 个候选 + 5 个拒绝样例全部拿到 SPDX/星数/语言/最近推送；无候选许可不明。
- 许可分布：MIT 15、Apache-2.0 6、BSD-3-Clause 5、GPL-3.0 2（hrv-analysis、jrnl）、GPL-2.0-or-later 1（habitctl）、ISC 1；均满足「宽松或 GPL-3.0 兼容」。
- 依赖判定：E（现有 venv）3 个；P/P-M（纯 Python/stdlib）4 个；B（模块独立 venv）18 个；N/A（JS 资产）5 个。
- 修正：`neuropsychology/NeuroKit2` 已更名 `NeuroKit`；`biosppy/biosppy` 实为 `scientisst/BioSPPy`；`orcasgit/python-withings` 已迁至 `python-nokia` 且停更，改用 `vangorra/python_withings_api`（MIT/111★）。
- 许可人工核对：openfoodfacts-python（REUSE `LICENSES/MIT.txt`→MIT）、python-fitbit（Apache-2.0 正文）、BrainFlow（MIT）、BioSPPy（BSD-3 正文）、habitctl（README GPLv2+）、myfitnesspal（MIT）；Habitica 为 NOASSERTION，归入拒绝。

## 未做 / 偏离
- 未安装/运行任何候选，未验证 B 类依赖在 Windows Py3.12 的实际可安装性（按任务「不写代码」）。
- 未逐个阅读源码，适配方式基于 README/包元数据与公开 API 推断；落地前需 spike 验证。
- 星数为 2026-11-01 快照；许可证可能随上游更新变化，安装时应按 commit 复核。
- UI 类 5 个库不是「模块」本身，只能作为核心渲染器或 v1 `ui:custom` iframe 资源，已在文档中标注。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 模块契约：v2 §1 明确「禁止 iframe」，但 UI/可视化类模块需要 iframe 沙箱或核心内置渲染器；需在契约层给出结论。
- manifest：建议增加 `upstream {url, commit, license}` 字段，便于自动署名、许可扫描与升级核对（当前 `author`/`repository` 不足以表达上游）。
- 注册表扫描：B 类模块依赖需联网装包，索引扫描需定义依赖白名单/哈希锁定策略。
- 法务：Open Food Facts 数据 ODbL 的署名与同源义务需产品文案配合。

## 需要指挥官决策
1. UI 类库走 v1 沙箱 iframe，还是只允许核心内置？若禁止 iframe，5 个 UI 候选全部降级为「核心依赖」而非模块。
2. 非官方 API（Garmin/Dexcom/MyFitnessPal）是否允许进入官方索引，还是只进社区索引并强制风险标注？
3. 是否接受「每模块独立 venv + 安装时联网」作为 B 类依赖标准路径，并允许模块声明 pip 依赖与锁文件？
4. 是否把 GPL-3.0/GPL-2.0-or-later 模块（hrv-analysis、jrnl、habitctl）纳入官方索引（进程隔离下法律风险可接受，但需统一声明）。

## 建议下一批
- 先做 4 个薄适配 spike（不写正式代码）：NeuroKit2（E/S）、HeartPy（E/S）、fitdecode（P/S）、gpxpy（P/S），验证 stdio RPC + 临时文件句柄模式。
- 再做导出双件套：wfdb（E/S）+ pyedflib（B/S），验证 WFDB/EDF 往返。
- 建立 `licenses/<module-id>/` 模板与自动许可扫描（SPDX + NOTICE + upstream commit）。
- 数据源按风险排序试点：openfoodfacts → fitbit/withings → garminconnect/pydexcom；MyFitnessPal 暂缓。
