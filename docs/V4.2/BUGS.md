# V4.2 问题清单（BUGS）

状态图例：`NEW` 待确认 / `REPRO` 已复现 / `ROOT CAUSE` 根因已定位 / `FIXING` 修复中 / `FIXED` 已修复待验证 / `DONE` 已验证

---

## BUG-201 除 Cardia 外，其他分析引擎无法分析心电图

- **状态**：`FIXED`（单测 + 真实 7 个 relay 模型 + 真实记录验证通过；待安装包实机验收）
- **优先级**：P0
- **用户描述**（2026-11-07）：
  > 除了 Cardia 模块，其他的它都不能正常分析我们的心电图。输入维度不匹配，直接就显示了；或者分析过程当中出现错误。

### 现象与复现

在本机 `%LOCALAPPDATA%\eclipse-health\eclipse_health.sqlite3` 的 `analyses` 表中，所有非 Cardia 分析均为 `failed`：

| 引擎 | 错误 |
|---|---|
| `org.eclipsehealth.relay-ecg:relay-k2` | `engine_error`：仅支持 2/3 维输入，模型输入维度为 4 |
| `org.eclipsehealth.relay-ecg:relay-k12` | 同上 |
| `org.eclipsehealth.relay-ecg:tlstm` | 同上 |
| `org.eclipsehealth.relay-ecg:bilstm` | 同上 |
| `org.eclipsehealth.relay-ecg:resnet1d` | `analysis_failed`：`ValueError: cannot reshape array of size 37908 into shape (162,2,234)` |

复现记录：2026-11-02 08:47–10:25、2026-11-07 02:23–02:25，记录 `rec_01a19bc6-a9a7-7730-a0d3-3bb148889108`（单导联 I、500 Hz、104.966 s）。Cardia 在同一记录上 `completed`，所以问题不在波形/导入。

### 根因

通用 ONNX 执行器只实现了「整段信号滑窗 + 单导联 + 单输入」的最小模型，而 relay-ecg 的 manifest 声明的是 V1 逐搏管线：

- `modules/official/relay-ecg/module.json`：
  - `input.mode = "sequence" | "beat"`
  - `input.leads = 2`
  - `input.windowBefore = 90`、`windowAfter = 144`（234 点窗口）
  - `input.beatsPerWindow = 64`、`input.zscorePerLead = true`、`input.dtMedianSeconds = 275/360`
  - `input.tensors.x.shape = [1, 64, 2, 234]`，`input.tensors.dt.shape = [1, 64]`
  - `preprocess.pipeline = "relay-v1-beat-window"`
- `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py`（V4.1 基线）：
  - `_preprocess_config()` 只读取 `normalize`、`windowSamples`、`strideSamples`、`channels`，**完全忽略** `mode`、`tensors`、`leads`、`beatsPerWindow`、`zscorePerLead`、`dtMedianSeconds`；
  - `_fit_input()` 只接受 2/3 维输入，遇到 4 维 `[1,64,2,234]` 直接抛「仅支持 2/3 维输入」；
  - 3 维 `[1,2,234]` 时从形状推断 `channels=2`，但数据只有 1 个导联，`reshape(count, 2, 234)` 抛原始 `ValueError`，且未被包装成 `OnnxEngineError`，于是 UI 显示 `ValueError: cannot reshape ...`；
  - `_session_for()` 没有像模块自身 worker 那样把符号 batch 固定为 1，relay-k12 的会话初始化可能超过十分钟。
- `backend/src/eclipse_health_backend/analysis_service/engines.py`：
  - 只要是 `format: onnx` 就登记为可用引擎，relay-sleep 的 `features-dt` / `raw-windows` 模型也会出现在 ECG 记录的分析引擎列表里，选中后必然维度不匹配。

### 修复

| 文件 | 变更 |
|---|---|
| `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py` | 新增 `relay-v1-beat-window` 管线：重采样到 360 Hz、单导联复制为双导联、XQRS 检测 R 峰、R 前 90 / 后 144 点切窗、逐导联 z-score、64 搏非重叠序列、`dt = RR / (275/360)`；支持 `sequence`（4 维 x + dt）与 `beat`（3 维 x）两种模式；输出 `[1,64,5]` / `[1,5]` 统一展平为 `[N, C]`；所有形状/推理异常包装为 `OnnxEngineError`；序列模型创建会话时固定 `batch=1` |
| `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py` | 旧窗口管线保留：`_fit_input` 遇到单导联数据 + 多通道模型时复制通道，不再抛裸 `ValueError` |
| `backend/src/eclipse_health_backend/analysis_service/engines.py` | 新增 `_unsupported_reason()`：`sleep-staging` / `features-dt` / `raw-windows` 模型标记为不可用并给出「不能分析心电记录」，避免选中后才报维度错误 |
| `backend/tests/analysis_service/test_relay_onnx_engine.py`（新增） | 5 组回归：4 维序列输入与 dt、3 维单搏输入、心搏不足、输出类别不匹配、睡眠模型不可用 |

### 行为变化

- relay-ecg 的 7 个模型现在能在 ECG 记录上完成分析；结果仍标记「模型级分类（非逐搏诊断）」。
- 单导联记录会复制为模型要求的双导联，结果中带 `single_lead_duplicated` 提示；500 Hz 等非 360 Hz 记录会重采样并带 `resampled` 提示。
- 末尾不足 64 搏的部分会丢弃，结果中带 `tail_beats_dropped` 提示，`parameters.beatsScored / beatsDropped` 可查。
- relay-sleep 的睡眠分期模型不再出现在可选列表中，而是标记为不可用并说明原因。

### 验收

- [x] `pytest tests/analysis_service`：全部通过（新增 5 个用例）；
- [x] `ruff check src tests/analysis_service/test_relay_onnx_engine.py`：通过；
- [x] 真实权重 + 真实记录（单导联 I、500 Hz、104.966 s）逐个模型验证：

| 模型 | 结果 | 耗时 |
|---|---|---|
| `relay-k2` | OK，128 搏评分 / 2 个序列 / 59 搏尾部丢弃 | 1.47 s |
| `resnet1d` | OK，187 搏逐搏评分 | 0.21 s |
| `bilstm` | OK，128 搏 / 2 序列 | 0.44 s |
| `tlstm` | OK，128 搏 / 2 序列 | 0.37 s |
| `relay-k4` | OK，128 搏 / 2 序列 | 2.61 s |
| `relay-k8` | OK，128 搏 / 2 序列 | 7.33 s |
| `relay-k12` | OK，128 搏 / 2 序列 | 11.53 s |

- [x] 构建产物 sidecar 与静默安装后的 sidecar：`GET /api/v1/health` 返回 `version=0.1.2`，引擎目录 7 个 relay 模型均 `available=true`；通过 API 发起 relay-k2 / resnet1d / relay-k8 / relay-k12 分析，全部 `completed`；
- [ ] 安装包界面实机：在记录详情页依次选择 relay-k2 / resnet1d / relay-k12，确认不再出现维度错误且能显示分类概率。

### 回滚点

- 修复前基线：`63b44d9`（V4.1 分支 `v4.1`）
- 本次修复提交：`cff837d`（分支 `v4.2`，tag `v4.2-m1`）
- 安装包记录提交：`efd4bc9`

---

## BUG-202 relay 引擎缺少心率 / HRV / 质量 / 异常占比

- **状态**：`FIXED`（单测 + 真实 relay-k2 记录验证通过；待安装包实机验收）
- **优先级**：P1
- **用户描述**（2026-11-07）：
  > 现在可以分析概率了，但是信号质量、异常波动占比、心率这些完全没有了。R 间期既然都算出来了，这些肯定很好算的呀。

### 根因

`onnx_engine.py` 的 relay 分支只把模型输出映射成 `class_probability.*` 测量值，并固定 `quality: None`、`beats: []`：

- 没有把逐搏 `argmax` 结果汇总成 N/SVEB/VEB/F 比例；
- 没有用 R 峰位置计算 RR，因此没有心率、SDNN、RMSSD、pNN50；
- 没有调用核心已有的 `assess_quality()`，所以信号质量分与质量警告为空；
- 前端 `analysis-panel.tsx` 的心率/HRV/异常占比/质量四个指标都从 measurements 和 `quality` 读取，读不到就显示 `—`。

### 修复

| 文件 | 变更 |
|---|---|
| `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py` | relay 分支对逐搏概率做 `argmax`，得到 `class_counts`；复用 `analysis.measurements.compute_measurements()` 生成 `heart_rate_mean/min/max`、`rr_mean`、`sdnn`、`rmssd`、`pnn50`、`n_ratio`、`svb_ratio`、`veb_ratio`、`f_ratio`；复用 `analysis.quality.assess_quality()` 生成 `quality.score/level/warnings/metrics`；摘要改为「平均心率 + N/SVEB/VEB/F 比例」 |
| `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py` | `_build_result()` 支持 `quality`、`extra_measurements`、`summary` 覆盖；relay 参数补充 `heartRate`、`classCounts`、`meanConfidence`、`qualityMetrics`、`lead`、`originalFs` |
| `backend/tests/analysis_service/test_relay_onnx_engine.py` | 新增断言：心率/HRV/比例/质量字段存在，质量分为 0–1，序列模型 `nBeatsDetected=80`、`nBeatsClassified=64` |

### 行为变化

- relay 引擎的分析结果现在和 Cardia 使用同一套测量口径：
  - 心率：平均 / 最小 / 最大；
  - HRV：RR 均值、SDNN、RMSSD、pNN50；
  - 逐搏比例：N / SVEB / VEB / F；
  - 信号质量：score、level、质量警告、质量指标。
- 序列模型只统计完整 64 搏序列；丢弃的尾部心搏不计入比例和 RR 统计，`parameters.beatsDropped` 保留说明。
- 质量评估失败不会让分析失败，会以 `quality_unavailable` 信息警告降级。

### 验收

- [x] `pytest tests/analysis_service/test_relay_onnx_engine.py`：5 passed；
- [x] `ruff check`：通过；
- [x] 真实 relay-k2 + 真实记录（单导联 I、500 Hz、104.966 s）：
  - 平均心率 105.43 bpm；
  - RR 均值 569.07 ms、SDNN 160.65 ms、RMSSD 164.89 ms、pNN50 4.76%；
  - 质量分 0.85（good）；
  - N 6.25% / SVEB 93.75% / VEB 0% / F 0%；
  - `nBeatsDetected=187`、`nBeatsClassified=128`；
- [ ] 安装包界面实机：确认四个指标卡片、质量警告和类别比例条正常显示。

### 回滚点

- 修复前基线：`9d7f3bb`（V4.2 分支）
- 本次修复提交：`b2487a5`（分支 `v4.2`）

---

## BUG-203 Cardia 警告 `lead_out_of_distribution` 显示乱码

- **状态**：`FIXED`（源码 + 单测；未打包，留待下一次 4.3 构建）
- **优先级**：P2
- **用户描述**（2026-11-08）：
  > 最后一句「当前导联为 I；模型在 MLII 上训练……」是乱码的，实在显示不了就删掉。

### 根因

1. Cardia 模块 worker 的 `main()` 没有像 relay/heartpy 那样显式
   `sys.stdin/stdout.reconfigure(encoding="utf-8")`。Windows 下管道 stdio 落到
   GBK，模块写出的中文警告被宿主按 UTF-8 读取，变成 `U+FFFD`。
2. 前端 `WarningRow` 只在没有 i18n 文案时回退到后端消息；
   `lead_out_of_distribution` 没有翻译键，于是把已损坏的后端消息直接显示出来。
3. 已有安装的 Cardia 模块版本相同，启动时不会自动覆盖，旧 worker 继续产生乱码。

### 修复

| 文件 | 变更 |
|---|---|
| `modules/official/cardia/src/main.py` | `main()` 显式把 stdin/stdout 固定为 UTF-8 |
| `modules/official/cardia/module.json` | 模块版本 `1.0.0` → `1.0.1`，并重新生成 `checksums.json` |
| `backend/src/eclipse_health_backend/analysis_service/bridge.py` | `ensure_installed()` 比较随包版本与已安装版本，不一致时自动升级 |
| `src/lib/i18n/zh-CN.ts`、`en-US.ts` | 补齐 `lead_out_of_distribution` 等警告文案；即使旧结果里存了乱码，UI 也显示干净文案 |

### 验收

- [x] `pytest tests/analysis_service`：通过；
- [x] `npx tsc --noEmit`：通过；
- [ ] 下次打包后实机确认 Cardia 警告不再出现乱码。

---

## BUG-204 relay 在手表单导联记录上 SVEB 比例异常高，缺少醒目提示

- **状态**：`FIXED`（文案 + 警告 + 单测；未打包，留待下一次 4.3 构建）
- **优先级**：P1
- **用户描述**（2026-11-08）：
  > 除了 Cardia，其他模型的 SVEB 特别高，甚至高过正常心搏。必须强调这是手表算出来的，不是真实比例，仅供参考；建议用医院心电图测试。是不是哪里弄错了？

### 核查结论：不是标签映射错误

用 relay-ecg 模块自身的 `_analyze()`（不经过核心的新代码）对同一段 360 Hz 信号做分析，
得到完全相同的结果：

```text
N 19.7% · SVEB 80.0% · VEB 0.0% · F 0.2% · Q 0.1%
counts: N=8, SVEB=120, VEB=0, F=0, Q=0
```

核心的 `argmax`、类别顺序和比例汇总与模块一致，所以高 SVEB 是模型在分布外输入上的
行为，不是类别下标或标签错位。

### 根因

- relay 模型在 MIT-BIH **医院双导联 MLII、360 Hz** 数据上训练；
- 当前记录是**手表单导联 Lead I、500 Hz、约 105 秒**，属于明显的分布外输入；
- 单导联被复制成两路以满足模型输入，模型看到的是退化双导联；
- 运动伪影、接触噪声和导联位置差异会让 SVEB 等类别吸收大量非典型形态，
  模型输出的逐搏类别比例不能当作真实心律失常比例。

### 修复

| 文件 | 变更 |
|---|---|
| `backend/src/eclipse_health_backend/analysis_service/onnx_engine.py` | 非 MLII / 非 360 Hz / 单导联输入时，在结果 warnings 最前面插入 `wearable_limited_accuracy`，明确说明 SVEB 可能偏高、不能当作真实比例、建议医院 12 导联心电图；参数增加 `outOfDistribution` |
| `src/components/records/analysis-panel.tsx` | 非 Cardia 引擎的结果顶部固定显示醒目 Alert「手表/可穿戴结果仅供参考」 |
| `src/lib/i18n/zh-CN.ts`、`en-US.ts` | 新增 `analysis.wearable.title/body` 与 `wearable_limited_accuracy` 文案 |

### 行为变化

- Cardia 结果不受影响；
- relay 等模块引擎在手表/可穿戴单导联记录上会同时显示：
  - 顶部醒目提示「手表/可穿戴结果仅供参考」；
  - 警告列表中的 `wearable_limited_accuracy`；
  - 原有质量警告与分类比例。
- 文案明确建议以医院 12 导联心电图和专业判读为准，并保留红旗症状立即就医提示。

### 验收

- [x] 模块自身 `_analyze()` 与核心结果一致，排除标签映射错误；
- [x] `pytest tests/analysis_service`：通过；
- [x] `npx tsc --noEmit`：通过；
- [ ] 下次打包后实机确认顶部提示与警告文案显示正常。

---

## 待补充

后续 bug 按同样格式追加：现象、复现、根因（file:line）、修复、验证、回滚点。
