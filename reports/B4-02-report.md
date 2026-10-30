# 报告 · B4-02 公开样本与格式资料采集

状态：部分完成

## 交付
- 样本：`uploads/samples/edf/`（4 个：2 个由 MIT-BIH 派生的 ECG EDF + Sleep-EDF 多通道 EDF + EDF+C 注释文件）；
  `uploads/samples/scp-ecg/`（3 个：1 个标准 12 导联真实 SCP-ECG + 2 个 Healforce 真实变体）。
- 索引：`uploads/samples/index.json`（7 个样本含 sha256/大小/导联/采样率/时长/许可证；3 个 `missing`：apple/samsung/huawei，写清缺什么）。
- 来源清单：`uploads/SOURCES.md`（每个文件的 URL、许可证、未采用来源及原因）。
- 格式说明：`docs/FORMATS/{edf,scp-ecg,apple,samsung,huawei}.md`（41–75 行/篇，推断处已标注依据）。
- 夹具：`backend/tests/fixtures/imports/{edf,scp-ecg,apple}/`，含 `README.md`（真/合成对照）、
  `_validate_samples.py`（最小校验）、两个 `_make_fixtures.py`（一次性生成脚本，非生产解析器）。
- Apple 只有**合成**夹具 `apple/electrocardiograms.csv`（512 Hz、`time,voltage`、伏特、Lead I，波形来自 MIT-BIH）。
- Samsung/华为只有文档，无夹具（字段未知，不编造）。

## 样本能力矩阵

| 格式 | 结论 | 样本 | 能力 / 限制 |
|---|---|---|---|
| EDF/EDF+ | 找到（派生+公开） | 4 个，≤185 KB | 单/双导联 ECG、多通道混合采样率、EDF+C 注释；无厂商原始 ECG 文件 |
| SCP-ECG | 找到（真实公开） | 3 个，33–34 KB | 标准 12 导联 500 Hz 可完整解码；Healforce 变体需专门解码 |
| Apple | 不可得（仅文档） | 合成 1 个 | `time,voltage` / 512 Hz / 伏特为推断；需用户真实导出验证 |
| Samsung | 不可得 | 0 | 无公开导出格式；需用户提供 CSV/JSON |
| 华为 | 不可得 | 0 | 无公开导出格式；需用户提供 CSV/JSON |

## 验证
- 命令：`backend\.venv\Scripts\python.exe backend\tests\fixtures\imports\_validate_samples.py`
- 结果：pass。7 个样本 sha256/大小与索引全部 `OK`。
  - EDF：`mitdb100-2lead` 360 Hz×10 s，`mitdb100-1lead` 360 Hz×10 s，`short_psg` 100/1 Hz×300 s（无 ECG），
    `Hypnogram` EDF+C 纯注释；单位字段读出 `mV`/`uV`。
  - SCP-ECG：`example.scp` 标准解析成功——section 0/1/2/3/5/6/7，设备 `ELI250`，采集 2002-11-22 09:10:00，
    12 导联各 5000 点，500 Hz，编码=2（二阶差分），2500 nV/LSB；用标准库 + 默认 Huffman 表解码后
    导联 II 范围 -0.67..0.34 mV、V2 -1.93..0.41 mV，生理上合理。
  - Apple 合成 CSV：5120 行、步长 0.001953 s（≈512 Hz）、±1 mV。
  - 边界/非法：截断 EDF、截断 SCP、空 CSV 均按预期抛 `ValueError`。
- 命令：`backend\.venv\Scripts\python.exe -m ruff check backend\tests\fixtures\imports`
- 结果：pass（All checks passed）。
- 现有工具：`wfdb 4.3.1` **不能**读 EDF（报找不到 `.hea`）；`pyedflib`/`mne` 未安装，EDF 只用标准库校验。
- 未跑 pytest：本任务不含生产解析器；夹具可能被 B4-03 的测试使用，由 B4-03 跑 `backend\tests\imports`。

## 未做 / 偏离
- **Apple 没有公开真实导出样本**：Apple 支持页/HealthKit 文档不提供样例，GitHub 也没有可再分发的脱敏导出；
  CSV 列名/单位/时间步长按 HealthKit 语义与社区目录结构**推断**，已在 `docs/FORMATS/apple.md` 标注。
- **Samsung/华为无公开原始波形导出格式**：只有 PDF 分享或合作方 SDK；按「需用户提供」处理，未造夹具。
- **EDF 没有找到公开 ECG 样本**：PhysioNet 的 EDF 数据集（Sleep-EDF/CHAT/SHHS）要么无 ECG 要么需授权；
  PhysioBank ATM 已下线（404）。改为从仓库已有的 MIT-BIH 100（ODC-By）派生标准 EDF，标记 `derived: true`。
- **SCP-ECG 的 Healforce 样本非 EN 1064**：section 0 偏移、绝对指针、16-bit 文件长度、12-bit 打包均不同；
  已如实记录，适配器不应按标准解码。
- 下载方式：WebFetch 访问 Bing 被工具的安全校验拦截，改用 `curl` + GitHub API/raw 检索；
  未使用 WebSearch（上游不支持）。临时检索文件已清理，未留在仓库。
- `uploads/README.md` 写着「Agent 不得写入 uploads/」，与任务提示词冲突；按提示词（B4-02 是唯一可写者）执行，
  未修改该 README。

## 跨区需求（需要别的 Agent 或指挥官处理）
- **B4-03**：开工时 `backend/tests/fixtures/imports/scp-ecg/README.md` 与 `example.scp` 已由 B4-03 先放置；
  本次复制了同名 `example.scp`（内容相同）与 `healforce-62.scp`，请勿回退。所有夹具按 `README.md` 的真/合成标注使用。
- **B4-03**：Samsung/华为不要写死字段映射，只返回 `requires`；Apple 先 `experimental`。
- **指挥官**：`uploads/` 已被 `.gitignore` 忽略，样本不会进版本库；若需要样本随仓库分发，需另行决定。

## 需要指挥官决策
- 是否接受 Apple 合成夹具 + 「推断格式」进入 B4-03（当前建议：接受，标 `experimental`）。
- Healforce 非标准 SCP 是否纳入 B4-03 范围（当前建议：只识别并明确报 `unsupported`，不实现厂商解码）。
- 是否向用户征集 Apple/Samsung/华为真实导出包（需要用户操作，Agent 无法代替）。

## 建议下一批
- 用用户提供的真实导出补 Apple（验证 CSV 列名/单位）与 Samsung/华为样本；
- 如后续要支持更多 EDF 变体，可引入 `pyedflib`（需批准新增依赖）做交叉验证；
- 为 SCP-ECG 增加「Healforce 变体」独立状态码，避免被当成坏文件。
