# eclipse health · 第三方模块候选 30 个（G6 调研）

> 2026-11-01 · 方法：GitHub REST API（license/stars/language/archived）+ 仓库 LICENSE/README + PyPI `requires_dist`。
> 目标：用**薄适配层**（stdio JSON-RPC 包装 CLI 或 Python 库）接入；不写代码，不做 fork。
> 星数为 2026-11-01 快照；SPDX 以仓库 LICENSE 为准，GitHub API 的 `NOASSERTION` 已人工核对。

## 0. 结论摘要

- 30 个候选全部为 MIT / Apache-2.0 / BSD-3-Clause / ISC / GPL-3.0 / GPL-2.0-or-later，均满足「宽松许可或 GPL-3.0 兼容」。
- **可直接复用现有 venv**：NeuroKit2、HeartPy（仅 numpy/scipy）、wfdb；**纯 stdlib/纯 Python**：fitdecode、fitparse、gpxpy；其余标记为 B（需模块独立 venv 装包）。
- 最薄、最稳的 10 个：NeuroKit2、HeartPy、fitdecode、gpxpy、wfdb、pyedflib、healthkit-to-sqlite、uPlot、BrainFlow、python-garminconnect。
- UI 类库（uPlot/ECharts/Plot/Tremor/React 热力图）**不能**作为 v2 声明式 widget 直接上架，只能走 v1 `ui:custom` 沙箱 iframe 或由核心内置；这是本轮最大契约缺口。

## 1. 判定口径

| 项 | 规则 |
|---|---|
| 许可 | MIT / Apache-2.0 / BSD / ISC / GPL-3.0 / GPL-2.0-or-later 通过；AGPL、NOASSERTION 且无法人工确认、无 LICENSE、专有/共享源码，一律拒绝 |
| 依赖 | `E`=现有 venv 已满足；`P`=纯 Python/stdlib；`B`=需在模块独立 venv 额外安装（标注关键包） |
| 平台 | 必须能在 Windows 11 + Python 3.12 运行；Docker/Postgres/Mongo/Android/iOS 专属直接降级或拒绝 |
| 形态 | 优先库/CLI；完整 Web 应用只允许抽取解析/算法部分 |
| 医疗 | 所有分析输出标注「非医疗器械」；算法结果不得表述为诊断 |

## 2. 候选总表（30）

### 2.1 心脏 / ECG / HRV

| # | 仓库 / 名称 | SPDX | ★ | 语言 | 做什么 | 模块类型 / ID | 适配方式 | UI 贡献 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [neuropsychology/NeuroKit](https://github.com/neuropsychology/NeuroKit) · NeuroKit2 | MIT | 2410 | Python | ECG/PPG/EDA/RSP 处理、峰值检测、HRV | analysis-model<br>`io.github.neuropsychology.neurokit2` | 包 `nk.ecg_process` / `nk.hrv`；临时 WFDB/CSV 入参；**E** | widgets：HRV stat+sparkline；pages：指标表/detail；tools：`hrv.summary`；recordTypes：analysis.hrv | S | 阈值结论易被当诊断；传递依赖多但已装；大信号走临时文件 |
| 2 | [paulvangentcom/heartrate_analysis_python](https://github.com/paulvangentcom/heartrate_analysis_python) · HeartPy | MIT | 1154 | Python | PPG/ECG 心率、HRV、异常搏动过滤 | analysis-model<br>`io.github.paulvangentcom.heartpy` | 包 `hp.process`；CSV/数组；**E**（numpy/scipy 已在） | widgets：RMSSD/SDNN；pages：段级结果表；tools：`ppg.quality` | S | 低质量信号仍返回数值，必须输出 quality 标志 |
| 3 | [Aura-healthcare/hrv-analysis](https://github.com/Aura-healthcare/hrv-analysis) | GPL-3.0 | 463 | Python | RR 间期时域/频域/非线性 HRV | analysis-model<br>`io.github.aura-healthcare.hrv-analysis` | `HRV(data=rr)`；**B**（pandas/astropy/nolds） | widgets：趋势；pages：频域表；tools | S | 额外依赖；GPL 需进程隔离（RPC 已满足）；医学解读风险 |
| 4 | [PGomes92/pyhrv](https://github.com/PGomes92/pyhrv) | BSD-3-Clause | 342 | Python | HRV 工具箱（时/频/非线性） | analysis-model<br>`io.github.pgomes92.pyhrv` | `pyhrv.time_domain/frequency_domain`；**B**（biosppy/nolds/spectrum） | widgets/pages/tools | M | 依赖链重、维护慢；numpy 输出需 JSON 化 |
| 5 | [scientisst/BioSPPy](https://github.com/scientisst/BioSPPy) | BSD-3-Clause | 124 | Python | ECG/EDA/EMG/呼吸信号处理 | analysis-model<br>`io.github.scientisst.biosppy` | 只用 ECG/HRV 子集；**B**（h5py/opencv/sklearn） | widgets/pages | M | 重依赖；与 NeuroKit2 重叠，优先级低 |

### 2.2 睡眠 / 活动 / 体能

| # | 仓库 / 名称 | SPDX | ★ | 语言 | 做什么 | 模块类型 / ID | 适配方式 | UI 贡献 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| 6 | [raphaelvallat/yasa](https://github.com/raphaelvallat/yasa) · YASA | BSD-3-Clause | 592 | Python | PSG 睡眠分期、纺锤波、频带功率 | analysis-model<br>`io.github.raphaelvallat.yasa` | 包 `yasa.SleepStaging`；**B**（mne/lightgbm/pooch） | pages：睡眠分期表；widgets：睡眠效率；recordTypes：sleep.session | L | 需多导 PSG，单设备数据不足；内置训练模型再分发需核对；重依赖 |
| 7 | [polyvertex/fitdecode](https://github.com/polyvertex/fitdecode) | MIT | 220 | Python | Garmin/ANT `.FIT` 解码 | device-adapter<br>`io.github.polyvertex.fitdecode` | 纯 Python；临时 `.FIT` → JSON；**P**；v1 `importFormats` | importFormats；recordTypes：activity.session；widgets：距离/心率 | S | 私有 profile 字段缺失；时区处理 |
| 8 | [dtcooper/python-fitparse](https://github.com/dtcooper/python-fitparse) | MIT | 826 | Python | `.FIT` 解析（records/laps） | device-adapter<br>`io.github.dtcooper.fitparse` | 纯 Python；**P** | importFormats；recordTypes | S | 与 fitdecode 二选一；更新较慢 |
| 9 | [tkrajina/gpxpy](https://github.com/tkrajina/gpxpy) | Apache-2.0 | 1106 | Python | GPX 轨迹解析/生成 | device-adapter<br>`io.github.tkrajina.gpxpy` | 纯 Python；**P**；导入/导出 GPX | importFormats/exporters；widgets：轨迹距离 | S | 心率/功率依赖 Garmin 扩展；本身无健康指标 |
| 10 | [hbldh/bleak](https://github.com/hbldh/bleak) | MIT | 2570 | Python | 跨平台 BLE 客户端（Windows WinRT） | device-adapter<br>`io.github.hbldh.bleak` | 模块 venv 装 bleak；连接 HR 带/体脂秤，解析 GATT；**B** | recordTypes：hr.sample/weight；widgets：实时心率 | M | 需硬件与蓝牙权限；Windows 配对问题；无统一 profile |

### 2.3 身体指标 / 营养 / 代谢

| # | 仓库 / 名称 | SPDX | ★ | 语言 | 做什么 | 模块类型 / ID | 适配方式 | UI 贡献 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| 11 | [gagebenne/pydexcom](https://github.com/gagebenne/pydexcom) | MIT | 263 | Python | Dexcom Share CGM 血糖读数 | device-adapter<br>`io.github.gagebenne.pydexcom` | 包 `Dexcom`；requests→httpx 可移植；**B**；账号/区域参数 | widgets：当前血糖+趋势；pages：血糖表；recordTypes：glucose.reading | S | 非官方 API；账号凭据；医疗风险高；需网络 |
| 12 | [openfoodfacts/openfoodfacts-python](https://github.com/openfoodfacts/openfoodfacts-python) | MIT | 474 | Python | 条码查营养（Open Food Facts） | data-source<br>`io.github.openfoodfacts.openfoodfacts` | REST 查询；pydantic 已装，需 requests/tqdm；**B**；数据 ODbL | pages：食品 detail/form；recordTypes：nutrition.entry；tools：`food.lookup` | S | 数据 ODbL 署名/同源；网络；条目质量参差 |
| 13 | [orcasgit/python-fitbit](https://github.com/orcasgit/python-fitbit) | Apache-2.0 | 633 | Python | Fitbit Web API（活动/睡眠/体重/心率） | data-source<br>`io.github.orcasgit.fitbit` | OAuth2 + requests-oauthlib；token 本地保存；**B** | importFormats；recordTypes：activity/sleep；widgets：步数 | M | API key/网络；OAuth token 安全；非官方封装、维护慢 |
| 14 | [coddingtonbear/python-myfitnesspal](https://github.com/coddingtonbear/python-myfitnesspal) | MIT | 877 | Python | MyFitnessPal 饮食日记抓取 | data-source<br>`io.github.coddingtonbear.myfitnesspal` | 抓取页面；需 lxml/cloudscraper/browser_cookie3；**B**；仅导入 | recordTypes：nutrition.entry；pages：日记表 | M | 违反 ToS/Cloudflare 风险；存账号密码；易碎 |
| 15 | [vangorra/python_withings_api](https://github.com/vangorra/python_withings_api) | MIT | 111 | Python | Withings API（体重/体脂/血压/睡眠） | data-source<br>`io.github.vangorra.withings` | OAuth2 REST；token 刷新；**B**（requests/oauth，包名以 README 为准） | recordTypes：body.measurement；widgets：体重趋势 | M | API key/网络；OAuth；不同设备字段差异 |

### 2.4 心理 / 压力 / 呼吸 / 习惯

| # | 仓库 / 名称 | SPDX | ★ | 语言 | 做什么 | 模块类型 / ID | 适配方式 | UI 贡献 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| 16 | [brainflow-dev/brainflow](https://github.com/brainflow-dev/brainflow) · BrainFlow | MIT | 1783 | C++/Python | EEG/EMG/ECG 采集与滤波（多板卡） | device-adapter<br>`io.github.brainflow-dev.brainflow` | pip `brainflow` 二进制 wheel；BoardShim 读取→JSON；**B** | recordTypes：eeg.session；widgets：信号质量；pages：通道表 | M | 需硬件；wheel 平台；原始脑电隐私极高 |
| 17 | [alexandrebarachant/muse-lsl](https://github.com/alexandrebarachant/muse-lsl) · muselsl | BSD-3-Clause | 783 | Python | Muse 头环 EEG 流（LSL） | device-adapter<br>`io.github.alexandrebarachant.muselsl` | 模块 venv 装 pylsl/bleak；`muselsl stream` 子进程；**B** | recordTypes：eeg.session；widgets：冥想时长 | M | 依赖 LSL 运行时；BLE 配对；维护一般 |
| 18 | [openbci-archive/OpenBCI_Python](https://github.com/openbci-archive/OpenBCI_Python) | MIT | 542 | Python | OpenBCI 板串口采集 | device-adapter<br>`io.github.openbci-archive.openbci` | pyserial；库调用或子进程；**B** | recordTypes：eeg.session | M | 2022 年后停更；需硬件；串口权限 |
| 19 | [blinry/habitctl](https://github.com/blinry/habitctl) | GPL-2.0-or-later | 399 | Rust | 极简 CLI 习惯追踪 | health-domain<br>`io.github.blinry.habitctl` | 子进程调用，解析文本输出；需 cargo 构建 Windows exe；**B** | pages：习惯列表/form；widgets：连续天数；recordTypes：habit.log | M | 文本格式耦合；Rust 构建链；GPL 进程隔离 |
| 20 | [jrnl-org/jrnl](https://github.com/jrnl-org/jrnl) | GPL-3.0 | 7353 | Python | 加密 CLI 日记/心情记录 | health-domain<br>`io.github.jrnl-org.jrnl` | 子进程 `jrnl --export json`；依赖多；**B** | pages：日记 list/detail；recordTypes：journal.entry；tools：`journal.search` | M | 加密/密钥环；用户隐私；CLI 输出解析 |

### 2.5 集成 / 导出

| # | 仓库 / 名称 | SPDX | ★ | 语言 | 做什么 | 模块类型 / ID | 适配方式 | UI 贡献 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| 21 | [MIT-LCP/wfdb-python](https://github.com/MIT-LCP/wfdb-python) · wfdb | MIT | 853 | Python | WFDB 读写、ECG 记录 | exporter<br>`io.github.mit-lcp.wfdb` | 已装；`wfdb.wrsamp` 导出；**E** | exporters；importFormats | S | 采样率/文件头校验；大文件走临时句柄 |
| 22 | [holgern/pyedflib](https://github.com/holgern/pyedflib) | BSD-3-Clause | 247 | Python | EDF+/BDF+ 读写 | exporter<br>`io.github.holgern.pyedflib` | 模块 venv 装 pyedflib（二进制轮子）；**B** | exporters | S | 通道命名/单位需符合 EDF 规范；轮子平台 |
| 23 | [dogsheep/healthkit-to-sqlite](https://github.com/dogsheep/healthkit-to-sqlite) | Apache-2.0 | 249 | Python | Apple Health `export.zip` 解析 | data-source<br>`io.github.dogsheep.healthkit-to-sqlite` | 只复用解析逻辑；用 stdlib `zipfile`+`plistlib` 重写；**P/M** | importFormats；recordTypes：activity/vitals | M | 原依赖 sqlite-utils；XML 巨大需流式；隐私 |
| 24 | [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) | MIT | 3227 | Python | Garmin Connect 非官方 API | data-source<br>`io.github.cyberjunky.garminconnect` | 模块 venv 装 curl_cffi；登录→JSON；**B** | importFormats；recordTypes：activity/sleep/body | M | 非官方、2FA/风控易断；账号凭据；网络 |
| 25 | [stravalib/stravalib](https://github.com/stravalib/stravalib) | Apache-2.0 | 1004 | Python | Strava v3 API 活动同步 | data-source<br>`io.github.stravalib.stravalib` | OAuth2；pydantic 已装，需 pint/arrow；**B** | importFormats；widgets：周里程 | M | API key/限流；OAuth；只有运动数据，无临床指标 |

### 2.6 UI / 组件 / 可视化

| # | 仓库 / 名称 | SPDX | ★ | 语言 | 做什么 | 模块类型 / ID | 适配方式 | UI 贡献 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|---|---|
| 26 | [leeoniya/uPlot](https://github.com/leeoniya/uPlot) | MIT | 10605 | JS | 轻量高性能时序图 | dashboard-widget<br>`io.github.leeoniya.uplot` | 静态 JS 资源；v1 `ui:custom` 沙箱 iframe，或核心内置渲染器 | widgets：波形/趋势图 | S | v2 声明式 UI 禁止 iframe，需策略确认；CSP |
| 27 | [apache/echarts](https://github.com/apache/echarts) | Apache-2.0 | 67648 | TS/JS | 通用交互图表 | dashboard-widget<br>`io.github.apache.echarts` | vendor `dist`，iframe 沙箱 | widgets/pages 图表 | M | 体积大；iframe 策略；无 Python |
| 28 | [observablehq/plot](https://github.com/observablehq/plot) | ISC | 5417 | JS | 声明式语法图形 | dashboard-widget<br>`io.github.observablehq.plot` | vendor dist + iframe | widgets：趋势/分布 | M | 依赖 D3；iframe 策略 |
| 29 | [tremorlabs/tremor](https://github.com/tremorlabs/tremor) | Apache-2.0 | 3684 | TS/React | 仪表盘组件（KPI/图表） | dashboard-widget<br>`io.github.tremorlabs.tremor` | 需 React 构建；或取编译产物 iframe | widgets：KPI 卡 | M | 与核心设计令牌冲突；构建链 |
| 30 | [grubersjoe/react-activity-calendar](https://github.com/grubersjoe/react-activity-calendar) | MIT | 599 | TS/React | 活动/习惯热力图 | dashboard-widget<br>`io.github.grubersjoe.activity-calendar` | React 组件；iframe 或移植为 SVG 声明式 | widgets：热力图 | S | React 构建；v2 无 heatmap 组件类型 |

## 3. 依赖与运行时矩阵

| 状态 | 项目 |
|---|---|
| **E** 现有 venv 可满足 | NeuroKit2、HeartPy（numpy/scipy）、wfdb |
| **P** 纯 Python/stdlib | fitdecode、python-fitparse、gpxpy、healthkit-to-sqlite（解析部分） |
| **B** 需模块独立 venv | hrv-analysis、pyhrv、BioSPPy、YASA、bleak、pydexcom、openfoodfacts-python、python-fitbit、python-myfitnesspal、python_withings_api、BrainFlow、muselsl、OpenBCI_Python、habitctl（Rust 构建）、jrnl、pyedflib、python-garminconnect、stravalib |
| **N/A** JS/前端资产 | uPlot、ECharts、Observable Plot、Tremor、react-activity-calendar |

> 说明：CLAUDE.md 已定「每模块独立 venv」，因此 B 类不是硬阻塞，只是不能直接复用核心 venv；安装时需 network 权限并锁定版本/哈希。
> 模型权重：以上 30 个均**不提供外部可下载权重**；YASA 包内自带训练模型、BrainFlow 为算法库，若后续替换为 ONNX/safetensors 需单独记录权重许可。

## 3.5 待指挥官决策

1. UI 类库是否允许 v1 `ui:custom` 沙箱 iframe？若坚持 v2「禁止 iframe」，uPlot/ECharts/Plot/Tremor/热力图只能由核心内置，不能作为第三方模块。
2. 是否接受「模块独立 venv + 联网安装」作为 B 类依赖的标准路径（CLAUDE.md 已倾向接受，但需明确索引扫描时的依赖白名单）。
3. 非官方 API（Garmin/Dexcom/MyFitnessPal）是否进入官方索引，还是只允许社区索引并显著标注 ToS/稳定性风险。
4. 是否给 manifest 增加 `upstream` 字段（URL/commit/license），用于自动生成署名与升级核对。

## 4. Top 10 推荐（按「薄 + 稳 + 离线」排序）

1. **NeuroKit2**（MIT，E）：ECG/HRV 主力算法，已有依赖，S 工作量。
2. **HeartPy**（MIT，E）：PPG/ECG 补充与交叉校验，仅 numpy/scipy。
3. **fitdecode**（MIT，P）：FIT 文件导入，纯 Python，零依赖。
4. **gpxpy**（Apache-2.0，P）：GPX 活动轨迹导入/导出。
5. **wfdb**（MIT，E）：ECG 记录导入/导出，医疗格式基线。
6. **pyedflib**（BSD-3，B）：EDF/BDF 导出，补 WFDB 之外的医院格式。
7. **healthkit-to-sqlite**（Apache-2.0，P/M）：Apple Health 导入，解析逻辑可 stdlib 重写。
8. **uPlot**（MIT，S）：波形/趋势图，体积小、性能好。
9. **BrainFlow**（MIT，B）：EEG/ECG/EMG 设备接入基座，硬件生态广。
10. **python-garminconnect**（MIT，B）：Garmin 数据源，用户覆盖大（需接受非官方 API 风险）。

候选替补：pydexcom（CGM）、habitctl（习惯）、ECharts（图表）、hrv-analysis（HRV 补充）、python-fitbit（Fitbit 数据源）。

## 5. 拒绝样例（5）

| 仓库 | 许可/状态 | 拒绝理由 |
|---|---|---|
| [wger-project/wger](https://github.com/wger-project/wger) | AGPL-3.0 | AGPL 与核心分发模型冲突；完整 Django + Postgres 应用，无法薄适配 |
| [HabitRPG/habitica](https://github.com/HabitRPG/habitica) | NOASSERTION | 代码/美术素材混合许可，无法确认可再分发；Node + Mongo 单体，超出模块边界 |
| [nightscout/cgm-remote-monitor](https://github.com/nightscout/cgm-remote-monitor) | AGPL-3.0 | AGPL；Node + MongoDB 完整服务，不是库/CLI |
| [oliexdev/openScale](https://github.com/oliexdev/openScale) | GPL-3.0 | 许可兼容，但 Kotlin/Android 专属，无法在 Windows Python 3.12 运行 |
| [Freeyourgadget/Gadgetbridge](https://github.com/Freeyourgadget/Gadgetbridge) | AGPL-3.0（已归档，迁至 Codeberg） | AGPL + Android 专属 + 上游归档，不可维护 |

## 6. 许可证与署名清单（落地时必须执行）

1. **随模块保留上游 LICENSE/NOTICE**：放入 `licenses/<module-id>/`，不得删除版权头；Apache-2.0 需保留 NOTICE 并标注修改。
2. **作者 vs 维护者**：manifest `author` 写适配层维护者（我们/社区开发者），并在 `description`/`repository` 明确 upstream 仓库与原版权人；不得暗示上游背书。
3. **wrapper vs fork**：优先 wrapper（子进程/库调用），不改上游；确需 patch 时 fork 并保留原许可、公开修改源码（GPL 模块尤其）。
4. **GPL 隔离**：GPL-3.0 / GPL-2.0-or-later 模块只经 stdio JSON-RPC 通信，不把其代码静态链入核心；核心保持 GPL-3.0。
5. **数据许可独立**：Open Food Facts 数据为 ODbL（署名 + 同源）；Apple Health/Garmin/Strava 数据受各自 ToS 约束，只做用户本人数据本地导入。
6. **模型权重**：若从算法库升级为 ONNX/safetensors，单独记录权重许可、来源 URL、sha256；模型许可与代码许可分开写。
7. **医疗声明**：所有分析/评分模块输出加「非医疗器械，不用于诊断」；保留 signal quality 与置信度字段。
8. **密钥与隐私**：API key/token 存 OS 密钥库，不写日志；健康数据默认不出本机，联网必须声明 `network` 权限并逐次可见。
9. **可追溯**：登记 upstream commit SHA、SPDX、PyPI 版本、星数快照日期；升级时重新核对 LICENSE 变化。

