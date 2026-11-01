# 报告 · H4 第三方模块适配包（候选 7–12）

状态：部分完成（6 个模块全部交付；核心 venv 未装上游库，依赖路径只验证到“缺依赖错误”）

## 交付

| # | 模块 slug / ID | 类型 | 依赖 | 贡献点 |
|---|---|---|---|---|
| 7 | `fitdecode` / `io.github.polyvertex.fitdecode` | device-adapter | `fitdecode>=0.10,<1` | importFormats(.fit)、activity.session、widget |
| 8 | `fitparse` / `io.github.dtcooper.fitparse` | device-adapter | `fitparse>=1.2,<2` | importFormats(.fit)、activity.session、widget |
| 9 | `gpxpy` / `io.github.tkrajina.gpxpy` | device-adapter | `gpxpy>=1.6,<2` | importFormats(.gpx)、activity.session、widget |
| 10 | `bleak` / `io.github.hbldh.bleak` | device-adapter | `bleak>=0.22,<2` | importFormats(ble-capture json)、hr.sample、weight、widget |
| 11 | `pydexcom` / `io.github.gagebenne.pydexcom` | device-adapter | `pydexcom>=0.4,<1` | importFormats(dexcom-share json)、glucose.reading、widget |
| 12 | `openfoodfacts` / `io.github.openfoodfacts.openfoodfacts` | data-source | `openfoodfacts>=1.0,<2` | sources、nutrition.entry、tool `food.lookup`、widget、page |

每个模块均含 `module.json`、`README.md`、`LICENSE`（GPL-3.0-only 声明）、`NOTICE`、
`src/main.py`（stdio JSON-RPC：initialize/warmup/health/deactivate + 业务方法）、
`src/adapter.py`（纯函数解析/映射）。`gpxpy` 额外带 `LICENSES/gpxpy-upstream.txt`。

## 验证

- manifest：6 个全部通过 `schemas/module.schema.json`（Draft202012Validator），并通过核心
  `load_manifest_file()` + `check_compatibility()`；`dependencies` 已被现有 schema/Manifest 接受。
- 测试：`backend/.venv/Scripts/python.exe -m pytest <6 个 test_official_*.py> -o addopts="" -q`
  → **52 passed in 0.19s**。
- ruff：`python -m ruff check <6 个模块目录 + 6 个测试文件>` → **All checks passed!**
- stdio 冒烟：`gpxpy`、`openfoodfacts` 的 initialize/health/latestProduct/deactivate 返回合法 JSON。
- 测试覆盖：manifest 校验、adapter 成功路径、非法输入（空列表/坏字节/坏条码/缺凭据）、
  worker initialize/health 与错误码 `INVALID_INPUT`。

## 未做 / 偏离

- 上游库（fitdecode/fitparse/gpxpy/bleak/pydexcom/openfoodfacts）均未装入核心 venv，遵守
  “不得 pip install”；真实文件/设备/网络解析路径未执行，缺依赖时统一返回 `DEPENDENCY_MISSING`。
- 上游 LICENSE 仅 gpxpy 成功下载；其余 5 个网络超时，NOTICE 标注“上游许可见 URL / pending”，
  发布前需补 `LICENSES/<slug>-upstream.txt`。
- `LICENSE` 为 SPDX 声明 + GPL 全文 URL，未内联约 35KB 全文；建议打包脚本统一注入。
- `gpxpy` 的 `exporters` 贡献未写：schema 的 `exporter.format` 枚举只有 pdf/png/csv/svg/fhir-json，
  不含 `gpx`；导出暂只经 RPC `exportGpx` 暴露。
- `bleak`/`pydexcom` 是设备适配但没有文件格式；因 schema 强制 device-adapter 必须有
  `importFormats`，二者声明了 `json` 离线采集/回放格式，README 已说明。
- 首页 widget 依赖 Stage B 数据通道；当前 `latest*` 方法返回本进程最近一次结果或空占位。
- 未生成 `checksums.json` / `.ehmod`（H 提示词不要求打包；由打包批次处理）。

## 跨区需求（需要别的 Agent 或指挥官处理）

- 核心模块安装/打包：为 6 个模块创建独立 venv 并安装锁定依赖（H1 路径），再跑上游真实数据。
- Stage B：实现 widget/page 的 module-rpc 数据通道；当前只声明贡献、不执行。
- schema（若后续要注册 GPX 导出）：`exporter.format` 增加 `gpx`；本 Agent 未改 schema。
- 上游 LICENSE 补齐：fitdecode / fitparse / bleak / pydexcom / openfoodfacts。

## 需要指挥官决策

- pydexcom 使用非官方 Dexcom Share API：是否进入官方索引，还是仅社区索引并显著标注风控风险。
- `bleak`/`pydexcom` 的 JSON 导入格式是否可接受；若不可，需为设备适配放宽“必须有 importFormats”。

## 建议下一批

- 安装 6 个模块 venv，用 MIT-BIH 以外的真实 `.fit`/`.gpx` 样本与 BLE 设备做集成测试。
- 打包 `.ehmod` 时自动生成 checksums、注入 GPL 全文与上游 LICENSE。
