# H3–H7 · 30 个第三方模块适配包（5 个 Agent × 6 个）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CANDIDATES_30.md`、`docs/MODULE_CONTRACT_V2.md`、`prompts/40-module-author-template.md`、`modules/official/cardia`、`modules/demo.echo`。
> **思考强度：low。** 目标是一次性产出可安装的 `.ehmod` 源码包，不追求临床级效果。
> 每模块按 `docs/MODULE_CANDIDATES_30.md` 的编号领取；你只负责分配给你的 6 个。

## 通用要求

### 1. 目录与 manifest

每个模块放 `modules/official/<slug>/`：

```
modules/official/<slug>/
  module.json          # 严格符合 schemas/module.schema.json
  README.md            # 用途、上游仓库、适配说明、非诊断声明
  LICENSE              # 本适配层（GPL-3.0）或上游许可说明
  NOTICE               # 上游项目、SPDX、仓库 URL、原版权人
  src/main.py          # stdio JSON-RPC worker（参考 cardia / demo.echo）
  src/adapter.py       # 纯函数解析/映射，便于单测
```

- `id` 用 `docs/MODULE_CANDIDATES_30.md` 给出的 `io.github.<owner>.<name>`；`version` 0.1.0。
- `author`：双方共同作者（上游项目/作者 + eclipse health adapters）；`repository` 写上游 URL；`description` 明确「适配自 <repo>」。
- `license`：核心适配层 GPL-3.0；上游许可写进 NOTICE；不要改上游许可。
- `dependencies`：按候选表 **B** 类写 PEP 508 依赖（如 `pandas>=2.1,<3`）；E/P 类写 `[]`。不要新增核心 sidecar 依赖。
- `permissions` 最小化：只读数据用 `records:read`；需要网络才加 `network`；不要申请 `records:delete`/`ui:custom`。
- `contributes` 至少一类：`importFormats` / `models` / `recordTypes` / `exporters` / `tools` / `ui.widgets` / `ui.pages`。
- UI 只能使用现有受控类型：`stat|sparkline|list|progress|text`（H2 之后再加 bar/line/heatmap；本批不要用新类型，避免 schema 冲突）。
- 所有分析/建议输出加「非医疗器械，不用于诊断」。

### 2. Worker

- stdio JSON-RPC，方法至少：`health`、`warmup`（可空实现）、模块声明的方法（import/analyze/tool/page data）。
- 不复制上游源码；通过 `import <lib>` 或子进程 CLI 调用；依赖装进模块 venv（H1）。
- 大输出/波形走临时文件句柄；单次返回 ≤1MB；错误用 JSON-RPC error，带可读 message。
- 路径/编码兼容 Windows 中文路径；不写用户目录之外的文件。

### 3. 测试

- 每个模块新增 `backend/tests/modules/test_official_<slug>.py`：
  - 纯函数/adapter 单测优先（不依赖上游库）；
  - 需要上游库的用 `pytest.importorskip`；需要网络的标 `@pytest.mark.slow` 并默认 skip；
  - manifest 通过 `schemas/module.schema.json` 校验；
  - 至少一个成功路径 + 一个错误路径。
- 不要为了跑通而在核心 venv 里 pip install；缺依赖就 skip 并在报告写清。

### 4. 署名/许可

- `NOTICE` 必须含：上游仓库 URL、SPDX、原版权行（从上游 LICENSE 复制）、修改说明「adapted as eclipse health module」。
- 能用 curl 取上游 LICENSE 就放 `LICENSES/<slug>-upstream.txt`；取不到就在 NOTICE 写「上游许可见 URL」并标记。
- 不把上游 README/图片/数据集复制进仓库。

## 每个 Agent 的分配

- Agent H3：候选 **1–6**（NeuroKit2、HeartPy、hrv-analysis、pyhrv、BioSPPy、YASA）
- Agent H4：候选 **7–12**（fitdecode、python-fitparse、gpxpy、bleak、pydexcom、openfoodfacts-python）
- Agent H5：候选 **13–18**（python-fitbit、python-myfitnesspal、python_withings_api、BrainFlow、muselsl、OpenBCI_Python）
- Agent H6：候选 **19–24**（habitctl、jrnl、wfdb、pyedflib、healthkit-to-sqlite、python-garminconnect）
- Agent H7：候选 **25–30**（stravalib、uPlot、ECharts、Observable Plot、Tremor、react-activity-calendar）

### 关于 H7（25–30）

这些是 JS/React 图表库，不能引入第三方运行时。做法：

- 不 vendor 其源码；用**我们自己的声明式 widget** 表达同类能力（趋势线、柱状、热力图、KPI、时间线、分布），manifest 里写 `dashboard-widget` + `ui.widgets`，`description` 注明「inspired by <repo>」。
- 因此 H7 实际产出 6 个**官方原生 UI 模块**（不依赖上游代码，许可只需 MIT/Apache 参考声明）；不要尝试 iframe。
- 如果 H2 的 bar/line/heatmap 类型尚未落地，先用 `sparkline/list/stat/text` 组合，H2 完成后再扩展。

## 文件所有权（每个 Agent 只改自己的）

- `modules/official/<自己的 6 个 slug>/**`
- `backend/tests/modules/test_official_<自己的 6 个 slug>.py`
- `reports/H<3-7>-modules-report.md`
- 不修改核心 `backend/src/**`、`src/**`、`schemas/**`、`docs/`、`prompts/`、`uploads/`

## 明确不做

- 不安装/打包 30 个 `.ehmod` 到安装包；不提交上游代码/数据/权重。
- 不新增核心依赖；不改核心 API/UI。
- 不 git commit；每个 Agent 写自己的报告（≤80 行，列出 6 个模块、依赖、测试、许可、未做项）。
