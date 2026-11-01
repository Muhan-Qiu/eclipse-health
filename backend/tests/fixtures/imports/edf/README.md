# EDF 真实样本（派生）

- 文件：`ecg-real.edf`（51,328 字节，12 导联 / 1000 Hz / 前 2 条数据记录 = 2 秒）
- 原始文件：https://github.com/Iliad-a/mit2edf/blob/master/Result-1.edf （747,328 字节）
- 上游数据：MIT-BIH Arrhythmia Database（PhysioNet），ODC-BY 1.0；转换仓库未附 LICENSE 文件
- 修改：只保留原始文件前 2 条记录，并把头部 `dataRecords` 改为 2；波形未改动
- 派生文件 sha256：`61e7463abdef176076f23ab4fe2d10856c7146476ec198999d7053e9e0a2fe3c`
- 用途：`tests/imports/test_edf_import.py` 验证真实 ECG EDF 的头部、单位、12 导联与数据偏移；测试只读
