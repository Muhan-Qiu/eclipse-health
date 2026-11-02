# 报告 · I2 Relay 心电模型包（4 个自研 + 3 个更低基线）

状态：完成（Agent 在写报告前被停止，指挥官续跑验收并补记）

## 交付
- `modules/official/relay-ecg/`：manifest、README/NOTICE、`src/main.py`（stdio JSON-RPC：health/warmup/list_models/analyze/stats/deactivate）、`src/adapter.py`、`models/index.json`、`tools/export_onnx.py`。
- 7 个 ONNX 在 `uploads/relay-ecg/models/`（gitignored）：4 个自研 + 3 个基线，合计 47MB。
- `backend/tests/modules/test_official_relay_ecg.py`：8 个测试。
- `scripts/pack_official_modules.py`：relay-ecg 打包时从 uploads 暂存权重；产出 `dist/modules/org.eclipsehealth.relay-ecg-0.1.0.ehmod`（26MB）。

## 模型与分数（macro F1，DS1/DS2，5 种子均值）
| 模型 | 类别 | score | 文件 |
|---|---|---|---|
| relay-k2 | ours | 0.5706 | relay_k2.onnx |
| relay-k12 | ours | 0.5417 | relay_k12.onnx |
| relay-k4 | ours | 0.5397 | relay_k4.onnx |
| relay-k8 | ours | 0.5199 | relay_k8.onnx |
| bilstm | baseline | 0.4186 | bilstm.onnx |
| resnet1d | baseline | 0.4178 | resnet1d.onnx |
| tlstm | baseline | 0.3522 | tlstm.onnx |

- 精选子集：V1 全量中 `lstm` 等基线在部分口径下高于 relay_k4/k8；本包按要求只收录低于我们最低分 0.5199 的基线，不是全量排行榜。
- 输入契约：`x [B,64,2,234]`（360 Hz，90 前/144 后采样，双导联 z-score）+ `dt [B,64]`；输出 `logits [B,64,5]`（N/SVEB/VEB/F/Q，Q 仅完整性）。
- 导出：opset 17，dynamic batch；PyTorch/onnxruntime argmax 一致性由模块测试覆盖。

## 验证
- `ruff check backend modules/official scripts`：All checks passed。
- `pytest backend/tests/modules/test_official_relay_ecg.py`：**8 passed**（约 20s）。
- `scripts/pack_official_modules.py`：33 模块打包成功（含 relay-ecg/relay-sleep），解压 checksums/layout 通过。
- 市场索引已重建并发布到 `https://eclipse-health.fit/official/index.json`（32 条，含两个 relay 模块）。

## 未做 / 偏离
- 没有重新训练；权重来自 V1 `results/ckpt`。
- 未把 relay-ecg 接入主记录分析 UI；通过模块页/引擎列表选择，现有 ONNX loader 可调用。
- 真实 WFDB 全流程分析未逐一跑 7 个模型；测试覆盖形状/排序/softmax/缺权重错误路径。
- 权重不入 git；打包时从 `uploads/` 复制。

## 跨区需求
- 安装包需重打以包含新的市场默认域名与模块索引；当前代码已完成，安装包重打中。
