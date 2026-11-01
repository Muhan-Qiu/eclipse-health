# SCP-ECG 格式要点（最小可用子集）

来源：EN 1064 / SCP-ECG 结构参考实现
<https://github.com/Ivorforce/SCP-ECG-Python-Interactive-Reader>（MIT）、
<https://github.com/gitrust/scpinfo>（MIT）、Healforce 变体
<https://github.com/KaibinBao/healforcescpecg>（MIT）。样本见 `uploads/samples/scp-ecg/`。

## 文件结构

- 文件头：`crc u16` + `记录总长度 u32`（小端）。
- 随后是各 section，**每个 section 都有 16 字节头**：
  `crc u16 | id u16 | length u32 | section_version u8 | protocol_version u8 | reserved 6B`。
  `length` 含 16 字节头。
- **Section 0**（id=0）是目录：6 字节文件头之后从偏移 6 开始，头后是指针数组，每项 10 字节：
  `section id u16 | section length u32 | index u32`。
  **index 从 1 开始，实际偏移 = index - 1**；index=0 表示空槽，可提前结束。
- 标准 section：0 目录、1 患者/采集数据、2 Huffman 表、3 导联定义、4 参考搏动、
  5 参考搏动样本、6 节律数据、7 全局测量、8 导联测量、9 搏动测量、10 诊断、
  11 通用注释。解析不了的段返回 `unsupported_section`，不要输出猜测数据。

## Section 1（患者/采集数据）

头之后是标签序列，每个标签：`tag id u8 | length u16 | data`；`tag id == 255` 为结束符，`length == 0` 跳过。
常用标签：0 姓、1 名、2 患者 ID、4 年龄（u16 + 单位）、5 出生日期（年 u16、月、日）、
6 身高、7 体重、8 性别、14 采集设备（含型号字符串，如 `ELI250`）、15 分析设备、
16/17 机构、18/19 科室、20/21 医生、22 技师、23 房间、25 采集日期（年 u16、月、日）、
26 采集时间（时、分、秒）、27 高通滤波 ×100 Hz、28 低通滤波 Hz、30 自由文本、31 序列号。

## Section 3（导联定义）

`lead_count u8 | flag u8 |` 每导联 9 字节：`start_sample u32 | end_sample u32 | lead_id u8`
（起止样本号从 1 开始、含两端）。`flag`：bit0 参考搏动减除、bit1 保留、bit2 各导联同时记录、
bit3+ 同时记录导联数。导联 ID 表（0=I, 1=II, 2=III? 注意！）以 `scpinfo` 的 leadtable 为准：
**1=I, 2=II, 3=V1, 4=V2, 5=V3, 6=V4, 7=V5, 8=V6, 9=V7, 61=III, 62=aVR, 63=aVL, 64=aVF**。
不同实现对该表有分歧，适配器应内置该表并在报告中注明来源。

## Section 6（节律数据）

`amp_multiplier u16`（nV/LSB）、`sample_time_interval u16`（µs）、`encoding u8`、`compression u8`，
然后每导联一个 `u16` 字节长度，再按导联顺序依次存放数据。
- 采样率 = `1e6 / sample_time_interval`。
- 物理值 mV = 解码值 × `amp_multiplier / 1e6`。
- `encoding`：0 原值，1 一阶差分，2 二阶差分。二阶差分解码：前两个值为真实值，
  先构造导数（首项 = v1-v0，其余为二阶差分）再 cumsum 两次；直接 cumsum 两次会漂移。
- Huffman：section 2 为空 / `number_of_tables == 0` 时按原始 int16；`19999` 用规范 C.3.7.6 默认表
  （`0`, `100`, `101`, `1100`, `1101`, … 的符号码）；自定义表暂不支持。
- `compression != 0`（双模态压缩）与参考搏动减除不支持，返回 `unsupported_section`。

## 已知坑

- **Healforce Prince 180D 导出不是合规 SCP-ECG**：section 0 从偏移 6 开始、指针 offset 为绝对偏移
  （不再 -1）、文件长度只有 16 bit、section 3 声明 3 导联但仅 1 个有数据、section 6 用 12-bit
  打包（每 3 个 16-bit 字装 4 个 12-bit 采样：10-bit 有符号 + 2-bit 搏动标记）且导联交错、
  section 2 有 Huffman 表但数据并未 Huffman 编码。**不要按标准解码器读 Healforce 文件**。
- 文件可能补齐到 32 KB（0x8000）固定大小；以 section 0 记录长度为准，不要按文件大小判断截断。
- CRC 各家实现不一致（Healforce 甚至不是 CRC-CCITT），不要因 CRC 不匹配直接拒收。
- 日期在标签 25 中是 4 字节（年 u16+月+日）；不要和标签 5 出生日期混淆。
- 复测/连续记录可能拆成多个文件，section 3 的 start_sample 会 >1（如 288001），不代表时间偏移。
- SCP 数值常按 2.5 µV 或 9.524 µV/LSB 量化；以 section 6 的 amp_multiplier 为准。

## 样本能力

| 样本 | 能力 | 限制 |
|---|---|---|
| `example.scp` | 标准 12 导联、500 Hz、10 s、默认 Huffman + 二阶差分、真实设备（ELI250） | 单条记录；无 Beats 汇总需求 |
| `62.SCP` / `63.SCP` | Healforce 真实设备变体、单导联 V3、4500 点 | 非标准编码，需专门解码；采样率需按厂商编码推导 |

推断（标注依据）：Healforce 的采样率无法从 section 6 的 150 µs 直接得到（与 4500 点/段不符），
按 4 采样/3 字打包与设备常见 250–500 Hz 推断为 250 Hz 或 500 Hz，未验证，索引中记 0。
