# 导入测试夹具（B4-02 提供）

| 路径 | 真/合成 | 来源 | 许可证 | 用途 |
|---|---|---|---|---|
| `scp-ecg/example.scp` | 真实 | https://github.com/gitrust/scpinfo/blob/master/example/example.scp | MIT | 标准 SCP-ECG，12 导联 / 500 Hz / 10 s |
| `scp-ecg/healforce-62.scp` | 真实 | https://github.com/KaibinBao/healforcescpecg/blob/master/demodata/ECG_0/62.SCP | MIT | Healforce 非标准变体（不应按标准解码） |
| `edf/mitdb100-1lead-10s.edf` | 合成（派生） | MIT-BIH 100 → EDF，见 `_make_fixtures.py` | ODC-By-1.0 | 单导联 EDF |
| `edf/mitdb100-2lead-10s.edf` | 合成（派生） | 同上 | ODC-By-1.0 | 双导联 EDF（MLII/V5） |
| `edf/short_psg.edf` | 真实 | edfio 测试数据（上游 Sleep-EDF） | Apache-2.0 / ODC-By-1.0 | 多通道、混合采样率、**无 ECG** |
| `edf/SC4001EC-Hypnogram.edf` | 真实 | 同上 | Apache-2.0 / ODC-By-1.0 | EDF+C 纯注释 |
| `apple/electrocardiograms.csv` | **合成** | MIT-BIH 波形按推测格式生成，见 `_make_fixtures.py` | ODC-By-1.0 | Apple CSV 解析路径；**非真实 Apple 导出** |

完整清单与 sha256：`uploads/samples/index.json`；格式说明：`docs/FORMATS/*.md`。
`_make_fixtures.py` 是一次性生成脚本，不是生产代码；重新生成会改变 sha256。
