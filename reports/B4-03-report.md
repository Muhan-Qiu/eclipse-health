# 报告 · B4-03 设备/医院格式适配器
状态：完成（EDF、SCP-ECG 已用公开真实样本验证；Apple/Samsung/华为为 experimental）

## 交付
- `importers/edf_adapter.py`：EDF/EDF+ 固定头 256B + 信号定义、数字→物理换算、多导联、起始时间、标注计数；非 ECG 标签通道拒绝，同记录不同采样率通道跳过。
- `importers/scp_ecg_adapter.py`：按真实 EN 1064 结构解析文件头/16B 段头/section 0 指针/1 头/section 2 默认 Huffman/section 3 导联/section 6 节律数据；支持 16-bit、AVM(nV/LSB)、一阶/二阶差分；未知变体明确 `unsupported_section`。
- `importers/apple_adapter.py` + `vendor_adapter.py` + `samsung_adapter.py` / `huawei_adapter.py`：Apple Health CSV（BOM/ISO 时区/注释采样率/Lead I/按量级推断 V 或 mV）；Samsung/华为 CSV+JSON 常见字段（time/timestamp、voltage/samples、samplingRate、unit、lead），缺字段用 `requires` 强制用户确认。
- `importers/tabular.py`：厂商文本共用读取（编码、分隔符、注释、ISO 时间列、单列表头）。
- `registry.py`：WFDB/CSV/EDF/SCP-ECG/Apple/Samsung/华为统一探测；同置信度冲突返回 422 `ambiguous_format` + 候选，不替用户选。
- `placeholders.py`：五个厂商占位全部移除，`placeholder_adapters()` 为空。
- 测试：新增 EDF/SCP/厂商三组，合计导入套件 94 例；真实夹具见 `backend/tests/fixtures/imports/{edf,scp-ecg}`。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend\src\eclipse_health_backend\importers backend\tests\imports` → **All checks passed**。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\imports` → **94 passed in 14.44s**。
- 回归 `pytest backend/tests/core backend/tests/api` → **80 passed in 3.91s**。
- TestClient 手工链路（每个格式 preview → commit → `GET /records/{id}/signal`）：

  | 输入 | format | fs | 导联 | 读回点数 | sourceUnit | verification |
  |---|---|---|---|---|---|---|
  | 合成 edf | edf | 500 | 1 | 1000 | mV | verified |
  | 真实 MIT-BIH→EDF | edf | 1000 | 12 | 2000 | mV | verified |
  | 合成 scp | scp-ecg | 500 | 1 | 200 | nV | verified |
  | 真实 scpinfo example.scp | scp-ecg | 500 | 12 | 5000 | nV | verified |
  | Apple CSV | apple | 500 | 1 | 1000 | mV | experimental |
  | Samsung JSON | samsung | 500 | 1 | 1000 | mV | experimental |
  | 华为 JSON（补参数） | huawei | 500 | 1 | 1000 | mV | experimental |

- SCP-ECG 真实样本：`gitrust/scpinfo` 的 `example.scp`（MIT）解码结果与 Ivorforce 参考实现逐导联比对，max abs diff **2.2e-16**；fixture sha256 `c7135a…1edfe`。
- EDF 真实样本：`Iliad-a/mit2edf` 的 `Result-1.edf`（MIT-BIH，ODC-BY）取前 2 条记录；12 导联/1000 Hz 全部读回；fixture sha256 `61e746…e3c`。
- 另用 pyedflib `test_generator.edf`（2.7MB，未入库）核对头部 12 通道、uV 换算与首记录数据偏移，结果一致。
- B4-02 到位后补测：`mitdb100-1/2lead-10s.edf` 正常导入；`short_psg.edf`（无 ECG）与 `SC4001EC-Hypnogram.edf`（纯注释）明确 422；Healforce `healforce-62.scp` 明确 `unsupported_section`，未按标准误读；Apple 合成夹具按量级从 V 推断并换算到 mV。

## 能力矩阵
| 格式 | 真实样本 | 合成验证 | 支持字段 | 已知限制 | 需要用户补 |
|---|---|---|---|---|---|
| EDF | 是（MIT-BIH 派生，12导/1000Hz） | 是 | 多导联、fs、单位、起始时间、标注数 | 不支持 BDF/24-bit；通道采样率不同则跳过；标注只计数；非 ECG 标签拒绝 | 其他设备 EDF |
| SCP-ECG | 是（scpinfo example，12导/500Hz） | 是 | section0/1/2/3/6、Huffman 默认表、AVM、差分编码 | 自定义 Huffman、非同步记录、参考搏动减法、仅 section5、8-bit 不支持 | 医院其他变体 |
| Apple | 否 | 是（B4-02 合成夹具，V 量级） | time/ISO、Voltage/Lead I、V/mV 量级推断、BOM、时区 | 识别依赖文件名或 Lead I 签名；普通 time,voltage 落回通用 CSV | 一份真实 `electrocardiograms.csv` |
| Samsung | 否 | 是 | CSV/JSON 通用键、fs、unit、lead | 公开格式不统一，字段按常见导出映射 | 真实导出文件 + 字段说明 |
| 华为 | 否 | 是 | 同上，缺省全部 `requires` | 公开资料最少，不猜字段 | 真实导出文件 |

## 未做 / 偏离
- B4-02 的 `docs/FORMATS/**`、`uploads/samples/index.json` 与夹具在开发中途到位；Apple/Samsung/华为仍无真实导出（索引 `missing`），保持 `experimental` 与 preview 警告。
- SCP-ECG 任务的段描述（2=导联、3=数据）与真实标准不符；按 EN 1064 实际结构实现（3=导联、6=节律数据），已用真实样本与参考实现交叉验证。
- Apple 单位按 B4-02 文档做量级推断（V/mV），推断不了时强制确认；不再默认 mV。
- Apple CSV 被改名且表头不含 Lead I 时会落回通用 CSV（仍可导入，但导联需确认）。
- Samsung/华为不默认导联/单位；Apple 按公开规格默认 Lead I 并给 `lead_assumed` 警告。
- B4-02 文档建议 Samsung/华为在无样本前只留占位；本任务要求接进导入链路，因此实现「仅识别文件名/内容标记 + 通用字段映射 + 缺项 requires + experimental」，未猜测固定厂商字段。
- 真实夹具只保留小文件（我们的 51KB/34KB 与 B4-02 的 4–184KB 文件），未复制大样本。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `ruff check backend` 全量仍失败：`backend/packaging/serve.py:186` 的 RUF100 未使用 noqa（非本区文件，未改）。
- 前端 `ImportHintFormat` 仍只有 `wfdb|csv|auto`；新格式自动识别可用，手动选择/hint 需 UI 侧扩类型与下拉项。
- B4-02 已交付 `uploads/samples/index.json` 与 `docs/FORMATS/*.md`；Apple/Samsung/华为真实导出仍缺，到位后把 `experimental` 改为 `verified`。
- 工作区根目录有他人生成的 `apple.html`/`ddg.html`/`s.html` 等临时文件，未处理。

## 需要指挥官决策
- EDF/SCP 的 `verified` 以“公开真实样本 + 参考实现交叉验证”为准，是否可以接受。
- EDF 目前拒绝无 ECG 标签的通道（如 `CH1`）；是否允许用户显式指定“文件就是 ECG”后强行导入。
- Samsung/华为是否保持“缺采样率/单位/导联必须确认”，还是允许默认 mV/I。

## 建议下一批
- 用用户真实 Apple/Samsung/华为导出补验字段与单位；EDF BDF/24-bit 与混合采样率；SCP 自定义 Huffman、section5 参考搏动、非同步导联；UI 格式提示与实验标记展示。
