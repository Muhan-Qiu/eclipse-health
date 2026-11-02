# B2-01 · ONNX 会话初始化 150 秒 · 排查报告

状态：根因已定位，**有可落地的修复**（数值差 2e-6，需指挥官放行）；本批先交付预热绕过。

## 结论

- 慢的不是线程/优化级别/Azure EP，也不是节点数本身：合成 12,000 节点模型初始化仅 0.84s。
- 真正的原因是 PyTorch 2.5.1 导出的**动态形状子图**（64 个展开 cell，6,176 Constant +
  2,112 Slice + 1,731 Gather + 1,489 Shape 的逐节点形状推演）。固定形状并做常量折叠后：
  **24,330 → 11,491 节点，init 193.6s → 1.51s**。
- 数值：随机输入下 logits 最大差 **1.9e-6**（softmax 后约 5e-7，远小于 B1-03 对齐阈值 1e-4）。
  仍属「改变推理数值」，且模型文件在 `backend/resources/`（不属本批所有权），故**默认不换**。

## 实测数据（本机，backend/.venv，onnxruntime 1.31.1）

| 场景 | 会话初始化 | 推理 |
|---|---|---|
| 原始模型 · ENABLE_ALL | 155.7s | 0.029s |
| 原始模型 · DISABLE_ALL + 单线程 | 198.0s | 0.042s |
| 原始模型 · ENABLE_BASIC | 203.9s | 0.037s |
| 原始模型 · 同进程第二次创建 | 186.9s | 0.061s |
| 手写 1 节点模型 | 0.06s | — |
| 合成 Add 链 100 / 1k / 5k / 12k 节点 | 0.05 / 0.07 / 0.36 / 0.84s | — |
| **onnxsim 简化版（11,491 节点）** | **1.51s** | 0.03s |

- 模型：`cardia_k4_best.onnx` 5.6MB，opset 17，ir 8，输入 `x[batch,64,104]`、`dt[batch,64]`，
  24,330 节点 / 46 initializer（2.89MB float32 ≈ 722k 参数）。
- 简化命令：`onnxsim.simplify(model, overwrite_input_shapes={"x":[1,64,104],"dt":[1,64]})`，
  4.4s 完成，产物 4.88MB。

## 排除项

- **provider**：`providers=["CPUExecutionProvider"]` 已生效；列表里的 AzureExecutionProvider 未注册。
- **优化级别**：ALL / BASIC / DISABLE_ALL 无差别（关闭优化反而更慢）。
- **ORT 版本**：项目 venv 只有 1.31.1，且没有 pip/uv；未降级（用系统 pip `--target` 临时装
  onnx/onnxsim 仅用于本次诊断，未写入项目依赖）。
- **系统因素**：模型从 bytes 加载（B1-03 已规避中文路径）；同进程重复创建同样慢，排除一次性缓存；
  Defender/磁盘无法解释 1 节点模型 0.06s 与 24k 节点模型 150s 的差异。

## 已交付的绕过（本批）

- `analysis/model.py`：`prewarm()`、会话初始化耗时记录、`EH_ORT_OPT_LEVEL` /
  `EH_ORT_INTRA_THREADS` / `EH_ORT_INTER_THREADS`（默认行为不变，数值路径未动）。
- 模块 `warmup`/`health` 后台预热 + 轮询；核心 `GET /engine` 暴露
  `warming|ready|error`、`warmupSeconds`、`readyAt`、模型卡摘要；HTTP 就绪不阻塞。
- 冷启动到 ready 实测：空闲 158.6s；本机有其他 Agent 并行跑测试时 392.6s（同一实现，
  差异来自 CPU 争用）——`GET /engine` 如实反映。

## 建议（需指挥官决策）

1. 批准把 onnxsim 产物作为官方权重（建议放模块 `models/`，由 Cardia 模块自带），
   预计启动 150s → ~2s；需重跑 B1-03 对齐测试（阈值 1e-4，预期通过）。
2. 或者在 CI 构建期做 onnxsim，仓库只提交简化图。
3. 若保留原图，则维持「后台预热 + UI 明确提示」，当前实现已满足。

## 复现

```powershell
# 临时环境（不影响项目依赖）
python -m pip install --target <tmp> onnx==1.17.0 onnxsim
# 见 reports 同目录的实测脚本逻辑：simplify(overwrite_input_shapes=...) → ort.InferenceSession
```
