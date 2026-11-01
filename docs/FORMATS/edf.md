# EDF / EDF+ 格式要点

来源：EDF 规范 <https://www.edfplus.info/specs/edf.html>，EDF+ 规范
<https://www.edfplus.info/specs/edfplus.html>；样本见 `uploads/samples/edf/` 与
`uploads/samples/index.json`。

## 文件结构

1. **固定头 256 字节**（ASCII，空格填充）：
   - `0-7` 版本（`0` 为 EDF，`255` + 版本号为 BDF）
   - `8-87` 患者（EDF+ 要求 `code sex birthdate name` 四段，空格分隔）
   - `88-167` 记录信息（EDF+ 为 `Startdate dd-MMM-yyyy ...`）
   - `168-175` 开始日期 `dd.mm.yy`，`176-183` 开始时间 `hh.mm.ss`
   - `184-191` 头部字节数（= 256 + 每通道 256 × ns）
   - `192-235` 保留；EDF+ 以 `EDF+C`（连续）或 `EDF+D`（不连续）开头
   - `236-243` 数据记录条数，`244-251` 每条记录秒数，`252-255` 通道数 ns
2. **每通道 256 字节 × ns**，**按字段分列存放**（不是按通道分块！）：
   label 16、transducer 80、physical dimension 8、physical min 8、physical max 8、
   digital min 8、digital max 8、prefilter 80、samples per record 8、reserved 32。
3. **数据记录**：n_records × (每通道 samples_per_record 个 `int16` 小端)，按记录内通道顺序交错。
   每条记录内字节数 = Σ(samples_per_record) × 2（EDF）或 × 3（BDF）。

## 换算与语义

- 物理值 = `(digital - dig_min) / (dig_max - dig_min) * (phys_max - phys_min) + phys_min`。
- 物理单位看 physical dimension：ECG 通常是 `mV` 或 `uV`（也有 `V`、空白）。适配器必须换算到 mV。
- 采样率 = `samples_per_record / 记录秒数`；不同通道可以不同（如 100 Hz EEG + 1 Hz 体温）。
- 同一文件内所有记录长度必须一致；不连续记录（EDF+D）用注释通道的 TAL 表达。
- EDF+ 注释：至少一个通道 label 为 `EDF Annotations`，数据是 TAL 文本（`onset\0duration\0text\0`，
  可含时间戳 `+start\x14end\x15text\x14\0`）。注释通道**不是导联**，必须跳过。
- ECG 导联名常见：`ECG`、`ECG I`/`ECG II`、`MLII`、`V5`、`ECG1`、`MCG`。标签不统一，优先按
  `ECG|EKG|MLII|V[1-6]|I{1,3}|aV[RFL]` 匹配，再做单位/量程合理性检查。

## 已知坑

- **列式头**：按通道逐块读会全错（本任务生成脚本第一版就踩了）。
- `header_bytes` 以文件实际值为准，不要假设 = 256+256ns。
- 数字字段是空格填充的 ASCII，可能带前导空格；空字段在非 ECG 通道常见（phys min/max 为空），
  此时该通道不可换算，应跳过或要求校正，而不是猜。
- EDF+ 的 patient/recording 字段有严格格式；`X X X X` 表示匿名。真实导出可能含姓名/生日，
  适配器入库前必须脱敏（DATA_SCHEMA_V1 §15）。
- 开始日期 `dd.mm.yy` 的世纪约定：`85` 之后按 19xx，`00-84` 按 20xx（EDF+ 规范为 `yy` 加上下文）；
  更可靠的是读 EDF+ recording 字段的 4 位年份。
- 通道可能重复/缺采样；`samples_per_record` 为 0 的通道要忽略。
- 有些厂商用 `EDF+C` 但没有注释通道，或反之；以「是否有 `EDF Annotations` 通道」为准。
- BDF（24-bit）本批未提供样本；看到版本号 `255` 应先拒绝并提示。
- 不要用 `wfdb` 读 EDF：本机 `wfdb 4.3.1` 不支持 EDF；`pyedflib`/`mne` 未安装（B4-03 用标准库 + numpy）。

## 样本能力

| 样本 | 能力 | 限制 |
|---|---|---|
| `mitdb100-2lead-10s.edf` | 双导联、360 Hz、mV、10×1 s 记录 | 我们生成的标准 EDF，非厂商文件 |
| `mitdb100-1lead-10s.edf` | 单导联 | 同上 |
| `short_psg.edf` | 多通道、混合采样率（100/1 Hz）、10×30 s | **无 ECG 通道** |
| `SC4001EC-Hypnogram.edf` | EDF+C 纯注释、TAL | 无波形，只测注释跳过 |

推断（标注依据）：Apple Watch 导出的 EDF 不存在（Apple 用 CSV/XML）；EDF 里 ECG 的单位多为 mV
（phys dimension 字段），但因设备而异，仍需按字段换算。
