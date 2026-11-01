# I1 · Relay 睡眠模型包（3 个自研 + 2 个更低基线）

> 先读 `prompts/00-COMMON.md`、`docs/MODULE_CONTRACT_V2.md`、`docs/MODULE_CANDIDATES_30.md`。
> **思考强度：low。** 目标是把用户已训练的 Sleep-EDF Relay 模型做成可选模块，不做论文级重训。

## 数据来源（已核实）

根目录：`C:\Users\qiumuhan\Downloads\relay LSTM\10月23日Sleep-EDF复现`

- 模型工厂：`trackb/models.py`、`trackb/models_baselines.py`、`trackb/models_relay.py`、`trackb/models_relay_v2_full.py`；特征维度 272，5 类（W/N1/N2/N3/R），输入 `(B,T,272)` + `dt`。
- 自研权重（pilot 可加载）：
  1. `results_trackb/_pilot/_ckpt/pilot_paper_highway_h_k2_S10_C256_lr2e-3_seed0/state.pt`（BA 0.8139）
  2. `results_trackb/_pilot/_ckpt/pilot_paper_highway_h_k2_S10_B256_lr1e-3_seed0/state.pt`（BA 0.8118）
  3. `results_trackb/_pilot/_ckpt/pilot_bilstm_L4_S10_B256_lr1e-3_seed0/state.pt`（BA 0.8083）
- 基线权重（必须低于上面 3 个）：
  4. `results/full/_ckpt/chambon2018_seed4/params.pt`（BA 0.7883）
  5. `results/full/_ckpt/attnsleep_seed1/params.pt`（若不存在则用 seed0；BA 0.757–0.765）
- 测试数据/特征：`trackb/seq_cache`、`trackb/features/2ch`；不要提交数据集。

## 交付

### 1. 选权重与导出 ONNX

- 在 `modules/official/relay-sleep/models/` 放 5 个 `.onnx`（或先放 `uploads/relay-sleep/`，打包时复制；不提交大权重到 git）。
- 用 base Python（`C:\Users\qiumuhan\anaconda3\python.exe`，torch 2.5.1）加载各 state，按对应 model factory 构建，`torch.onnx.export` 固定 `seq_len=10`，输入名 `features [B,10,272]`、`dt [B,10,1]`，输出 `logits [B,10,5]`；`opset=17`，dynamic batch。
- 用同一份验证 batch 对比 PyTorch/onnxruntime 的 argmax，一致率 ≥99%；写 `verify.json`（每模型 BA、参数量、导出输入形状、校验一致率、sha256）。
- 模型元数据 `models/index.json`：`{id,name,source:"relay",class:"ours|baseline",score,metric:"balanced_accuracy",file,sha256,seqLen,classes}`；基线分数必须 < 自研最低分 0.8083。

### 2. 模块

- `modules/official/relay-sleep/`：
  - `module.json`：`type:"analysis-model"`，`id:"org.eclipsehealth.relay-sleep"`，`contributes.models[]` 5 个模型（name/modelCard 含分数、非诊断声明），`ui.pages` 一个「睡眠分期」页，`ui.widgets` 一个「睡眠分期摘要」卡；权限 `records:read`，依赖 `numpy>=1.26`、`onnxruntime>=1.17`（特征提取若需 mne 可写 `mne>=1.8`，但先只用已缓存的 272 维特征/用户导入 npz）。
  - `src/main.py` stdio JSON-RPC：`health`、`warmup`、`list_models`、`predict`（输入 `features` 数组或 npz 路径 + `modelId`），返回 5 类逐窗 logits/argmax；不做 EDF 解码（留给后续）。
  - `src/adapter.py` 纯函数：feature 形状校验、softmax、类别映射、摘要。
  - `README.md`/`NOTICE`：模型为你自研；基线来源 Chambon2018/AttnSleep（braindecode/torch），非诊断声明；权重不提交 git（`.gitignore` 加 `modules/official/relay-sleep/models/*.onnx` 或使用 uploads）。
- 测试 `backend/tests/modules/test_official_relay_sleep.py`：manifest schema、5 模型元数据、特征形状、softmax 求和、缺权重 skip、分数排序断言（ours > baseline）。

### 3. 打包

- 更新 `scripts/pack_official_modules.py`（或新增脚本）把 `uploads/relay-sleep/models/*.onnx` 复制进模块 staging 再打包；输出 `dist/modules/org.eclipsehealth.relay-sleep-0.1.0.ehmod`。
- 不要求本轮接入主界面；模块页安装后由现有模块页/页面渲染器展示。

## 文件所有权（只改这些）

- `modules/official/relay-sleep/**`（新建）
- `backend/tests/modules/test_official_relay_sleep.py`
- `scripts/pack_official_modules.py`（只加 relay-sleep 权重复制逻辑）
- `.gitignore`（权重）
- `reports/I1-relay-sleep-report.md`

## 明确不做

- 不重新训练、不改用户原始代码/数据；不把 100MB 权重提交 git。
- 不做 EDF→特征提取（本轮只接 272 维特征/npz）；不新增核心依赖。
- 不 commit；不改 `prompts/`、`uploads/` 之外的用户文件。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend modules/official scripts
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_relay_sleep.py -q
```

报告 `reports/I1-relay-sleep-report.md`，≤80 行：5 个权重、导出/校验、分数、模块 API、未做项。
