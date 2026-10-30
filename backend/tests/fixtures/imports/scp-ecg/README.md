# SCP-ECG 真实样本

- 文件：`example.scp`（34,144 字节）
- 来源：https://github.com/gitrust/scpinfo/blob/master/example/example.scp
- 许可证：MIT（Copyright (c) 2020 gitrust），全文见同目录 `LICENSE-gitrust-scpinfo.txt`
- sha256：`c7135a29ef2e36b829d0972f3859eee5b7c2f48e6a99af28b19f3a0e1a91edfe`
- 内容：12 导联 / 5000 样本 / 500 Hz / 标准 Huffman + 二阶差分 / AVM=2500 nV
- 用途：`tests/imports/test_scp_ecg_import.py` 验证真实 SCP-ECG 解码；测试只读。
