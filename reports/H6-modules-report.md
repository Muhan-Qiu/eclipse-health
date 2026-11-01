# 报告 · H6 第三方模块适配包（候选 19–24）
状态：完成

## 交付

| # | 目录 | 模块 ID | 类型 | 依赖 | 主要方法 / 贡献 |
|---|---|---|---|---|---|
| 19 | `modules/official/habitctl` | io.github.blinry.habitctl | health-domain | 无（Rust CLI 子进程） | habits.list/summary/form/log；recordType habit.log、页面、连续天数 widget |
| 20 | `modules/official/jrnl` | io.github.jrnl-org.jrnl | health-domain | jrnl>=4.0,<5 | journal.list/get/summary/search；recordType journal.entry、页面、LLM 工具 journal.search |
| 21 | `modules/official/wfdb` | io.github.mit-lcp.wfdb | exporter | 无（核心 venv 已装） | export.wfdb/export.csv/import.wfdb；importFormats、csv exporter |
| 22 | `modules/official/pyedflib` | io.github.holgern.pyedflib | exporter | pyedflib>=0.1.38,<1 | export.edf/export.csv/import.edf；importFormats、csv exporter |
| 23 | `modules/official/healthkit-to-sqlite` | io.github.dogsheep.healthkit-to-sqlite | data-source | 无（纯 stdlib） | import.healthkit/summary；sources、importFormats、4 个 recordTypes |
| 24 | `modules/official/garminconnect` | io.github.cyberjunky.garminconnect | data-source | garminconnect>=0.2,<1、curl_cffi>=0.7,<1 | import.garmin/summary；network + allowedHosts、3 个 recordTypes、widget/页面 |

每个模块含 `module.json`、`README.md`、`LICENSE`（适配层 GPL-3.0-only）、`NOTICE`
（上游 URL/SPDX/版权/修改说明/非背书）、`src/main.py`（stdio JSON-RPC）、`src/adapter.py`
（纯函数），以及打包生成的 `checksums.json`。全部输出带「非医疗器械，不用于诊断」。

## 验证

- 命令：`backend\.venv\Scripts\python.exe -m pytest <6 个 test_official_*.py> -q`
- 结果：**45 passed, 0 failed, 0 skipped，约 0.7s**；覆盖成功路径、非法参数、空/缺失上游。
- manifest：6/6 通过 `schemas/module.schema.json`（Draft 2020-12）与核心 `parse_manifest`；
  `dependencies`、`allowedHosts` 均已被当前 schema 与 Manifest 模型接受（无需挂起）。
- ruff：6 个模块目录 + 6 个测试文件 `All checks passed`。
- 打包：`scripts/pack_demo.py` 6/6 打包成功，checksums 与 layout 校验通过；临时目录产物已清理。
- worker 冒烟：6 个 `main.py` 各喂 `initialize/health/deactivate`，均返回 result 并正常退出。
- wfdb 往返实测通过（`export.wfdb` 写 .hea/.dat → `import.wfdb` 读回 4 样本）。

## 未做 / 偏离

- 核心 venv 未安装 `pyedflib`、`garminconnect`、`curl_cffi`（遵守不 pip install 约束）。
  EDF 往返与 Garmin 登录未实测；测试覆盖 `upstream_unavailable` 与参数错误路径。
- `habitctl`、`jrnl` 上游 CLI 不在 PATH，子进程主路径未实测；用 `params.text` 覆盖解析/搜索。
- schema 的 `exporter.format` 枚举无 `wfdb`/`edf`：两个导出器用 `csv` 贡献点 + RPC 原生导出表达，
  README 已标注限制；未伪造枚举值。
- 未联网取上游 LICENSE 全文：`NOTICE` 写明许可 URL 并标记「未内置」，未复制上游 README/数据。
- `garminconnect` 的离线 JSON 导入格式只声明了扩展名，未实现离线解析（候选表也未要求）。
- 未新增核心依赖，未改 `backend/src`、`src`、`schemas`、`docs`、`prompts`、`uploads`，未 commit。

## 跨区需求（需别的 Agent / 指挥官）

- `schemas/module.schema.json` 的 exporter `format` 若长期无 wfdb/edf，原生医疗格式只能走 RPC；
  建议扩展枚举或允许 `custom:<name>`。
- 工具 `id` → RPC `method` 的映射未在文档明确；`journal.search` 按 id 同名方法实现。
- B 类模块的 venv 安装链路（H1）尚未在真实安装流程中跑通，本批只做源码包。

## 需要指挥官决策

- 非官方 Garmin API 是否进入官方索引（ToS/2FA/风控风险），还是仅社区索引并显著标注。
- 是否接受 `checksums.json` 随源码目录提交（当前由 `pack_demo.py` 生成，已排除 `__pycache__`）。

## 建议下一批

- 在模块独立 venv 中实装 `pyedflib` / `garminconnect`，补 EDF 与 Garmin 的真实/离线往返测试。
- 为 habitctl/jrnl 提供测试桩二进制或固定输出样本，覆盖子进程主路径。
- 等 H2 的 bar/line/heatmap 组件落地后，丰富习惯与活动的趋势面板。
