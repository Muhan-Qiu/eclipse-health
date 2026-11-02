# 模块审计与官方/社区分家报告

生成时间：2026-11-01T15:14:51Z　审计环境：Python 3.12.7，依赖模式 `install`

## 结论

- 官方索引：**10** 个市场模块（另有 Cardia 随安装包内置，不进入市场索引）。
- 社区索引：**22** 个模块，`verified=false`，与官方同样签名。
- 冒烟：pass 17 / partial 3 / skipped 12 / fail 1；总计 33（含 Cardia）。
- 模块 ID、版本、`.ehmod` 文件名全部不变；两个索引均用现有开发密钥 `dev-2026` 重签。

## 官方保留（10）

- `io.github.aura-healthcare.hrv-analysis` — 无外部账号的 HRV 分析
- `io.github.dogsheep.healthkit-to-sqlite` — 本地 Apple Health 导出导入，无账号
- `io.github.holgern.pyedflib` — EDF 导入/导出，临床与穿戴设备通用格式
- `io.github.mit-lcp.wfdb` — WFDB 导入/导出，心电数据的标准交换格式
- `io.github.neuropsychology.neurokit2` — 无外部账号的通用生理信号分析
- `io.github.paulvangentcom.heartpy` — 无外部账号的 HRV/PPG 分析
- `io.github.scientisst.biosppy` — 无外部账号的生理信号分析
- `io.github.tkrajina.gpxpy` — 本地 GPX 轨迹导入，无账号、可离线验证
- `org.eclipsehealth.relay-ecg` — 第一方 ECG 模型包，核心分析闭环
- `org.eclipsehealth.relay-sleep` — 第一方睡眠模型包，核心分析闭环

## 移入社区（22）

- `io.github.alexandrebarachant.muselsl` — 需要 Muse 头环与 LSL 环境，无法在审计中验证
- `io.github.apache.echarts` — 可选图表组件，不属于核心健康闭环
- `io.github.blinry.habitctl` — 主路径依赖外部 habitctl 可执行文件，非 Python 依赖
- `io.github.brainflow-dev.brainflow` — 需要 BrainFlow 支持的采集硬件，无法在审计中验证
- `io.github.coddingtonbear.myfitnesspal` — 需要 MyFitnessPal 账号，依赖 cloudscraper 抓取，上游脆弱
- `io.github.cyberjunky.garminconnect` — 需要 Garmin 账号登录，且为受 TOS 约束的非官方客户端
- `io.github.dtcooper.fitparse` — 可选的 FIT 文件导入，与 fitdecode 功能重复
- `io.github.gagebenne.pydexcom` — 需要 Dexcom Share 账号与实时网络
- `io.github.grubersjoe.activity-calendar` — 可选仪表盘组件，不属于核心健康闭环
- `io.github.hbldh.bleak` — 需要 BLE 硬件与现场蓝牙环境，无法在审计中验证
- `io.github.jrnl-org.jrnl` — 主路径依赖外部 jrnl CLI，非 Python 依赖
- `io.github.leeoniya.uplot` — 可选图表组件，不属于核心健康闭环
- `io.github.observablehq.plot` — 可选图表组件，不属于核心健康闭环
- `io.github.openbci-archive.openbci` — 需要 OpenBCI 串口硬件，无法在审计中验证
- `io.github.openfoodfacts.openfoodfacts` — 依赖实时 Open Food Facts 网络查询，离线无法验证
- `io.github.orcasgit.fitbit` — 需要 Fitbit OAuth 账号与令牌
- `io.github.pgomes92.pyhrv` — 上游 pyhrv 返回 ReturnTuple，模块适配层未兼容，hrv.metrics 无法通过冒烟
- `io.github.polyvertex.fitdecode` — 可选的 FIT 文件导入，与 fitparse 功能重复
- `io.github.raphaelvallat.yasa` — worker 最小环境未提供 HOME/USERPROFILE，yasa/mne 启动报 FileNotFoundError
- `io.github.stravalib.stravalib` — 需要 Strava OAuth 账号与令牌
- `io.github.tremorlabs.tremor` — 可选仪表盘组件，不属于核心健康闭环
- `io.github.vangorra.withings` — 需要 Withings OAuth 账号与令牌

## 完整矩阵

| 模块 ID | 类型 | 来源 | 权限 | 外部依赖 | 测试深度 | 冒烟 |
|---|---|---|---|---|---|---|
| `io.github.alexandrebarachant.muselsl` | device-adapter | community | files:user-selected, records:write | 硬件, Python 依赖 | manifest-only | skipped（requires-hardware） |
| `io.github.apache.echarts` | dashboard-widget | community | records:read | - | adapter+rpc | pass · chart.line |
| `io.github.aura-healthcare.hrv-analysis` | analysis-model | official | records:read, llm | Python 依赖 | manifest-only | pass · hrv.frequency |
| `io.github.blinry.habitctl` | health-domain | community | records:read, records:write | 外部 CLI | adapter+rpc | pass · habits.list |
| `io.github.brainflow-dev.brainflow` | device-adapter | community | files:user-selected, records:write | 硬件, Python 依赖 | manifest-only | skipped（requires-hardware） |
| `io.github.coddingtonbear.myfitnesspal` | data-source | community | network, records:write | 账号/OAuth, 网络, Python 依赖 | manifest-only | skipped（requires-account-oauth） |
| `io.github.cyberjunky.garminconnect` | data-source | community | network, records:write | 账号/OAuth, 网络, Python 依赖 | adapter+rpc | skipped（requires-account-oauth） |
| `io.github.dogsheep.healthkit-to-sqlite` | data-source | official | files:user-selected, records:write | - | adapter+rpc | pass · import.healthkit |
| `io.github.dtcooper.fitparse` | device-adapter | community | files:user-selected, records:write | Python 依赖 | worker-rpc | partial（fixture-required; dispatch verified） · summary |
| `io.github.gagebenne.pydexcom` | device-adapter | community | network, records:write | 账号/OAuth, 网络, Python 依赖 | worker-rpc | skipped（requires-account-oauth） |
| `io.github.grubersjoe.activity-calendar` | dashboard-widget | community | records:read | - | adapter+rpc | pass · summary |
| `io.github.hbldh.bleak` | device-adapter | community | files:user-selected, records:write | 硬件, Python 依赖 | worker-rpc | skipped（requires-hardware） |
| `io.github.holgern.pyedflib` | exporter | official | files:user-selected, files:export, records:read | Python 依赖 | adapter+rpc | pass · export.csv |
| `io.github.jrnl-org.jrnl` | health-domain | community | records:read, llm | 外部 CLI, Python 依赖 | adapter+rpc | pass · journal.list |
| `io.github.leeoniya.uplot` | dashboard-widget | community | records:read | - | adapter+rpc | pass · trend |
| `io.github.mit-lcp.wfdb` | exporter | official | files:user-selected, files:export, records:read | - | adapter+rpc | pass · export.csv |
| `io.github.neuropsychology.neurokit2` | analysis-model | official | records:read, llm | - | manifest-only | pass · hrv.summary |
| `io.github.observablehq.plot` | dashboard-widget | community | records:read | - | adapter+rpc | pass · plot.trend |
| `io.github.openbci-archive.openbci` | device-adapter | community | files:user-selected, records:write | 硬件, Python 依赖 | manifest-only | skipped（requires-hardware） |
| `io.github.openfoodfacts.openfoodfacts` | data-source | community | network, llm, records:write | 网络, Python 依赖 | worker-rpc | skipped（requires-live-network） |
| `io.github.orcasgit.fitbit` | data-source | community | network, records:write | 账号/OAuth, 网络, Python 依赖 | manifest-only | skipped（requires-account-oauth） |
| `io.github.paulvangentcom.heartpy` | analysis-model | official | records:read, llm | Python 依赖 | manifest-only | pass · ppg.quality |
| `io.github.pgomes92.pyhrv` | analysis-model | community | records:read, llm | Python 依赖 | manifest-only | partial（representative-method-returned-error） · hrv.metrics |
| `io.github.polyvertex.fitdecode` | device-adapter | community | files:user-selected, records:write | Python 依赖 | worker-rpc | partial（fixture-required; dispatch verified） · summary |
| `io.github.raphaelvallat.yasa` | analysis-model | community | records:read, llm | Python 依赖 | manifest-only | fail（install-or-start-failed） |
| `io.github.scientisst.biosppy` | analysis-model | official | records:read, llm | Python 依赖 | manifest-only | pass · ecg.quality |
| `io.github.stravalib.stravalib` | data-source | community | records:read, records:write, network | 账号/OAuth, 网络, Python 依赖 | adapter+rpc | skipped（requires-account-oauth） |
| `io.github.tkrajina.gpxpy` | device-adapter | official | files:user-selected, files:export, records:write | Python 依赖 | worker-rpc | pass · importFile |
| `io.github.tremorlabs.tremor` | dashboard-widget | community | records:read | - | adapter+rpc | pass · kpis |
| `io.github.vangorra.withings` | data-source | community | network, records:write | 账号/OAuth, 网络, Python 依赖 | manifest-only | skipped（requires-account-oauth） |
| `org.eclipsehealth.cardia` | analysis-model | official | files:user-selected | 随包内置 | none | skipped（bundled-with-installer） |
| `org.eclipsehealth.relay-ecg` | analysis-model | official | records:read | Python 依赖 | manifest-only | pass · list_models |
| `org.eclipsehealth.relay-sleep` | analysis-model | official | records:read | Python 依赖 | manifest-only | pass · list_models |

## 迁移理由分组

- **账号/OAuth**：garminconnect、fitbit、withings、myfitnesspal、stravalib、pydexcom。
- **硬件/BLE**：bleak、brainflow、muselsl、openbci-python。
- **实时网络/抓取脆弱**：openfoodfacts。
- **外部 CLI**：habitctl、jrnl。
- **可选 UI/导入、非核心闭环**：activity-calendar、echarts、observable-plot、uplot、tremor、fitdecode、fitparse。
- **上游兼容性/运行环境未通过冒烟**：pyhrv（ReturnTuple 不兼容）、yasa（worker 最小环境缺 HOME/USERPROFILE）。

## 复现

```powershell
backend\.venv\Scripts\python.exe scripts/pack_official_modules.py
backend\.venv\Scripts\python.exe scripts/build_marketplace_index.py
backend\.venv\Scripts\python.exe scripts/audit_modules.py --deps install
backend\.venv\Scripts\python.exe -m pytest backend/tests/modules backend/tests/marketplace
```
