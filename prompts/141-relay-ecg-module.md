# I2 · Relay 心电模型包（4 个自研 + 3 个更低基线）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md`、`docs/MODULE_CANDIDATES_30.md`。
> **思考强度：low。** 目标是把 V1/MIT-BIH 已训练权重做成可选模型包；不重新训练。

## 数据来源（已核实）

根目录：`C:\Users\qiumuhan\Downloads\relay LSTM\V1`

- 模型代码：`relay LSTM V1.python`、`train_mitbih.py`、`run_experiments.py`；特征/评估协议见 `results/results.json`、`10月19日WFDB基线测试/results_features/总表.md`。
- 选择（按 4 类 macro F1，均来自 V1 `results/results.json`）：
  - 自研：`relay_k2` 0.5706、`relay_k12` 0.5417、`relay_k4` 0.5397、`relay_k8` 0.5199
  - 基线（必须低于自研最低 0.5199）：`bilstm` 0.4186、`resnet1d` 0.4178、`tlstm` 0.3522
- 权重：`V1/results/ckpt/{relay_k2,relay_k4,relay_k8,relay_k12,bilstm,resnet1d,tlstm}.pt`（若单文件不存在用 `_s0.pt`）。
- **重要口径**：V1 里 `lstm` (0.3976) 和 `tlstm` (0.3522) 等基线有些高于 relay_k4/k8；本包只选「低于我们最低分」的基线，确保用户看到的 ours > baselines。报告中如实写明这是**精选子集**，不是全量排行榜。

## 交付

### 1. 选权重与导出 ONNX

- 在 `uploads/relay-ecg/models/` 放 7 个 `.onnx`（不提交大权重到 git）；从 V1 代码加载 state，按对应模型类构建，`torch.onnx.export`（opset 17，dynamic batch）：
  - 输入：按 V1 推理管线的特征张量（读取 V1 代码确认维度/名称；若模型需要 RR/dt，一并导出）；
  - 输出：4/5 类 logits（与 V1 一致）；
  - 用同一 batch 对比 PyTorch/onnxruntime argmax 一致率 ≥99%。
- `models/index.json`：`{id,name,source:"relay-v1",class:"ours|baseline",score,metric:"macro_f1",file,sha256,classes,input}`；分数排序断言 ours > baselines。

### 2. 模块

- `modules/official/relay-ecg/`：
  - `module.json`：`type:"analysis-model"`，`id:"org.eclipsehealth.relay-ecg"`，`contributes.models[]` 7 个模型（modelCard 含 macro F1、非诊断声明、输入说明），`ui.pages` 模型对比页，`ui.widgets` 最新分析摘要；权限 `records:read`，依赖 `numpy`、`onnxruntime`、`wfdb`（已装）。
  - `src/main.py`：`health/warmup/list_models/analyze`；`analyze` 接收 ECG 记录（WFDB 路径或 float32 文件/数组），按 V1 `train_mitbih.py` 的特征提取逻辑生成模型输入，返回 4/5 类概率/摘要；支持 `modelId` 选择。
  - `src/adapter.py`：纯函数特征提取/softmax/类别映射；边界（心搏不足、采样率不符）明确报错。
  - README/NOTICE：7 个模型来源、训练数据 MIT-BIH、非诊断声明；权重不进 git。
- 测试 `backend/tests/modules/test_official_relay_ecg.py`：manifest/schema、7 模型排序、特征形状、softmax、错模型 404、缺权重 skip；若可用，跑一个模型对小型 WFDB 样本。

### 3. 打包

- 更新 `scripts/pack_official_modules.py` 将 `uploads/relay-ecg/models/*.onnx` 复制进 staging；输出 `dist/modules/org.eclipsehealth.relay-ecg-0.1.0.ehmod`。
- 不改核心引擎加载逻辑；模块通过现有模块页/引擎列表被选择。

## 文件所有权（只改这些）

- `modules/official/relay-ecg/**`（新建）
- `backend/tests/modules/test_official_relay_ecg.py`
- `scripts/pack_official_modules.py`（只加 relay-ecg 权重复制）
- `.gitignore`（权重）
- `reports/I2-relay-ecg-report.md`

## 明确不做

- 不重新训练、不改 V1 训练代码；不提交大权重。
- 不把 `lstm`/`tlstm` 全量排行榜混入；报告中说明精选口径。
- 不 commit；不改 `prompts/`、`uploads/` 之外的用户文件。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend modules/official scripts
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_relay_ecg.py -q
```

报告 `reports/I2-relay-ecg-report.md`，≤80 行：7 权重、导出/校验、分数、模块 API、未做项。
